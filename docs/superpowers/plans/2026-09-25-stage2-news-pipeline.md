# 階段 2：新聞進 D1 施工計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每日新聞改寫進 D1：GitHub Actions 抓取、評分、分組、標記後送 `POST /api/ingest`，Function 呼叫 Workers AI 做中文摘要再寫入；舊自動卡一次匯入 D1。

**Architecture:** Python 端拆成小模組：`tagging.py`（唯一的關鍵詞比對與標記）、`scoring.py`、`clustering.py`（語意分組）、`ingest_client.py`（呼叫 API），`fetch_news.py` 只負責串起管線。Pages Functions 新增 `/api/ingest` 與 `/api/news/recent`，驗證邏輯與 AI 呼叫抽成 `_ingest.js`、`_ai.js`，用 Node 內建 `node:sqlite` 模擬 D1 測試。所有詞表與門檻只寫在 `taxonomy.yaml`。

**Tech Stack:** Python 3.12（本機 3.13 也可）、PyYAML、feedparser、sentence-transformers（LaBSE）、trafilatura、googlenewsdecoder、pytest；Cloudflare Pages Functions、D1、Workers AI；Node 24 `node --test`。

**Spec:** `docs/superpowers/specs/2026-09-24-vault-v2-design.md`（§3、§4.3、§5、§6.1–§6.4、§10 第 1 與第 3 步、§11、§12）

**前提：** 階段 1（PR #1）已合併進 main，或至少本分支從 `redesign/vault-v2` 開出。

## 範圍

| 做 | 延後 |
|---|---|
| D1 新聞資料表（migration 0001） | 留言表改 `target` 欄位 → 階段 3（migration 0002） |
| `/api/ingest`、`/api/news/recent` | `/api/news/annotate`、管線第 12 步補註、`make retag` → 階段 4（只有手動收錄會產生 `needs_annotate=1`，手動收錄也在階段 4） |
| `fetch_news.py` 重寫、分組校準 | |
| 舊自動卡匯入 D1 | 刪除舊卡檔案 → 階段 3（新聞頁改讀 D1 之後）；刪 `99-daily/` 等 → 階段 5 |

**與 spec §12 的差異：** Functions 整合測試不用 `wrangler pages dev` 加本機 D1（沒有 `wrangler.toml` 時綁本機 D1 很麻煩），改用 Node 內建 `node:sqlite` 模擬 D1（`tests/js/fake_d1.js`，真的執行 migration SQL，含 FTS5），再加上 Task 10 的線上驗收。

**上線影響（要讓使用者知道）：** 合併進 main 後，bot 不再 commit 事件卡，網站首頁的新聞清單會停在合併當天，直到階段 3 新聞頁改讀 D1。舊卡保留，網站照常 build。

## Global Constraints

- 程式要能在 Python 3.10 以上執行。Cloudflare build 用 3.12，只安裝 `pyyaml markdown`：`build_site.py` 會經由 `tracker.py` 載入 `tagging.py`、`notes.py`、`taxonomy.py`，這幾個檔只能用標準庫與 PyYAML。numpy、sentence-transformers、trafilatura、googlenewsdecoder 一律在函式內延後 import。
- Windows 本機執行 Python 一律加 `PYTHONUTF8=1`。torch 要裝在短路徑 venv（例如 `C:\bvv`），否則 pip 會撞到 260 字元路徑上限（實測 scratch 目錄會失敗）。
- 含反斜線的程式碼用檔案寫入工具寫，不要經過 Bash heredoc。
- 詞表、權重、門檻、模型名稱只寫在 `taxonomy.yaml`。關鍵詞比對只用 `tagging.matches()`。
- 受保護端點的 token 放 header `x-ingest-token`，用 `_lib.js` 的 `checkToken()`（固定時間比較）。D1 例外一律回 `503 {"error":"db_unavailable"}`。
- 每批 10 則（`MAX_BATCH`）、`/api/news/recent` 每頁 500 筆、原文前 1,500 字、抓原文逾時 10 秒。
- Workers AI 模型：`@cf/qwen/qwen3-30b-a3b-fp8`。
- 不放 `wrangler.toml`（README 有寫原因）。
- `INGEST_TOKEN` 用 `python -c "import secrets;print(secrets.token_urlsafe(32))"` 產生，不寫進任何檔案、不印在 log。
- **舊自動卡（`type: event` 且 `auto: true`）這一階段不刪。** 留言表 `comments` 這一階段不動。
- 分支：`redesign/stage2-news`（從 `redesign/vault-v2` 開）。不 push，除非使用者說可以。
- 每個檔案不超過 500 行。

## Review Focus

撰寫計畫時已實際跑過全部程式碼（87 個 pytest、14 個 node 測試、一次真實 RSS 的 dry-run：778 則 → 177 則達門檻 → 60 個分組）。以下是規格沒寫、但最容易出錯的五種輸入，各已在對應 task 加了測試：

1. **英文一般字撞到縮寫**：「banks did not…」不能被當成 `DID`。舊版全部轉小寫比對，這個錯誤已經在線上。→ Task 1 `test_english_verb_did_is_not_DID`
2. **簡體中文新聞**：PANews、吳說是簡體，「稳定币」要命中「穩定幣」。舊版完全漏抓。→ Task 1 `test_simplified_chinese_hits_traditional_keyword`、Task 2 `test_countries_and_tracks_use_shared_matcher`
3. **Google News 轉址解不開**（套件壞掉或單則失敗）：新聞仍要入庫，`url_resolved=0`。→ Task 7 `test_decode_gnews_*`
4. **新分組的報導全是重複網址**：不能留下 `item_count=0` 的空分組。→ Task 5 `重複網址…全重複時不開空分組`
5. **同一新分組跨兩批送出**：第二批要併進第一批建立的分組，不能開成兩組。→ Task 6 `test_new_cluster_split_across_batches_reuses_real_id`

另外兩個既有漏洞順手修掉，在 Task 1 註明：複數 `stablecoins` 原本完全不計分（改成字根 `stablecoin*`）；轄區規則原本寫死在 `tracker.py`（搬到 taxonomy）。

---

## 檔案結構

| 檔案 | 動作 | 職責 |
|---|---|---|
| `taxonomy.yaml` | 修改 | 加 `jurisdiction_rules`、`title_only`、`scoring`、`clustering` |
| `scripts/taxonomy.py` | 修改 | 必要欄位加四個；檢查轄區規則的 key 都在 `jurisdictions` |
| `scripts/tagging.py` | 新增 | `matches()`、`to_trad()`、`note_terms()`、`tags_for()` |
| `scripts/scoring.py` | 新增 | `score()` |
| `scripts/tracker.py` | 修改 | 國家規則改讀 taxonomy，比對改用 `tagging.matches()` |
| `scripts/feeds.yaml` | 修改 | 只放來源；併入 WIP 分支的新來源與 Google News 查詢 |
| `scripts/news_utils.py` | 新增 | `normalize_url()`、`clean_summary()`、`detect_lang()`、`utc_iso()` |
| `scripts/clustering.py` | 新增 | `load_embedder()`、`assign_clusters()`、`apply_limit()`、Jaccard 備援 |
| `scripts/calibrate_clusters.py` | 新增 | 門檻校準 |
| `scripts/ingest_client.py` | 新增 | `Client.recent()`、`Client.ingest()`、`client_from_env()` |
| `scripts/fetch_news.py` | 重寫 | 管線：`parse_entry()`、`collect()`、`decode_gnews()`、`prepare_payload()`、`main()` |
| `scripts/import_legacy.py` | 新增 | 舊自動卡 → D1 |
| `db/migrations/0001_news.sql` | 新增 | 新聞資料表、FTS5、trigger |
| `functions/_lib.js` | 修改 | 加 `safeEqual()`、`checkToken()`、`dbUnavailable()` |
| `functions/api/comments/[id].js` | 修改 | 改用 `_lib.js` 的 `safeEqual()` |
| `functions/_ingest.js` | 新增 | `validateItem()`、`MAX_BATCH` |
| `functions/_ai.js` | 新增 | `buildMessages()`、`parseSummary()`、`summarize()` |
| `functions/api/ingest.js` | 新增 | `POST /api/ingest` |
| `functions/api/news/recent.js` | 新增 | `GET /api/news/recent` |
| `.github/workflows/news.yml` | 重寫 | 每日送 D1；手動 `mode=import` 匯入舊卡 |
| `requirements-news.txt` | 新增 | Actions 管線相依 |
| `requirements-dev.txt` | 修改 | 加 `feedparser`、`numpy` |
| `Makefile` | 修改 | `peek`、`calibrate`、`test`、`install-news`；刪 `fetch`、`update` |
| `scripts/README.md` | 重寫 | 新管線說明 |
| `docs/decisions.md` | 新增 | 分組校準結果、AI 抽查紀錄 |
| `tests/test_*.py`、`tests/js/*`、`tests/fixtures/cluster_calibration.yaml` | 新增 | 測試 |

---

### Task 1：taxonomy 評分設定、共用比對與評分

**Files:**
- Modify: `taxonomy.yaml`、`scripts/taxonomy.py`、`requirements-dev.txt`
- Create: `scripts/tagging.py`、`scripts/scoring.py`
- Test: `tests/test_tagging.py`、`tests/test_scoring.py`

**Interfaces:**
- Produces: `tagging.matches(kw: str, text: str) -> bool`；`tagging.to_trad(s) -> str`；`tagging.note_terms(root: Path) -> list[tuple[str, list[str]]]`；`tagging.tags_for(item: dict, tax: dict, terms: list) -> list[{"kind","key"}]`（item 需有 `title`、`rss_summary`、`source_feed`）。
- Produces: `scoring.score(title, summary, tier, sc: dict, assume_core=False) -> tuple[int, list[str]]`，`sc` 是 `tax["scoring"]`。
- Produces: `taxonomy.yaml` 的 `clustering: {model, threshold, window_days, jaccard_fallback}`、`limits.daily_top`、`limits.min_score`。

- [ ] **Step 1：開分支、裝相依**

計畫檔所在的分支 `redesign/stage2-news` 已從 `redesign/vault-v2` 開出。PR #1 若在審閱中又有新 commit，先 rebase：

```bash
cd C:/Users/user/Documents/blockchain-vault
git switch redesign/stage2-news
git rebase redesign/vault-v2
```

`requirements-dev.txt` 改成：

```
pyyaml
markdown
pytest
feedparser
numpy
```

```bash
python -m pip install -r requirements-dev.txt
```

- [ ] **Step 2：寫失敗的測試**

`tests/test_tagging.py`：

```python
import tagging
from tagging import matches, tags_for, note_terms


def test_s2t_table_has_unique_pairs():
    simp = tagging._PAIRS[0::2]
    assert len(tagging._PAIRS) % 2 == 0
    assert len(set(simp)) == len(simp)
    assert all(a != b for a, b in zip(simp, tagging._PAIRS[1::2]))
    assert tagging.to_trad("稳定币监管") == "穩定幣監管"


def test_matches_rules():
    assert matches("SEC", "SEC approves ETF")
    assert not matches("SEC", "Securities firm")          # 單字邊界
    assert not matches("DID", "the bank did it")          # 全大寫縮寫區分大小寫
    assert matches("tokeniz*", "Tokenized deposits")      # 字根、不分大小寫
    assert not matches("stablecoin", "stablecoins2x")
    assert matches("U.S.", "U.S. Treasury")
    assert matches("穩定幣", "香港稳定币条例")              # 簡轉繁


def _item(title, summary="", feed="CoinDesk"):
    return {"title": title, "rss_summary": summary, "source_feed": feed}


def test_tags_topics_watch_jurisdiction(tax):
    tags = tags_for(_item("SoFi begins stablecoin settlement on Mastercard network"), tax, [])
    assert {"kind": "topic", "key": "穩定幣"} in tags
    assert {"kind": "topic", "key": "RWA"} in tags
    assert {"kind": "jurisdiction", "key": "美國"} in tags
    tags = tags_for(_item("JPMorgan Kinexys settles repo on chain"), tax, [])
    assert {"kind": "watch", "key": "kinexys"} in tags and {"kind": "watch", "key": "jpmorgan"} in tags


def test_jurisdiction_source_first_and_title_only_words(tax):
    tags = tags_for(_item("Speech on payments", feed="HKMA Press Releases"), tax, [])
    assert [t["key"] for t in tags if t["kind"] == "jurisdiction"] == ["香港"]
    # 「US」只在標題算數；內文出現不算
    tags = tags_for(_item("Bank pilots tokenized deposits", "Priced in US dollars"), tax, [])
    assert not [t for t in tags if t["kind"] == "jurisdiction"]


def test_note_terms_and_note_tags(tmp_vault, tax):
    (tmp_vault / "20-concepts" / "cash-leg.md").write_text(
        "---\nid: abcd2345\ntype: concept\ntitle: 現金腿\naliases: [cash leg, DvP]\n---\n", encoding="utf-8")
    (tmp_vault / "10-events" / "old.md").write_text(
        "---\ntype: event\nauto: true\ntitle: DvP 舊卡\n---\n", encoding="utf-8")
    (tmp_vault / "20-concepts" / "no-id.md").write_text("---\ntype: concept\ntitle: 沒有 id\n---\n", encoding="utf-8")
    terms = note_terms(tmp_vault)
    assert terms == [("abcd2345", ["現金腿", "cash leg", "DvP"])]
    tags = tags_for(_item("Banks test DvP settlement"), tax, terms)
    assert {"kind": "note", "key": "abcd2345"} in tags
    assert not [t for t in tags_for(_item("Dvpx launches"), tax, terms) if t["kind"] == "note"]


def test_tags_are_unique(tax):
    tags = tags_for(_item("Stablecoin stablecoin 穩定幣"), tax, [])
    assert len(tags) == len({(t["kind"], t["key"]) for t in tags})
```

`tests/test_scoring.py`：

```python
import pytest

import taxonomy
from scoring import score


@pytest.fixture
def sc(tax):
    return tax["scoring"]


def test_title_hits_count_double(sc):
    s, hits = score("SEC Clears Tokenized Stocks To Trade Onchain As CFTC Widens Software Relief", "", "trade", sc)
    assert s == 8
    assert set(hits) == {"tokeniz", "SEC"}


def test_english_verb_did_is_not_DID(sc):
    s, hits = score("Why banks did not adopt stablecoins", "", "trade", sc)
    assert "DID" not in hits
    assert s == 4


def test_simplified_chinese_hits_traditional_keyword(sc):
    s, hits = score("美联储拟对稳定币发行商实施新资本规则", "", "trade", sc)
    assert "穩定幣" in hits
    assert s == 4


def test_generic_word_needs_core_in_title(sc):
    s, hits = score("Fidelity reports quarterly earnings", "", "trade", sc)
    assert hits == [] and s == -8
    s, hits = score("Fidelity launches tokenized money market fund", "", "trade", sc)
    assert "Fidelity" in hits and s == 8


def test_assume_core_skips_core_miss_penalty(sc):
    assert score("Bank adds new custody service", "", "aggregator", sc, assume_core=True)[0] == 0
    assert score("Bank adds new custody service", "", "aggregator", sc)[0] == -6


def test_noise_words_penalised(sc):
    title = "BiFu 將亮相 Token2049 新加坡，舉辦「超越熱度：RWA 真正落地，還缺什麼？」主題晚宴與行業酒會"
    assert score(title, "", "trade", sc)[0] == -12


def test_jurisdiction_rule_must_be_known(tmp_path, tax):
    import yaml
    bad = dict(tax, jurisdiction_rules={"火星": {"keywords": ["Mars"], "sources": []}})
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(taxonomy.TaxonomyError, match="火星"):
        taxonomy.load_taxonomy(p)
```

- [ ] **Step 3：確認測試失敗**

Run: `PYTHONUTF8=1 python -m pytest tests/test_tagging.py tests/test_scoring.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'tagging'`

- [ ] **Step 4：taxonomy.yaml 加上評分、轄區、分組設定**

在 `taxonomy.yaml` 最後（`watchlist` 之後）加上以下內容。權重、組合、雜訊詞、core 詞搬自 `scripts/feeds.yaml` 與 `fetch_news.py`，再併入 WIP 分支 `wip/news-sources-expansion` 新增的機構詞。與舊版刻意不同的地方：

- 縮寫全改大寫（`ZK`、`SSI`、`DID`、`RWA`、`CBDC`、`KYC`、`AML`），因為 `matches()` 對全大寫縮寫區分大小寫。
- `stablecoin`、`deposit token`、`verifiable credential`、`digital asset` 改成字根（加 `*`），複數才會命中。
- 轄區規則逐字搬自 `tracker.py` 的 `COUNTRIES` 與 `BODY_AMBIGUOUS`。
- 分組模型用 LaBSE、門檻 0.67（Task 4 的校準結果，spec 原訂 MiniLM 0.75）。

```diff
@@ -31,3 +31,124 @@ watchlist:
   - {id: fireblocks, name: Fireblocks,           aliases: [Fireblocks]}
   - {id: zk,         name: Zero knowledge,       aliases: [zero knowledge, ZKP, zkEVM, 零知識]}
   - {id: polygon,    name: Polygon／Privado ID,  aliases: [Polygon, Polygon ID, Privado ID]}
+
+# ── 轄區判斷規則（新聞標記與各國進度共用）──
+# keywords 比對標題與內文；sources 比對來源名稱開頭；title_only 的詞只在標題裡算數
+jurisdiction_rules:
+  美國:
+    keywords: [美國, 美联储, 聯準會, 美國財政部, U.S., US, American, SEC, Fed, Federal Reserve,
+               OCC, FDIC, CFTC, FinCEN, Treasury, GENIUS, Congress, White House,
+               SoFi, Mastercard, Visa, Circle, Coinbase, JPMorgan, BlackRock, Paxos,
+               Anchorage, Ondo, Nasdaq, NYSE, DTCC, Citi, Goldman, Fiserv]
+    sources: [SEC, Federal Reserve, OCC, FDIC, CFTC, FinCEN]
+  歐盟:
+    keywords: [歐盟, 歐洲央行, 欧盟, EU, European, Europe, ECB, Eurosystem, ESMA, EBA, MiCA]
+    sources: [ECB, ESMA, EBA]
+  英國:
+    keywords: [英國, 英国, UK, U.K., Britain, British, Bank of England, BoE, FCA]
+    sources: [Bank of England]
+  香港:
+    keywords: [香港, Hong Kong, HKMA, 金管局, 證監會, SFC]
+    sources: [HKMA, SFC HK]
+  新加坡: {keywords: [新加坡, Singapore, MAS], sources: [MAS]}
+  日本: {keywords: [日本, Japan, Japanese, JFSA], sources: [Japan FSA]}
+  韓國: {keywords: [韓國, 韩国, 南韓, Korea, Korean, Kakao, KakaoBank, Upbit, Naver], sources: []}
+  台灣: {keywords: [台灣, 臺灣, Taiwan, 金管會, 央行總裁], sources: [金管會]}
+  加拿大: {keywords: [加拿大, Canada, Canadian], sources: []}
+
+title_only: [US, U.S., American, Treasury, Fed, Congress, Europe, European, EU,
+             UK, U.K., British, Korean, Japanese, Canadian, Visa, Mastercard, Circle]
+
+# ── 新聞評分（fetch_news.py）──
+# 關鍵詞比對規則見 scripts/tagging.py 的 matches()：全大寫縮寫區分大小寫，尾端 * 表示字根
+scoring:
+  cap: 20                  # 關鍵詞＋組合加分的上限；之後才加減雜訊與 tier
+  tier_bonus: {primary: 4, trade: 0, aggregator: -2}
+  core_miss_penalty: -8    # 沒命中任何 core 詞
+  noise_penalty: -6        # 每命中一個雜訊詞
+  weights:
+    ZK: 3
+    零知識: 3
+    zero-knowledge: 3
+    zk-proof: 3
+    SSI: 3
+    DID: 3
+    "verifiable credential*": 3
+    可驗證憑證: 3
+    數位身分: 2
+    RWA: 3
+    "tokeniz*": 2
+    "tokenis*": 2
+    代幣化: 2
+    "stablecoin*": 2          # 字根：stablecoins 也要算
+    穩定幣: 2
+    "settle*": 2
+    結算: 2
+    DvP: 3
+    wCBDC: 3
+    CBDC: 2
+    "regulat*": 2
+    法規: 2
+    監理: 2
+    金管會: 3
+    FSC: 1
+    HKMA: 2
+    SFC: 2
+    FinCEN: 3
+    SEC: 2
+    BIS: 2
+    "custod*": 1
+    "licens*": 2
+    licence: 2
+    "deposit token*": 3
+    代幣化存款: 3
+    託管: 1
+    Chainlink: 3
+    CCIP: 3
+    Kinexys: 3
+    Onyx: 2
+    JPMorgan: 2
+    J.P. Morgan: 2
+    JP Morgan: 2
+    摩根大通: 2
+    Fidelity: 2
+    富達: 2
+    BNY: 2
+    紐約梅隆: 2
+    Fireblocks: 3
+    Polygon: 2
+    Polygon ID: 3
+    Privado ID: 3
+    zero knowledge: 3
+    ZKP: 3
+    zkEVM: 3
+    Hyperledger: 2
+  combos:                  # a 組與 b 組各命中至少一個才加分
+    - {a: [代幣化, "tokeniz*", "tokenis*"], b: [結算, "settle*", DvP, CBDC], bonus: 4}
+    - {a: [穩定幣, "stablecoin*"], b: [法規, 監理, "regulat*", licence, license], bonus: 3}
+    - {a: [SSI, DID, "verifiable credential*", 可驗證憑證, 數位身分], b: [KYC, AML, 法規, 監理, "regulat*"], bonus: 4}
+    - {a: [ZK, 零知識, zero-knowledge], b: [身分, identity, 隱私, privacy, compliance, 法遵], bonus: 4}
+    - {a: [RWA, 代幣化], b: [基金, fund, 債券, bond, 黃金, gold, 存款, deposit], bonus: 3}
+  core: [ZK, 零知識, zero-knowledge, SSI, DID, "verifiable credential*", 可驗證憑證, 數位身分, RWA,
+         "tokeniz*", "tokenis*", 代幣化, "stablecoin*", 穩定幣, CBDC, DvP, blockchain, 區塊鏈,
+         distributed ledger, "digital asset*", 虛擬資產, 數位資產, settlement asset, 結算資產,
+         Chainlink, CCIP, Kinexys, Fireblocks, Polygon ID, Privado ID, zero knowledge, ZKP, zkEVM, Hyperledger]
+  # 泛用詞：標題沒有同時命中 core 詞時不計分（Polygon 幾何、Fidelity 保險、Onyx 他牌）
+  generic: [Polygon, Fidelity, 富達, Onyx]
+  noise: [晚宴, 酒會, 峰會, 論壇, 嘉賓, 報名, 贊助, 空投, airdrop, AMA, giveaway, 限時, 優惠,
+          將亮相, 盛大, 即將舉行, price prediction, price analysis, 價格預測]
+  topic_map:               # 新聞 topic 標記：命中任一詞就標該主題
+    ZK: [ZK, 零知識, zero-knowledge, zk-proof, zero knowledge, ZKP, zkEVM]
+    SSI: [SSI, DID, "verifiable credential*", 可驗證憑證, 數位身分]
+    RWA: [RWA, "tokeniz*", "tokenis*", 代幣化, 代幣化存款, "deposit token*", DvP, "settle*", 結算]
+    金融法規: ["regulat*", "licens*", licence, 法規, 監理, 金管會, FinCEN, SEC, HKMA, SFC, BIS]
+    穩定幣: ["stablecoin*", 穩定幣, CBDC, wCBDC]
+    重點機構: [Chainlink, CCIP, Kinexys, Onyx, JPMorgan, J.P. Morgan, JP Morgan, 摩根大通, Fidelity, 富達,
+             BNY, 紐約梅隆, Fireblocks, Polygon, Polygon ID, Privado ID, Hyperledger]
+
+# ── 事件分組（scripts/clustering.py）──
+clustering:
+  model: sentence-transformers/LaBSE   # 校準結果見 docs/decisions.md；換模型要同步改 news.yml 的快取 key
+  threshold: 0.67          # cosine 門檻
+  window_days: 14          # 新報導跟幾天內的報導比對
+  jaccard_fallback: 0.35   # 模型載入失敗時退回標題 Jaccard 的門檻
```

- [ ] **Step 5：`scripts/taxonomy.py` 加必要欄位與轄區檢查**

```diff
@@ -4,7 +4,8 @@ from pathlib import Path
 import yaml
 
 ROOT = Path(__file__).resolve().parent.parent
-REQUIRED = ("limits", "topics", "jurisdictions", "tracks", "stages", "maturity", "origins", "watchlist")
+REQUIRED = ("limits", "topics", "jurisdictions", "tracks", "stages", "maturity", "origins", "watchlist",
+            "jurisdiction_rules", "title_only", "scoring", "clustering")
 
 
 class TaxonomyError(ValueError):
@@ -24,4 +25,7 @@ def load_taxonomy(path: Path = ROOT / "taxonomy.yaml") -> dict:
     ids = [w["id"] for w in data["watchlist"]]
     if len(ids) != len(set(ids)):
         raise TaxonomyError("watchlist id 重複")
+    unknown = [j for j in data["jurisdiction_rules"] if j not in data["jurisdictions"]]
+    if unknown:
+        raise TaxonomyError("jurisdiction_rules 有不在 jurisdictions 的轄區：" + ", ".join(unknown))
     return data
```

- [ ] **Step 6：建立 `scripts/tagging.py`**

```python
"""關鍵詞比對與新聞標記。評分、標記、各國進度都用這裡的 matches()，不要在別處另寫一套。

只依賴標準庫與 notes.py（PyYAML），因為 build_site.py 經由 tracker.py 會載入它，
而 Cloudflare build 只裝 pyyaml、markdown。
"""
import re
from pathlib import Path

import notes as notes_mod

ASCII_KW = re.compile(r"[A-Za-z0-9 .\-]+")
UPPER_DOTTED = re.compile(r"[A-Z](\.[A-Z])+\.?")

# 簡體 → 繁體的單字對照，只涵蓋本站主題常見字，讓「稳定币」也能命中「穩定幣」。
# ponytail: 逐字對照，詞彙差異（监管／監理）不處理；漏抓變多再改用 opencc
_PAIRS = ("币幣稳穩链鏈块塊监監规規资資产產银銀结結证證数數为為务務发發与與国國际際场場机機构構权權"
          "应應业業执執会會员員税稅贷貸汇匯兑兌实實现現网網络絡这這个個们們时時间間进進对對说說开開"
          "关關联聯备備储儲报報项項协協议議条條领領导導总總统統财財经經济濟贸貿纳納达達韩韓欧歐华華"
          "东東亚亞户戶账賬转轉让讓签簽认認质質杠槓杆桿预預测測创創试試点點颁頒许許虚虛拟擬钱錢托託"
          "价價额額长長线線众眾筹籌买買卖賣盘盤仓倉险險边邊隐隱验驗凭憑据據码碼电電讯訊云雲区區广廣"
          "义義兴興举舉传傳体體债債偿償则則动動单單变變号號启啟团團圣聖处處复復学學审審宪憲将將层層"
          "属屬岁歲师師带帶库庫张張强強录錄态態战戰扩擴护護担擔择擇换換损損断斷无無旧舊显顯标標样樣"
          "检檢极極气氣没沒涨漲满滿热熱状狀独獨环環画畫盖蓋矿礦确確离離种種积積竞競简簡类類紧緊约約"
          "级級练練组組终終维維综綜续續罗羅职職胜勝艺藝节節获獲营營补補视視计計订訂讨討训訓记記讲講"
          "论論设設访訪评評识識诉訴译譯询詢该該详詳语語请請读讀调調谈談负負责責败敗货貨购購费費贵貴"
          "赔賠赚賺赛賽趋趨车車轮輪软軟较較输輸过過运運还還远遠违違连連适適选選释釋针針铁鐵销銷锁鎖"
          "错錯键鍵门門问問队隊阶階陆陸随隨难難页頁顶頂顺順须須频頻题題风風飞飛驱驅龙龍黄黃齐齊")
S2T = str.maketrans(_PAIRS[0::2], _PAIRS[1::2])


def to_trad(s: str) -> str:
    return s.translate(S2T)


def matches(kw: str, text: str) -> bool:
    """關鍵詞是否出現在 text。

    - 中日韓字：子字串比對，雙方先轉繁體。
    - 英數：單字邊界。全大寫縮寫（SEC、DID、U.S.）區分大小寫，
      否則英文動詞 did 會命中 DID；其餘不分大小寫。
    - 尾端 * 表示字根，只放寬右邊界（tokeniz* 命中 tokenized）。
    """
    stem = kw.endswith("*")
    k = kw[:-1] if stem else kw
    if not ASCII_KW.fullmatch(k):
        return to_trad(k.lower()) in to_trad(text.lower())
    right = "" if stem else r"(?![A-Za-z0-9])"
    if k.isupper() or UPPER_DOTTED.fullmatch(k):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(k)}{right}", text) is not None
    return re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}{right}", text.lower()) is not None


def topic_tags(text: str, tax: dict) -> list:
    return [t for t, kws in tax["scoring"]["topic_map"].items() if any(matches(k, text) for k in kws)]


def watch_tags(text: str, tax: dict) -> list:
    return [w["id"] for w in tax["watchlist"] if any(matches(a, text) for a in w["aliases"])]


def jurisdiction_tags(title: str, summary: str, source_feed: str, tax: dict) -> list:
    """優先序：來源名稱 → 標題關鍵詞 → 內文關鍵詞（title_only 的泛稱不算）。與 tracker.countries_of 相同。"""
    rules = tax["jurisdiction_rules"]
    by_src = [c for c, r in rules.items() if any(s and source_feed.startswith(s) for s in r.get("sources") or [])]
    if by_src:
        return by_src
    by_title = [c for c, r in rules.items() if any(matches(k, title) for k in r["keywords"])]
    if by_title:
        return by_title
    title_only = set(tax["title_only"])
    return [c for c, r in rules.items()
            if any(matches(k, summary) for k in r["keywords"] if k not in title_only)]


def note_terms(root: Path) -> list:
    """[(筆記 id, [title 與 aliases])]。跳過壞檔、舊自動卡、沒有 id 的筆記；詞長至少 2。"""
    out = []
    for n in notes_mod.iter_notes(root):
        if n.error or notes_mod.is_legacy_auto(n) or not n.fm.get("id"):
            continue
        raw = [n.fm.get("title")] + list(n.fm.get("aliases") or [])
        terms = [str(t).strip() for t in raw if t is not None and len(str(t).strip()) >= 2]
        if terms:
            out.append((str(n.fm["id"]), terms))
    return out


def tags_for(item: dict, tax: dict, terms: list) -> list:
    """一則新聞的標記：[{kind, key}]，不重複。比對標題＋RSS 摘要。"""
    title, summary = item["title"], item.get("rss_summary") or ""
    text = f"{title} {summary}"
    pairs = ([("topic", k) for k in topic_tags(text, tax)]
             + [("watch", k) for k in watch_tags(text, tax)]
             + [("note", nid) for nid, ts in terms if any(matches(t, text) for t in ts)]
             + [("jurisdiction", k) for k in jurisdiction_tags(title, summary, item["source_feed"], tax)])
    return [{"kind": k, "key": v} for k, v in dict.fromkeys(pairs)]
```

- [ ] **Step 7：建立 `scripts/scoring.py`**

```python
"""新聞評分。規則全在 taxonomy.yaml 的 scoring，這裡只有算法。"""
from tagging import matches


def score(title: str, summary: str, tier: str, sc: dict, assume_core: bool = False):
    """回傳 (分數, 命中的權重詞)。

    1. 權重詞：標題命中算兩倍。generic 泛用詞只在標題也命中 core 詞時才算。
    2. 組合加分：a、b 兩組都命中才加。
    3. 封頂 cap，再扣雜訊詞。
    4. 命中 core（或來源本身就是主題查詢 assume_core）才給 tier 加分，否則扣 core_miss_penalty。
    """
    text = f"{title} {summary}"
    title_core = any(matches(c, title) for c in sc["core"])
    generic = set(sc.get("generic") or [])
    hits, s = [], 0
    for kw, w in sc["weights"].items():
        in_t, in_s = matches(kw, title), matches(kw, summary)
        if not (in_t or in_s):
            continue
        if kw in generic and not title_core:
            continue
        s += w * 2 if in_t else w
        hits.append(kw.rstrip("*"))
    for c in sc["combos"]:
        if any(matches(x, text) for x in c["a"]) and any(matches(y, text) for y in c["b"]):
            s += c["bonus"]
    s = min(s, sc["cap"])
    s += sc["noise_penalty"] * sum(1 for n in sc["noise"] if matches(n, text))
    core_hit = assume_core or any(matches(c, text) for c in sc["core"])
    s += sc["tier_bonus"].get(tier, 0) if core_hit else sc["core_miss_penalty"]
    return s, hits
```

- [ ] **Step 8：確認測試通過**

Run: `PYTHONUTF8=1 python -m pytest -q`
Expected: 全部 PASS（含階段 1 的既有測試）

- [ ] **Step 9：Commit**

```bash
git add taxonomy.yaml requirements-dev.txt scripts/taxonomy.py scripts/tagging.py scripts/scoring.py tests/test_tagging.py tests/test_scoring.py
git commit -m "feat: 評分與標記規則搬進 taxonomy，共用 matches()（縮寫區分大小寫、簡轉繁）"
```

---

### Task 2：tracker 改讀 taxonomy；feeds.yaml 只放來源

**Files:**
- Modify: `scripts/tracker.py`、`scripts/feeds.yaml`
- Test: `tests/test_tracker.py`

**Interfaces:**
- Consumes: `taxonomy.load_taxonomy()`、`tagging.matches()`（Task 1）。
- Produces: `tracker.COUNTRIES`、`tracker.BODY_AMBIGUOUS` 形狀不變（`build_site.py` 在用）。`feeds.yaml` 只剩 `primary`、`trade`、`aggregator` 三個清單；`aggregator` 每項有 `name`、`query`、選填 `lang`（`en`／`tw`）、`assume_core`。

- [ ] **Step 1：寫失敗的測試** `tests/test_tracker.py`

```python
import tracker


def _note(title, body="", folder="10-events", **fm):
    return {"title": title, "body": body, "folder": folder, **fm}


def test_countries_come_from_taxonomy(tax):
    assert [c for c, _ in tracker.COUNTRIES] == list(tax["jurisdiction_rules"])
    assert "US" in tracker.BODY_AMBIGUOUS


def test_countries_and_tracks_use_shared_matcher():
    n = _note("美联储：代币化证券新规")                    # 簡體標題，議題詞只有繁體版
    assert tracker.countries_of(n) == ["美國"]
    assert "代幣化證券／RWA" in tracker.tracks_of(n)
    assert tracker.countries_of(_note("Why banks did not adopt it", source_name="SEC Press Releases")) == ["美國"]
    assert tracker.countries_of(_note("Bank pilots deposits", "Priced in US dollars")) == []
```

- [ ] **Step 2：確認失敗**

Run: `PYTHONUTF8=1 python -m pytest tests/test_tracker.py -q`
Expected: FAIL（`test_countries_come_from_taxonomy` 或簡體標題那一行）

- [ ] **Step 3：先存一份目前的各國進度頁，改完後比對**

```bash
PYTHONUTF8=1 python scripts/build_site.py >/dev/null && cp site/tracker.html /tmp/tracker-before.html
```

- [ ] **Step 4：修改 `scripts/tracker.py`**

刪掉檔案裡的 `COUNTRIES`、`BODY_AMBIGUOUS` 定義與 `_match()`，改讀 taxonomy、改用 `matches()`：

```diff
@@ -4,38 +4,20 @@
 - 階段只來自你寫的法規筆記（40-regulations）：status 文字自動換算，或用 frontmatter 的 stage: 1–5 直接指定。
 - 事件卡只當「動態」掛在格子的時間軸上，不會自動改階段——進度判斷要人來做。
 
-國家、議題、關鍵詞都寫在這個檔案最上面，要加國家或調整分類改這裡就好。
+國家的判斷規則在 taxonomy.yaml 的 jurisdiction_rules；議題與階段的關鍵詞寫在這個檔案。
 """
 import re
 
-# ── 國家：依顯示順序。keywords 比對標題與內文開頭；sources 比對事件的來源名稱 ──
-COUNTRIES = [
-    ("美國", dict(
-        keywords=["美國", "美联储", "聯準會", "美國財政部", "U.S.", "US", "American", "SEC", "Fed", "Federal Reserve",
-                  "OCC", "FDIC", "CFTC", "FinCEN", "Treasury", "GENIUS", "Congress", "White House",
-                  # 主要美國業者：標題沒寫國名時靠它們判斷（例：SoFi 穩定幣結算）
-                  "SoFi", "Mastercard", "Visa", "Circle", "Coinbase", "JPMorgan", "BlackRock", "Paxos",
-                  "Anchorage", "Ondo", "Nasdaq", "NYSE", "DTCC", "Citi", "Goldman", "Fiserv"],
-        sources=["SEC", "Federal Reserve", "OCC", "FDIC", "CFTC", "FinCEN"])),
-    ("歐盟", dict(
-        keywords=["歐盟", "歐洲央行", "欧盟", "EU", "European", "Europe", "ECB", "Eurosystem", "ESMA", "EBA", "MiCA"],
-        sources=["ECB", "ESMA", "EBA"])),
-    ("英國", dict(
-        keywords=["英國", "英国", "UK", "U.K.", "Britain", "British", "Bank of England", "BoE", "FCA"],
-        sources=["Bank of England"])),
-    ("香港", dict(
-        keywords=["香港", "Hong Kong", "HKMA", "金管局", "證監會", "SFC"],
-        sources=["HKMA", "SFC HK"])),
-    ("新加坡", dict(keywords=["新加坡", "Singapore", "MAS"], sources=["MAS"])),
-    ("日本", dict(keywords=["日本", "Japan", "Japanese", "JFSA"], sources=["Japan FSA"])),
-    ("韓國", dict(keywords=["韓國", "韩国", "南韓", "Korea", "Korean", "Kakao", "KakaoBank", "Upbit", "Naver"], sources=[])),
-    ("台灣", dict(keywords=["台灣", "臺灣", "Taiwan", "金管會", "央行總裁"], sources=["金管會"])),
-    ("加拿大", dict(keywords=["加拿大", "Canada", "Canadian"], sources=[])),
-]
+import taxonomy
+from tagging import matches
+
+# ── 國家：規則在 taxonomy.yaml 的 jurisdiction_rules（新聞標記也用同一份），依那裡的順序顯示 ──
+_TAX = taxonomy.load_taxonomy()
+COUNTRIES = [(name, dict(keywords=r["keywords"], sources=r.get("sources") or []))
+             for name, r in _TAX["jurisdiction_rules"].items()]
 
 # 只在標題裡算數的泛稱（內文出現不代表事件發生在該國）
-BODY_AMBIGUOUS = {"US", "U.S.", "American", "Treasury", "Fed", "Congress", "Europe", "European", "EU",
-                  "UK", "U.K.", "British", "Korean", "Japanese", "Canadian", "Visa", "Mastercard", "Circle"}
+BODY_AMBIGUOUS = set(_TAX["title_only"])
 
 # ── 議題：一則筆記可同時屬於多條 ──
 TRACKS = [
@@ -72,18 +54,6 @@ STATUS_RULES = [
 ]
 
 
-def _match(kw: str, text: str, low: str) -> bool:
-    """ASCII 關鍵詞用單字邊界；全大寫縮寫（US、EU、SEC…）區分大小寫，避免撞到一般英文字。
-    尾端 * 表示字根。CJK 用子字串。"""
-    stem = kw.endswith("*")
-    k = kw[:-1] if stem else kw
-    if not re.fullmatch(r"[A-Za-z0-9 .\-]+", k):
-        return k in text
-    right = "" if stem else r"(?![A-Za-z0-9])"
-    if k.isupper() or re.fullmatch(r"[A-Z](\.[A-Z])+\.?", k):
-        return re.search(rf"(?<![A-Za-z0-9]){re.escape(k)}{right}", text) is not None
-    return re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}{right}", low) is not None
-
 
 def _text_of(note, body_chars=400):
     """比對用的文字：標題＋內文開頭（跳過 frontmatter 與段落標題）。"""
@@ -104,13 +74,13 @@ def countries_of(note):
     if by_src:
         return by_src
     title = note["title"]
-    by_title = [c for c, cfg in COUNTRIES if any(_match(k, title, title.lower()) for k in cfg["keywords"])]
+    by_title = [c for c, cfg in COUNTRIES if any(matches(k, title) for k in cfg["keywords"])]
     if by_title:
         return by_title
     # 內文只認機構與中文國名；US、Europe 這類泛稱在內文裡太常順帶出現（例：「美元」「US dollar」）
     text = _text_of(note, 300)
     return [c for c, cfg in COUNTRIES
-            if any(_match(k, text, text.lower()) for k in cfg["keywords"] if k not in BODY_AMBIGUOUS)]
+            if any(matches(k, text) for k in cfg["keywords"] if k not in BODY_AMBIGUOUS)]
 
 
 def tracks_of(note):
@@ -126,8 +96,7 @@ def tracks_of(note):
         manual = [manual] if isinstance(manual, str) else list(manual)
         return [t for t in names if t in manual]
     text = note["title"] if note["folder"] == "40-regulations" else _text_of(note)
-    low = text.lower()
-    out = [t for t, kws in TRACKS if any(_match(k, text, low) for k in kws)]
+    out = [t for t, kws in TRACKS if any(matches(k, text) for k in kws)]
     if note["folder"] == "40-regulations":
         topics = set(note.get("topics") or [])
         if "穩定幣" in topics and "穩定幣" not in out:
```

- [ ] **Step 5：跑測試並比對各國進度頁**

```bash
PYTHONUTF8=1 python -m pytest -q
PYTHONUTF8=1 python scripts/build_site.py >/dev/null
diff <(sed 's/<[^>]*>/\n/g' /tmp/tracker-before.html | grep -v '^\s*$') <(sed 's/<[^>]*>/\n/g' site/tracker.html | grep -v '^\s*$')
```

Expected：測試全過。diff 只多出簡體中文新聞被正確歸類的列（撰寫計畫時實測只多一則：「香港立法会议员邱达根…」出現在香港）。如果有國家或議題消失，停下來檢查 taxonomy 的轄區規則是否抄漏。

- [ ] **Step 6：feeds.yaml 換成 WIP 分支的來源清單，拿掉已搬走的評分設定**

```bash
git checkout origin/wip/news-sources-expansion -- scripts/feeds.yaml
```

打開 `scripts/feeds.yaml`，刪除從 `# 主題權重：命中越多、權重越高的詞，score 越高` 那一行到檔案結尾的全部內容（`weights`、`noise`、`dedup_threshold` 已在 taxonomy）。檔案最後應該是 `GN 區塊鏈金融（繁中）` 那一項。確認：

```bash
python -c "import yaml;d=yaml.safe_load(open('scripts/feeds.yaml',encoding='utf-8'));print({k:len(v) for k,v in d.items()})"
```

Expected: `{'primary': 21, 'trade': 26, 'aggregator': 11}`

- [ ] **Step 7：Commit**

```bash
git add scripts/tracker.py scripts/feeds.yaml tests/test_tracker.py
git commit -m "refactor: 各國判斷規則改讀 taxonomy；feeds.yaml 併入重點機構與 Google News 來源"
```

---

### Task 3：網址正規化與摘要清理

**Files:**
- Create: `scripts/news_utils.py`
- Test: `tests/test_news_utils.py`

**Interfaces:**
- Produces: `normalize_url(url) -> str`、`clean_summary(raw, title="") -> str`（最多 600 字）、`detect_lang(title) -> "zh"|"en"`、`utc_iso(datetime) -> "YYYY-MM-DDTHH:MM:SSZ"`。

- [ ] **Step 1：寫失敗的測試** `tests/test_news_utils.py`

```python
import datetime as dt

from news_utils import normalize_url, clean_summary, detect_lang, utc_iso


def test_normalize_url():
    assert (normalize_url("HTTPS://Example.COM/a/b/?utm_source=x&id=3&fbclid=y&gclid=z#frag")
            == "https://example.com/a/b?id=3")
    assert normalize_url("https://example.com/") == "https://example.com"
    assert normalize_url("https://example.com/p?ref=tw&reference=1") == "https://example.com/p?reference=1"
    # 同一篇的兩種寫法要正規化成同一個
    assert normalize_url("https://a.com/x/?utm_medium=rss") == normalize_url("https://A.com/x")


def test_clean_summary():
    raw = "&lt;p&gt;Banks <b>tokenize</b> deposits.&lt;/p&gt; The post X appeared first on Y."
    assert clean_summary(raw) == "Banks tokenize deposits."
    assert clean_summary("Big news here - Reuters", "Big news here") == ""   # 只是重述標題
    long = ("第一句話很長。" * 120)
    out = clean_summary(long)
    assert len(out) <= 600 and out.endswith("。")


def test_detect_lang_and_utc_iso():
    assert detect_lang("香港穩定幣條例") == "zh"
    assert detect_lang("SEC approves") == "en"
    tpe = dt.timezone(dt.timedelta(hours=8))
    assert utc_iso(dt.datetime(2026, 9, 25, 7, 0, tzinfo=tpe)) == "2026-09-24T23:00:00Z"
```

- [ ] **Step 2：確認失敗**

Run: `PYTHONUTF8=1 python -m pytest tests/test_news_utils.py -q`
Expected: FAIL，`No module named 'news_utils'`

- [ ] **Step 3：建立 `scripts/news_utils.py`**（`clean_summary` 搬自 WIP 分支）

```python
"""新聞文字與網址的小工具：網址正規化、RSS 摘要清理、語言判斷。只用標準庫。"""
import datetime as dt
import html
import re
import urllib.parse

TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|ref)$", re.I)
CJK = re.compile(r"[一-鿿]")

# 摘要尾巴的 RSS 樣板句
BOILERPLATE = [r"The post .{0,200}? appeared first on .{0,80}?\.?$", r"\[?…\]?\s*$",
               r"(Continue|Read) (reading|more).{0,40}$", r"本文.{0,20}(首發|原文)於.{0,40}$"]
SUMMARY_MAX = 600


def normalize_url(url: str) -> str:
    """去重用的網址：小寫 scheme 與 host、去追蹤參數、去 fragment 與結尾斜線。"""
    p = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"),
                                    urllib.parse.urlencode(query), ""))


def clean_summary(raw: str, title: str = "") -> str:
    """RSS 摘要轉純文字：解實體、去標籤、去樣板句，在句尾截斷。摘要只是標題重述時回傳空字串。"""
    # 先解碼再去標籤：反過來的話，編碼過的 &lt;script&gt; 會在解碼後變成真的標籤
    t = re.sub(r"<[^>]+>", " ", html.unescape(raw or ""))
    t = re.sub(r"\s+", " ", t).strip()
    for pat in BOILERPLATE:
        t = re.sub(pat, "", t, flags=re.I).strip()
    if title:
        tl = re.sub(r"\W+", "", title.lower())
        if not t or re.sub(r"\W+", "", t.lower()).startswith(tl[: max(20, len(tl) - 5)]):
            return ""
    if len(t) > SUMMARY_MAX:
        cut = t[:SUMMARY_MAX]
        end = max(cut.rfind(x) for x in ("。", "！", "？", ". ", "! ", "? "))
        t = cut[: end + 1] if end > SUMMARY_MAX // 2 else cut.rstrip() + "…"
    return t


def detect_lang(title: str) -> str:
    return "zh" if CJK.search(title) else "en"


def utc_iso(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 4：確認通過**

Run: `PYTHONUTF8=1 python -m pytest tests/test_news_utils.py -q`
Expected: 3 passed

- [ ] **Step 5：Commit**

```bash
git add scripts/news_utils.py tests/test_news_utils.py
git commit -m "feat: 網址正規化、RSS 摘要清理、語言判斷"
```

---

### Task 4：事件分組與門檻校準

**Files:**
- Create: `scripts/clustering.py`、`scripts/calibrate_clusters.py`、`tests/fixtures/cluster_calibration.yaml`、`docs/decisions.md`
- Test: `tests/test_clustering.py`

**Interfaces:**
- Consumes: `taxonomy.yaml` 的 `clustering`（Task 1）。
- Produces: `load_embedder(model_name) -> embed | None`，`embed(texts)` 回傳已正規化向量；`assign_clusters(new_items, existing, embed, threshold, jaccard_threshold) -> list[int | "new:<n>"]`（`new_items` 需有 `title`、`score`，可有 `title_zh`；`existing` 是 `/api/news/recent` 的 items）；`apply_limit(items, refs, daily_top) -> list[(item, ref)]`。

- [ ] **Step 1：建立校準資料** `tests/fixtures/cluster_calibration.yaml`（標題取自 main 上的自動卡）

```yaml
# 事件分組門檻的校準資料（spec §6.2），標題取自 main 上的自動卡。
# same：每組內的標題必須合併成同一事件。
# different：清單內每則各自是不同事件，彼此不能合併，也不能併進 same 的任何一組。
same:
  sofi_mastercard:
    - Mastercard and SoFi Team on Stablecoin Settlement to Cards
    - SoFi begins stablecoin settlement on Mastercard network for program expected to exceed $25 billion in annualized volume
    - SoFi tie-up shows stablecoins can provide alternative blockchain settlement rail
  canada_big_six:
    - Canada's 'Big Six' banks to launch interbank tokenized deposit initiative
    - Canada’s six largest banks explore tokenized Canadian dollar deposits
    - Canada’s big six banks explore tokenized deposit system to modernize payments
  a16z_rwa_perps:
    - a16z：RWA永续合约交易额8月同比激增44倍达1173亿美元，链上交易占比升至86%
    - a16z：CEX RWA 永续交易总量份额约 14% ，链上交易则占 86%
  cftc_mass_tokenization:
    - CFTC Chairman Selig says markets must prepare for ‘mass tokenization’
    - CFTC 主席：大規模代幣化來襲，金融市場未來十年變化超越過去總和
different:
  - CFTC Staff Releases Updates to FAQs Concerning Registrants and Registered Entity Activities Relating to Crypto Assets and Blockchain Technologies
  - EU's financial regulator to make AI and tokenization a supervisory priority in 2027
  - UK’s largest banks complete world’s first interbank transactions using tokenized deposits
  - HIFI raises $37M to expand stablecoin payments, tokenized markets
  - The Clearing House taps Quant for tokenised deposit network
  - KB Securities, Securitize and Optimism Sign Exploratory Korea Tokenization MOU
  - SEC’s Peirce Urges Zero-Knowledge Proofs to Reduce KYC Data Collection
  - Bitwise推出PPLUS RWA Vault，采用杠杆策略目标净收益率超10%
  - CryptoRank：第三季度永续合约DEX的RWA交易量达3650亿美元，环比增 32%
  - RockawayX投入1.5亿美元布局RWA信贷，押注链上收益市场
```

- [ ] **Step 2：寫失敗的測試** `tests/test_clustering.py`

```python
import numpy as np

from clustering import assign_clusters, apply_limit, title_tokens, jaccard


def fake_embed(table):
    """測試用：以標題查表回傳正規化向量。"""
    def embed(texts):
        v = np.asarray([table[t] for t in texts], dtype=float)
        return v / np.linalg.norm(v, axis=1, keepdims=True)
    return embed


def it(title, score):
    return {"title": title, "score": score}


def test_joins_existing_cluster_and_opens_new_ones():
    table = {"A1": [1, 0, 0], "A2": [0.95, 0.05, 0], "B": [0, 1, 0], "C": [0, 0, 1]}
    existing = [{"title": "A1", "cluster_id": 7}, {"title": "old", "cluster_id": None}]
    table["old"] = [1, 0, 0]
    refs = assign_clusters([it("A2", 5), it("B", 9), it("C", 3)], existing, fake_embed(table), 0.75, 0.35)
    assert refs == [7, "new:1", "new:2"]            # B 分數最高，先開組


def test_new_items_merge_with_each_other():
    table = {"x": [1, 0], "y": [0.9, 0.1], "z": [0, 1]}
    refs = assign_clusters([it("x", 3), it("y", 8), it("z", 1)], [], fake_embed(table), 0.75, 0.35)
    assert refs[0] == refs[1] == "new:1" and refs[2] == "new:2"


def test_jaccard_fallback_when_no_model():
    items = [it("Canada big six banks tokenized deposits", 5), it("Canada's big six banks explore tokenized deposits", 4)]
    refs = assign_clusters(items, [], None, 0.75, 0.35)
    assert refs == ["new:1", "new:1"]
    assert jaccard(title_tokens(items[0]["title"]), title_tokens(items[1]["title"])) >= 0.35


def test_empty_input():
    assert assign_clusters([], [{"title": "a", "cluster_id": 1}], None, 0.75, 0.35) == []


def test_apply_limit_keeps_existing_and_top_new_groups():
    items = [it("a", 9), it("b", 2), it("c", 5), it("d", 1)]
    refs = ["new:1", "new:2", "new:2", 42]
    kept = apply_limit(items, refs, daily_top=1)
    assert [r for _, r in kept] == ["new:1", 42]


def test_calibration_fixture_shape():
    from calibrate_clusters import load_groups
    groups = load_groups()
    assert [len(g) for g in groups[:4]] == [3, 3, 2, 2]
    assert len(groups) == 14 and all(len(g) == 1 for g in groups[4:])


def test_grid_counts_split_and_wrong_pairs():
    from calibrate_clusters import grid
    table = {"a1": [1, 0, 0], "a2": [0.8, 0.6, 0], "b": [0.6, 0.8, 0], "c": [0, 0, 1]}
    rows = dict((thr, (split, wrong)) for thr, split, wrong in grid([["a1", "a2"], ["b"], ["c"]], fake_embed(table), [0.7, 0.9, 0.99]))
    assert rows[0.99] == (1, 0)      # 門檻太高：a1、a2 沒合併
    assert rows[0.7] == (0, 2)       # a2、b 太像（0.96），b 被併進 a 組
```

- [ ] **Step 3：確認失敗**

Run: `PYTHONUTF8=1 python -m pytest tests/test_clustering.py -q`
Expected: FAIL，`No module named 'clustering'`

- [ ] **Step 4：建立 `scripts/clustering.py`**

```python
"""事件分組：新報導跟近期報導比語意相似度，夠像就併進同一組，否則開新組。

模型與 numpy 延後到真的要用時才載入：測試與 Cloudflare build 不需要它們。
"""
import re
import sys
import unicodedata

# ── 標題 Jaccard（模型載入失敗時的備援；舊版 fetch_news.py 的去重方法）──
TITLE_NOISE = ["news", "breaking", "exclusive", "update", "report", "報導", "快訊",
               "獨家", "最新", "消息", "新聞"]
STOPWORDS = {"a", "an", "the", "to", "of", "for", "in", "on", "and", "or", "with", "as",
             "by", "at", "from", "is", "are", "be", "its", "it", "s", "into", "over",
             "after", "via", "new", "says", "said", "will", "could", "may", "than"}
STEM_LEN = 5


def title_tokens(title: str) -> frozenset:
    """英文取前 5 字母當詞幹、中文取 2-gram。"""
    t = unicodedata.normalize("NFKC", title).lower().replace("’", "'")
    for w in TITLE_NOISE:
        t = t.replace(w, " ")
    t = re.sub(r"'s\b", " ", t)
    words = {w[:STEM_LEN] for w in re.findall(r"[a-z0-9]+", t) if w not in STOPWORDS}
    grams = set()
    for run in re.findall(r"[一-鿿]+", t):
        grams |= {run[i:i + 2] for i in range(len(run) - 1)} or {run}
    return frozenset(words | grams)


def jaccard(a, b) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def cluster_text(item: dict) -> str:
    return f"{item['title']} {item.get('title_zh') or ''}".strip()


def load_embedder(model_name: str):
    """回傳 embed(texts) -> 已正規化的向量陣列；載入失敗回傳 None（呼叫端退回 Jaccard）。"""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
    except Exception as e:  # 套件沒裝、下載失敗、快取壞掉都一樣處理
        print(f"  ! 分組模型載入失敗，退回標題 Jaccard：{e}", file=sys.stderr)
        return None
    prefix = "query: " if "e5" in model_name else ""   # e5 系列要求輸入加前綴

    def embed(texts):
        return model.encode([prefix + t for t in texts], normalize_embeddings=True)
    return embed


def _similarities(new_texts, pool_texts, embed):
    """回傳 (新×既有, 新×新) 兩個相似度矩陣。"""
    if embed is None:
        nt = [title_tokens(t) for t in new_texts]
        pt = [title_tokens(t) for t in pool_texts]
        return [[jaccard(a, b) for b in pt] for a in nt], [[jaccard(a, b) for b in nt] for a in nt]
    import numpy as np
    n = np.asarray(embed(new_texts))
    p = np.asarray(embed(pool_texts)) if pool_texts else np.zeros((0, n.shape[1]))
    return n @ p.T, n @ n.T


def assign_clusters(new_items, existing, embed, threshold, jaccard_threshold):
    """回傳與 new_items 對齊的 cluster_ref：既有 cluster_id（int）或本次暫時代號 'new:<n>'。

    new_items 依分數高到低處理：高分的先開組，低分的才併進來。
    existing 是 /api/news/recent 的結果；cluster_id 為空的略過。
    embed 為 None 時用標題 Jaccard 與 jaccard_threshold。
    """
    if not new_items:
        return []
    pool = [e for e in existing if e.get("cluster_id")]
    s_pool, s_new = _similarities([cluster_text(i) for i in new_items],
                                  [cluster_text(e) for e in pool], embed)
    thr = threshold if embed is not None else jaccard_threshold
    refs, done, n = [None] * len(new_items), [], 0
    for i in sorted(range(len(new_items)), key=lambda k: -new_items[k]["score"]):
        best, best_ref = -1.0, None
        for p, e in enumerate(pool):
            if s_pool[i][p] > best:
                best, best_ref = float(s_pool[i][p]), e["cluster_id"]
        for j in done:
            if s_new[i][j] > best:
                best, best_ref = float(s_new[i][j]), refs[j]
        if best >= thr:
            refs[i] = best_ref
        else:
            n += 1
            refs[i] = f"new:{n}"
        done.append(i)
    return refs


def apply_limit(items, refs, daily_top):
    """併入既有分組的全留；新分組依組內最高分排序，只留前 daily_top 組。回傳 [(item, ref)]。"""
    best = {}
    for it, r in zip(items, refs):
        if isinstance(r, str):
            best[r] = max(best.get(r, it["score"]), it["score"])
    keep = set(sorted(best, key=lambda r: -best[r])[:daily_top])
    return [(it, r) for it, r in zip(items, refs) if not isinstance(r, str) or r in keep]
```

- [ ] **Step 5：建立 `scripts/calibrate_clusters.py`**

```python
#!/usr/bin/env python3
"""事件分組門檻校準（spec §6.2）。讀 tests/fixtures/cluster_calibration.yaml，
用實際的分組邏輯（assign_clusters）掃過一串門檻，每個門檻印出：

- 漏併：必須合併的兩則被分到不同組的對數
- 誤併：不同事件被併進同一組的對數

誤併比漏併糟（一個事件會藏住另一個），所以先挑誤併最少、再挑漏併最少的門檻。

用法：python scripts/calibrate_clusters.py [--model <名稱>]
相依：sentence-transformers（見 requirements-news.txt）
"""
import argparse
import sys
from pathlib import Path

import yaml

import clustering
from taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "cluster_calibration.yaml"
THRESHOLDS = [round(0.40 + 0.02 * k, 2) for k in range(28)]     # 0.40 … 0.94


def load_groups(path=FIXTURE):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return list(data["same"].values()) + [[t] for t in data["different"]]


def grid(groups, embed, thresholds):
    """回傳 [(門檻, 漏併對數, 誤併對數)]。embed 只呼叫一次。"""
    texts = [t for g in groups for t in g]
    gid = [k for k, g in enumerate(groups) for _ in g]
    vectors = dict(zip(texts, embed(texts)))
    cached = lambda ts: [vectors[t] for t in ts]
    items = [{"title": t, "score": 0} for t in texts]
    out = []
    for thr in thresholds:
        refs = clustering.assign_clusters(items, [], cached, thr, 0)
        split = wrong = 0
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                same, together = gid[i] == gid[j], refs[i] == refs[j]
                split += same and not together
                wrong += together and not same
        out.append((thr, split, wrong))
    return out


def main():
    tax = load_taxonomy()
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=tax["clustering"]["model"])
    a = ap.parse_args()
    embed = clustering.load_embedder(a.model)
    if embed is None:
        sys.exit("模型載入失敗，無法校準")
    groups = load_groups()
    must = sum(len(g) * (len(g) - 1) // 2 for g in groups)
    rows = grid(groups, embed, THRESHOLDS)
    print(f"模型：{a.model}（必須合併的共 {must} 對）")
    for thr, split, wrong in rows:
        print(f"  {thr:.2f}  漏併 {split:>2}  誤併 {wrong:>2}")
    best = min(rows, key=lambda r: (r[2], r[1]))
    ties = [r[0] for r in rows if (r[2], r[1]) == (best[2], best[1])]
    print(f"最佳：誤併 {best[2]}、漏併 {best[1]}，門檻 {ties[0]:.2f}–{ties[-1]:.2f}，建議取中間 {ties[len(ties) // 2]:.2f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6：確認測試通過**

Run: `PYTHONUTF8=1 python -m pytest tests/test_clustering.py -q`
Expected: 7 passed

- [ ] **Step 7：記錄校準結果** `docs/decisions.md`

撰寫計畫時已用真實模型跑過校準（2026-09-25），結果如下，直接寫入。只有換模型或 fixture 增加案例時才需要重跑，重跑方式：

```bash
python -m venv C:/bvv
C:/bvv/Scripts/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
C:/bvv/Scripts/python -m pip install sentence-transformers pyyaml numpy
PYTHONUTF8=1 C:/bvv/Scripts/python scripts/calibrate_clusters.py --model sentence-transformers/LaBSE
```

Expected：最後一行是 `最佳：誤併 0、漏併 3，門檻 0.66–0.68`。

```markdown
# 決策紀錄

## 2026-09-25 事件分組模型與門檻（spec §6.2）

資料：`tests/fixtures/cluster_calibration.yaml`，4 組必須合併（共 8 對）、10 則彼此不同的事件。
方法：`python scripts/calibrate_clusters.py --model <模型>`，用實際分組邏輯掃 0.40–0.94 的門檻，
數「漏併」（該合併卻分開的對數）與「誤併」（不同事件被併在一起的對數）。誤併優先壓到 0。

| 模型 | 最佳門檻 | 漏併 | 誤併 | 備註 |
|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2（spec 原訂） | 0.74–0.76 | 5 | 0 | 0.68 時漏併 3、誤併 2 |
| multilingual-e5-small | 0.92 | 3 | 2 | 所有配對都在 0.8 以上，分不開 |
| paraphrase-multilingual-mpnet-base-v2 | 0.72–0.74 | 3 | 0 | |
| **LaBSE** | **0.66–0.68** | **3** | **0** | 採用，門檻取 0.67 |

**結論**：採用 `sentence-transformers/LaBSE`，門檻 0.67。只看標題時，沒有任何模型能做到零錯誤。
LaBSE 在不誤併的前提下漏併最少。

**最難的案例**
- 該合併卻合不起來：CFTC 主席談「大規模代幣化」的中英文報導、SoFi 第三篇評論文。
  上線後既有報導會帶 AI 翻的 `title_zh` 一起比對，跨語言的情況應該會改善。
- 容易誤併：a16z 與 CryptoRank 兩則 RWA 永續合約交易量數據；英國與加拿大銀行的代幣化存款新聞。

**何時重跑**：換模型、fixture 增加案例，或上線兩週後發現重複分組明顯偏多或偏少。

## AI 摘要抽查（spec §12）

上線後第一次每日執行完成時，抽 10 則 `summary_by='ai'` 的新聞，人工比對原文，確認沒有編造數字或機構。
```

- [ ] **Step 8：Commit**

```bash
git add scripts/clustering.py scripts/calibrate_clusters.py tests/test_clustering.py tests/fixtures/cluster_calibration.yaml docs/decisions.md
git commit -m "feat: 事件語意分組；校準後採用 LaBSE、門檻 0.67"
```

---

### Task 5：D1 migration、`/api/news/recent`、測試用 D1

**Files:**
- Create: `db/migrations/0001_news.sql`、`functions/api/news/recent.js`、`tests/js/fake_d1.js`
- Modify: `functions/_lib.js`、`functions/api/comments/[id].js`
- Test: `tests/js/recent.test.js`

**Interfaces:**
- Produces: `_lib.js` 的 `safeEqual(a, b)`、`checkToken(request, expected, header) -> Response | null`、`dbUnavailable() -> Response`。
- Produces: `GET /api/news/recent?days=<1–400>&page=<0…>`，header `x-ingest-token`，回傳 `{items: [{id, url_canonical, title, title_zh, cluster_id, published_at}], next_page: int | null}`，每頁 500 筆。
- Produces: `tests/js/fake_d1.js` 的 `fakeD1()`（套好 migration 的記憶體 D1，`.raw` 是底層 `DatabaseSync`）與 `brokenD1()`。

- [ ] **Step 1：建立 `db/migrations/0001_news.sql`**（spec §5，但不含留言表；全部 `IF NOT EXISTS`，可重跑）

```sql
-- 階段 2：新聞資料表（spec §5）。可重跑：全部 IF NOT EXISTS。
-- 留言表 comments 不在這裡動，階段 3 才改成 target 欄位。
-- 執行：npx wrangler d1 execute blockchain-vault-comments --remote --file db/migrations/0001_news.sql

CREATE TABLE IF NOT EXISTS clusters (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title_zh     TEXT,
  lead_item_id INTEGER,
  first_seen   TEXT NOT NULL,
  last_seen    TEXT NOT NULL,
  item_count   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS news_items (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  url_canonical  TEXT NOT NULL UNIQUE,
  url_original   TEXT NOT NULL,
  url_resolved   INTEGER NOT NULL DEFAULT 1,
  title          TEXT NOT NULL,
  title_zh       TEXT,
  outlet         TEXT NOT NULL,
  source_feed    TEXT NOT NULL,
  tier           TEXT NOT NULL CHECK (tier IN ('primary','trade','aggregator','manual')),
  lang           TEXT NOT NULL,
  published_at   TEXT NOT NULL,
  fetched_at     TEXT NOT NULL,
  summary        TEXT,
  summary_by     TEXT CHECK (summary_by IN ('ai','rss') OR summary_by IS NULL),
  score          INTEGER NOT NULL,
  cluster_id     INTEGER REFERENCES clusters(id),
  status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','hidden')),
  added_by       TEXT NOT NULL CHECK (added_by IN ('bot','manual','import')),
  needs_annotate INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_news_pub     ON news_items (published_at);
CREATE INDEX IF NOT EXISTS idx_news_cluster ON news_items (cluster_id);

CREATE TABLE IF NOT EXISTS news_tags (
  news_id INTEGER NOT NULL REFERENCES news_items(id),
  kind    TEXT NOT NULL CHECK (kind IN ('topic','watch','note','jurisdiction')),
  key     TEXT NOT NULL,
  PRIMARY KEY (news_id, kind, key)
);
CREATE INDEX IF NOT EXISTS idx_tags_key ON news_tags (kind, key);

CREATE VIRTUAL TABLE IF NOT EXISTS news_fts USING fts5 (
  title, title_zh, summary, content='news_items', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS news_fts_ai AFTER INSERT ON news_items BEGIN
  INSERT INTO news_fts (rowid, title, title_zh, summary) VALUES (new.id, new.title, new.title_zh, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS news_fts_ad AFTER DELETE ON news_items BEGIN
  INSERT INTO news_fts (news_fts, rowid, title, title_zh, summary) VALUES ('delete', old.id, old.title, old.title_zh, old.summary);
END;
CREATE TRIGGER IF NOT EXISTS news_fts_au AFTER UPDATE ON news_items BEGIN
  INSERT INTO news_fts (news_fts, rowid, title, title_zh, summary) VALUES ('delete', old.id, old.title, old.title_zh, old.summary);
  INSERT INTO news_fts (rowid, title, title_zh, summary) VALUES (new.id, new.title, new.title_zh, new.summary);
END;

CREATE TABLE IF NOT EXISTS ingest_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  run_id     TEXT,
  received   INTEGER,
  inserted   INTEGER,
  duplicates INTEGER,
  ai_failed  INTEGER,
  errors     TEXT
);
```

- [ ] **Step 2：建立測試用 D1** `tests/js/fake_d1.js`

```javascript
// 測試用的 D1：以 Node 內建 node:sqlite（含 FTS5）模擬 D1 的 prepare/bind/all/first/run/batch。
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";

const MIGRATION = new URL("../../db/migrations/0001_news.sql", import.meta.url);

class Stmt {
  constructor(db, sql, args = []) {
    this.db = db;
    this.sql = sql;
    this.args = args;
  }
  bind(...args) {
    return new Stmt(this.db, this.sql, args);
  }
  exec() {
    const results = this.db.prepare(this.sql).all(...this.args).map((r) => ({ ...r }));
    return { results, success: true, meta: {} };
  }
  async all() {
    return this.exec();
  }
  async first() {
    return this.exec().results[0] ?? null;
  }
  async run() {
    const r = this.db.prepare(this.sql).run(...this.args);
    return { success: true, meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
  }
}

export function fakeD1() {
  const db = new DatabaseSync(":memory:");
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(readFileSync(MIGRATION, "utf8"));
  return {
    raw: db,
    prepare: (sql) => new Stmt(db, sql),
    // D1 的 batch 是交易：任一句失敗就全部回滾
    async batch(stmts) {
      db.exec("BEGIN");
      try {
        const out = stmts.map((s) => s.exec());
        db.exec("COMMIT");
        return out;
      } catch (e) {
        db.exec("ROLLBACK");
        throw e;
      }
    },
  };
}

export const brokenD1 = () => ({
  prepare() {
    throw new Error("D1 down");
  },
  async batch() {
    throw new Error("D1 down");
  },
});
```

- [ ] **Step 3：寫失敗的測試** `tests/js/recent.test.js`

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeD1, brokenD1 } from "./fake_d1.js";
import { onRequestGet } from "../../functions/api/news/recent.js";

const TOKEN = "t0ken";

async function get(env, qs, token = TOKEN) {
  const request = new Request(`https://site/api/news/recent?${qs}`, { headers: { "x-ingest-token": token } });
  const res = await onRequestGet({ request, env });
  return { status: res.status, body: await res.json() };
}

function seed(db, n, daysAgo) {
  const pub = new Date(Date.now() - daysAgo * 86400000).toISOString();
  const ins = db.raw.prepare(`INSERT INTO news_items (url_canonical, url_original, title, outlet, source_feed, tier,
    lang, published_at, fetched_at, score, added_by) VALUES (?, ?, ?, 'o', 'f', 'trade', 'en', ?, ?, 1, 'bot')`);
  for (let i = 0; i < n; i++) ins.run(`https://ex.com/${daysAgo}/${i}`, "https://ex.com", `t${i}`, pub, pub);
}

test("需要 token", async () => {
  assert.equal((await get({ DB: fakeD1(), INGEST_TOKEN: TOKEN }, "days=14", "bad")).status, 403);
});

test("只回傳時間窗內的新聞，並分頁", async () => {
  const DB = fakeD1();
  seed(DB, 501, 1);
  seed(DB, 3, 30);
  const env = { DB, INGEST_TOKEN: TOKEN };
  const p0 = await get(env, "days=14&page=0");
  assert.equal(p0.body.items.length, 500);
  assert.equal(p0.body.next_page, 1);
  assert.deepEqual(Object.keys(p0.body.items[0]),
    ["id", "url_canonical", "title", "title_zh", "cluster_id", "published_at"]);
  const p1 = await get(env, "days=14&page=1");
  assert.deepEqual([p1.body.items.length, p1.body.next_page], [1, null]);
  assert.equal((await get(env, "days=60&page=1")).body.items.length, 4);
});

test("參數檢查與 D1 故障", async () => {
  const env = { DB: fakeD1(), INGEST_TOKEN: TOKEN };
  assert.equal((await get(env, "days=0")).status, 400);
  assert.equal((await get(env, "days=abc")).status, 400);
  assert.equal((await get(env, "page=-1")).status, 400);
  assert.equal((await get({ DB: brokenD1(), INGEST_TOKEN: TOKEN }, "days=14")).status, 503);
});
```

- [ ] **Step 4：確認失敗**

Run: `node --test "tests/js/*.test.js"`
Expected: FAIL，找不到 `functions/api/news/recent.js`。（`node:sqlite` 會印 ExperimentalWarning，可忽略。）

- [ ] **Step 5：`functions/_lib.js` 最後加上**

```javascript
// 固定時間比較，避免從回應時間推測 token
export function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// 驗證 header 裡的 token。通過回傳 null，否則回傳 403 回應。伺服器沒設 token 時一律拒絕。
export function checkToken(request, expected, header) {
  if (!expected) return json({ error: "伺服器未設定 token" }, 403);
  const given = request.headers.get(header) || "";
  return safeEqual(given, expected) ? null : json({ error: "token 不正確" }, 403);
}

// D1 查詢失敗時的統一回應（spec §8.3）
export const dbUnavailable = () => json({ error: "db_unavailable" }, 503);
```

`functions/api/comments/[id].js` 改用共用的 `safeEqual`：

```diff
@@ -1,14 +1,6 @@
 // DELETE /api/comments/<id> → 刪除一則留言。
 // 需要 header x-admin-token 與環境變數 ADMIN_TOKEN 相符（給站長清留言用）。
-import { json, getDB, noDB } from "../../_lib.js";
-
-// 固定時間比較，避免從回應時間推測 token
-function safeEqual(a, b) {
-  if (a.length !== b.length) return false;
-  let diff = 0;
-  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
-  return diff === 0;
-}
+import { json, getDB, noDB, safeEqual } from "../../_lib.js";
 
 export async function onRequestDelete({ request, params, env }) {
   const expected = env.ADMIN_TOKEN;
```

- [ ] **Step 6：建立 `functions/api/news/recent.js`**

```javascript
// GET /api/news/recent?days=14&page=0 → 近期新聞的網址與分組，給 Actions 去重與分組用。
// header x-ingest-token 要與 INGEST_TOKEN 相符。每頁 500 筆，next_page 為 null 表示沒有下一頁。
import { json, getDB, noDB, checkToken, dbUnavailable } from "../../_lib.js";

const PAGE = 500;

export async function onRequestGet({ request, env }) {
  const denied = checkToken(request, env.INGEST_TOKEN, "x-ingest-token");
  if (denied) return denied;
  const db = getDB(env);
  if (!db) return noDB();
  const q = new URL(request.url).searchParams;
  const days = Number(q.get("days") ?? 14);
  const page = Number(q.get("page") ?? 0);
  if (!Number.isInteger(days) || days < 1 || days > 400) return json({ error: "days 須為 1–400 的整數" }, 400);
  if (!Number.isInteger(page) || page < 0) return json({ error: "page 不正確" }, 400);
  const since = new Date(Date.now() - days * 86400000).toISOString();
  try {
    const { results } = await db
      .prepare(`SELECT id, url_canonical, title, title_zh, cluster_id, published_at FROM news_items
                WHERE published_at >= ? ORDER BY id LIMIT ? OFFSET ?`)
      .bind(since, PAGE + 1, page * PAGE).all();
    return json({ items: results.slice(0, PAGE), next_page: results.length > PAGE ? page + 1 : null });
  } catch (e) {
    console.error("recent failed", e);
    return dbUnavailable();
  }
}
```

- [ ] **Step 7：確認通過**

Run: `node --test "tests/js/*.test.js"`
Expected: `ℹ pass 3`、`ℹ fail 0`

- [ ] **Step 8：Commit**

```bash
git add db/migrations/0001_news.sql functions/_lib.js functions/api/comments/[id].js functions/api/news/recent.js tests/js/fake_d1.js tests/js/recent.test.js
git commit -m "feat: D1 新聞資料表 migration 與 /api/news/recent"
```

---

### Task 6：`POST /api/ingest`

**Files:**
- Create: `functions/_ingest.js`、`functions/_ai.js`、`functions/api/ingest.js`
- Test: `tests/js/ingest.test.js`

**Interfaces:**
- Consumes: `checkToken`、`dbUnavailable`、`charLen`（`_lib.js`）；migration 0001 的資料表（Task 5）。
- Produces: `POST /api/ingest`，header `x-ingest-token`，body：

```json
{
  "run_id": "字串，選填",
  "skip_ai": false,
  "items": [{
    "url_canonical": "https://…", "url_original": "https://…", "url_resolved": 1,
    "title": "…", "outlet": "Reuters", "source_feed": "GN Chainlink",
    "tier": "primary|trade|aggregator", "lang": "en", "published_at": "2026-09-25T01:00:00Z",
    "score": 7, "rss_summary": "…", "content": "…",
    "cluster_ref": 12 或 "new:1", "added_by": "bot|import",
    "tags": [{"kind": "topic|watch|note|jurisdiction", "key": "…"}]
  }]
}
```

  回傳 `{inserted, duplicates, ai_failed, errors: [{index, url, error}], clusters: {"new:<n>": 真正的 id}}`。items 須 1–10 筆，否則 400。

- [ ] **Step 1：寫失敗的測試** `tests/js/ingest.test.js`

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeD1, brokenD1 } from "./fake_d1.js";
import { onRequestPost } from "../../functions/api/ingest.js";
import { validateItem } from "../../functions/_ingest.js";
import { parseSummary } from "../../functions/_ai.js";

const TOKEN = "t0ken";
const okAI = { run: async () => ({ response: '{"title_zh": "中文標題", "summary": "穩定幣結算摘要內容。"}' }) };
const badAI = { run: async () => { throw new Error("AI down"); } };

function item(n, extra = {}) {
  return {
    url_canonical: `https://ex.com/${n}`, url_original: `https://ex.com/${n}?utm_source=x`, url_resolved: 1,
    title: `Title ${n}`, outlet: "CoinDesk", source_feed: "CoinDesk", tier: "trade", lang: "en",
    published_at: "2026-09-25T01:00:00Z", score: 5, rss_summary: "RSS summary", content: "",
    cluster_ref: "new:1", added_by: "bot", tags: [{ kind: "topic", key: "RWA" }], ...extra,
  };
}

async function post(env, body, token = TOKEN) {
  const request = new Request("https://site/api/ingest", {
    method: "POST", headers: { "x-ingest-token": token, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const res = await onRequestPost({ request, env });
  return { status: res.status, body: await res.json() };
}

const rows = (db, sql, ...a) => db.raw.prepare(sql).all(...a).map((r) => ({ ...r }));

test("token 錯誤或伺服器未設定都回 403", async () => {
  const DB = fakeD1();
  assert.equal((await post({ DB, INGEST_TOKEN: TOKEN }, { items: [item(1)] }, "wrong")).status, 403);
  assert.equal((await post({ DB }, { items: [item(1)] })).status, 403);
});

test("批次大小限制 1–10", async () => {
  const env = { DB: fakeD1(), INGEST_TOKEN: TOKEN };
  assert.equal((await post(env, { items: [] })).status, 400);
  const eleven = Array.from({ length: 11 }, (_, i) => item(i));
  assert.equal((await post(env, { items: eleven })).status, 400);
});

test("寫入新聞、AI 摘要、分組、標記、ingest_log 與 FTS", async () => {
  const DB = fakeD1();
  const r = await post({ DB, INGEST_TOKEN: TOKEN, AI: okAI },
    { run_id: "run1", items: [item(1, { score: 3 }), item(2, { score: 9 })] });
  assert.equal(r.status, 200);
  assert.deepEqual({ ...r.body, clusters: undefined },
    { inserted: 2, duplicates: 0, ai_failed: 0, errors: [], clusters: undefined });
  const cid = r.body.clusters["new:1"];
  const news = rows(DB, "SELECT title_zh, summary, summary_by, cluster_id FROM news_items ORDER BY id");
  assert.deepEqual(news[0], { title_zh: "中文標題", summary: "穩定幣結算摘要內容。", summary_by: "ai", cluster_id: cid });
  const [c] = rows(DB, "SELECT item_count, lead_item_id, first_seen FROM clusters WHERE id = ?", cid);
  assert.equal(c.item_count, 2);
  assert.equal(c.lead_item_id, 2);                       // 分數 9 的那則
  assert.equal(c.first_seen, "2026-09-25T01:00:00.000Z");
  assert.equal(rows(DB, "SELECT * FROM news_tags").length, 2);
  assert.equal(rows(DB, "SELECT run_id, received, inserted FROM ingest_log")[0].inserted, 2);
  assert.equal(rows(DB, "SELECT rowid FROM news_fts WHERE news_fts MATCH ?", "穩定幣").length, 2);
});

test("AI 失敗退回 RSS 摘要，仍然入庫", async () => {
  const DB = fakeD1();
  const r = await post({ DB, INGEST_TOKEN: TOKEN, AI: badAI }, { items: [item(1)] });
  assert.equal(r.body.inserted, 1);
  assert.equal(r.body.ai_failed, 1);
  assert.deepEqual(rows(DB, "SELECT summary, summary_by, title_zh FROM news_items")[0],
    { summary: "RSS summary", summary_by: "rss", title_zh: null });
});

test("skip_ai 不呼叫 AI；沒綁 AI 算失敗但照樣入庫", async () => {
  let called = false;
  const spyAI = { run: async () => { called = true; return {}; } };
  const r = await post({ DB: fakeD1(), INGEST_TOKEN: TOKEN, AI: spyAI }, { skip_ai: true, items: [item(1)] });
  assert.equal(called, false);
  assert.equal(r.body.ai_failed, 0);
  const r2 = await post({ DB: fakeD1(), INGEST_TOKEN: TOKEN }, { items: [item(1)] });
  assert.deepEqual([r2.body.inserted, r2.body.ai_failed], [1, 1]);
});

test("重複網址（資料庫已有、同批重複）算 duplicates；全重複時不開空分組", async () => {
  const DB = fakeD1();
  const env = { DB, INGEST_TOKEN: TOKEN, AI: okAI };
  await post(env, { items: [item(1)] });
  const r = await post(env, { items: [item(1), item(2, { cluster_ref: "new:2" }), item(2, { cluster_ref: "new:2" })] });
  assert.deepEqual([r.body.inserted, r.body.duplicates], [1, 2]);
  assert.deepEqual(Object.keys(r.body.clusters), ["new:2"]);   // new:1 全是重複，不開組
  assert.equal(rows(DB, "SELECT COUNT(*) AS n FROM clusters")[0].n, 2);
});

test("併入既有分組會更新篇數；指向不存在的分組改開新組", async () => {
  const DB = fakeD1();
  const env = { DB, INGEST_TOKEN: TOKEN, AI: okAI };
  const cid = (await post(env, { items: [item(1)] })).body.clusters["new:1"];
  await post(env, { items: [item(2, { cluster_ref: cid })] });
  assert.equal(rows(DB, "SELECT item_count FROM clusters WHERE id = ?", cid)[0].item_count, 2);
  await post(env, { items: [item(3, { cluster_ref: 999 })] });
  const [n3] = rows(DB, "SELECT cluster_id FROM news_items WHERE url_canonical = 'https://ex.com/3'");
  assert.notEqual(n3.cluster_id, 999);
  assert.equal(rows(DB, "SELECT item_count FROM clusters WHERE id = ?", n3.cluster_id)[0].item_count, 1);
});

test("單筆不合格只回報該筆，其餘照寫", async () => {
  const DB = fakeD1();
  const r = await post({ DB, INGEST_TOKEN: TOKEN, AI: okAI },
    { items: [item(1, { url_canonical: "javascript:alert(1)" }), item(2)] });
  assert.equal(r.body.inserted, 1);
  assert.deepEqual(r.body.errors, [{ index: 0, url: "javascript:alert(1)", error: "url_canonical 不正確" }]);
});

test("D1 故障回 503 db_unavailable", async () => {
  const r = await post({ DB: brokenD1(), INGEST_TOKEN: TOKEN }, { items: [item(1)] });
  assert.deepEqual([r.status, r.body.error], [503, "db_unavailable"]);
});

test("validateItem 擋下各種壞欄位", () => {
  const bad = [
    { tier: "manual" }, { lang: "EN" }, { score: 1.5 }, { published_at: "昨天" },
    { cluster_ref: "new:x" }, { cluster_ref: 0 }, { added_by: "manual" }, { url_resolved: 2 },
    { title: "  " }, { tags: [{ kind: "person", key: "x" }] }, { rss_summary: "x".repeat(2001) },
  ];
  for (const b of bad) assert.ok(validateItem(item(1, b)).error, JSON.stringify(b));
  assert.equal(validateItem(item(1)).item.published_at, "2026-09-25T01:00:00.000Z");
});

test("parseSummary 容忍 think 區塊、markdown 圍欄與物件回應", () => {
  const want = { title_zh: "標題", summary: "摘要" };
  assert.deepEqual(parseSummary('<think>想一想</think>{"title_zh":"標題","summary":"摘要"}'), want);
  assert.deepEqual(parseSummary('```json\n{"title_zh":"標題","summary":"摘要"}\n```'), want);
  assert.deepEqual(parseSummary({ title_zh: "標題", summary: "摘要" }), want);
  assert.equal(parseSummary("抱歉，我無法"), null);
  assert.equal(parseSummary('{"summary":"只有摘要"}'), null);
});
```

- [ ] **Step 2：確認失敗**

Run: `node --test "tests/js/*.test.js"`
Expected: FAIL，找不到 `functions/api/ingest.js`

- [ ] **Step 3：建立 `functions/_ingest.js`**

```javascript
// /api/ingest 的輸入驗證（純函式，可用 node --test 測）。沒有 onRequest* 匯出，Pages 不會產生路由。
import { charLen } from "./_lib.js";

export const MAX_BATCH = 10;
const TIERS = new Set(["primary", "trade", "aggregator"]);
const ADDED_BY = new Set(["bot", "import"]);
const TAG_KINDS = new Set(["topic", "watch", "note", "jurisdiction"]);
const MAX = { url: 2048, title: 500, name: 200, rss_summary: 2000, content: 3000, tag_key: 100, tags: 40 };

const isUrl = (s) => typeof s === "string" && s.length <= MAX.url && /^https?:\/\/\S+$/i.test(s);
const text = (v, max) => (typeof v === "string" && v.trim() && charLen(v.trim()) <= max ? v.trim() : null);
const optText = (v, max) => {
  if (v === undefined || v === null || v === "") return { ok: true, value: "" };
  return typeof v === "string" && charLen(v) <= max ? { ok: true, value: v.trim() } : { ok: false };
};

// 回傳 { item } 或 { error }
export function validateItem(raw) {
  if (!raw || typeof raw !== "object") return { error: "不是物件" };
  if (!isUrl(raw.url_canonical)) return { error: "url_canonical 不正確" };
  if (!isUrl(raw.url_original)) return { error: "url_original 不正確" };
  const title = text(raw.title, MAX.title);
  if (!title) return { error: "title 不正確" };
  const outlet = text(raw.outlet, MAX.name);
  if (!outlet) return { error: "outlet 不正確" };
  const source_feed = text(raw.source_feed, MAX.name);
  if (!source_feed) return { error: "source_feed 不正確" };
  if (!TIERS.has(raw.tier)) return { error: "tier 不正確" };
  if (typeof raw.lang !== "string" || !/^[a-z]{2}$/.test(raw.lang)) return { error: "lang 不正確" };
  if (typeof raw.published_at !== "string" || Number.isNaN(Date.parse(raw.published_at))) {
    return { error: "published_at 不正確" };
  }
  if (!Number.isInteger(raw.score)) return { error: "score 必須是整數" };
  if (!ADDED_BY.has(raw.added_by)) return { error: "added_by 不正確" };
  const ref = raw.cluster_ref;
  if (!(Number.isInteger(ref) && ref > 0) && !(typeof ref === "string" && /^new:\d{1,5}$/.test(ref))) {
    return { error: "cluster_ref 不正確" };
  }
  const url_resolved = raw.url_resolved === undefined ? 1 : raw.url_resolved;
  if (url_resolved !== 0 && url_resolved !== 1) return { error: "url_resolved 須為 0 或 1" };
  const rss = optText(raw.rss_summary, MAX.rss_summary);
  if (!rss.ok) return { error: "rss_summary 過長或不是字串" };
  const content = optText(raw.content, MAX.content);
  if (!content.ok) return { error: "content 過長或不是字串" };
  const tags = raw.tags ?? [];
  if (!Array.isArray(tags) || tags.length > MAX.tags) return { error: "tags 不正確" };
  for (const t of tags) {
    if (!t || !TAG_KINDS.has(t.kind) || !text(t.key, MAX.tag_key)) return { error: "tag 不正確" };
  }
  return {
    item: {
      url_canonical: raw.url_canonical, url_original: raw.url_original, url_resolved,
      title, outlet, source_feed, tier: raw.tier, lang: raw.lang,
      published_at: new Date(raw.published_at).toISOString(),
      score: raw.score, added_by: raw.added_by, cluster_ref: ref,
      rss_summary: rss.value, content: content.value,
      tags: tags.map((t) => ({ kind: t.kind, key: t.key.trim() })),
    },
  };
}
```

- [ ] **Step 4：建立 `functions/_ai.js`**

Workers AI 的 qwen3 回應格式可能是 `{response}` 或 OpenAI 式的 `{choices}`，也可能帶 `<think>` 區塊；`parseSummary()` 都要能處理，其他情況一律回 null 走 RSS 備援。

```javascript
// Workers AI 摘要。沒有 onRequest* 匯出，Pages 不會產生路由。
export const MODEL = "@cf/qwen/qwen3-30b-a3b-fp8";
const SOURCE_MAX = 1500;

const SYSTEM = [
  "你是新聞摘要助理。只根據使用者提供的原文，原文沒寫的不要補。",
  '只輸出一個 JSON 物件：{"title_zh": "…", "summary": "…"}，不要輸出其他文字。',
  "title_zh：標題的繁體中文翻譯；原標題已是中文就轉成繁體。",
  "summary：2–3 句繁體中文，保留數字、日期、機構原名；原文不足以摘要就回空字串。",
  "/no_think",
].join("\n");

export function buildMessages(item) {
  const source = (item.content || item.rss_summary || "").slice(0, SOURCE_MAX);
  return [
    { role: "system", content: SYSTEM },
    { role: "user", content: `標題：${item.title}\n媒體：${item.outlet}\n原文：\n${source}` },
  ];
}

// 模型輸出 → {title_zh, summary}；格式不對回傳 null
export function parseSummary(out) {
  if (out && typeof out === "object") out = JSON.stringify(out);
  if (typeof out !== "string") return null;
  const m = out.replace(/<think>[\s\S]*?<\/think>/g, "").match(/\{[\s\S]*\}/);
  if (!m) return null;
  let o;
  try {
    o = JSON.parse(m[0]);
  } catch {
    return null;
  }
  if (typeof o.title_zh !== "string" || typeof o.summary !== "string") return null;
  return { title_zh: o.title_zh.trim().slice(0, 300) || null, summary: o.summary.trim().slice(0, 1000) };
}

// 失敗（沒綁 AI、逾時、格式不對）一律回傳 null，由呼叫端退回 RSS 摘要
export async function summarize(ai, item) {
  if (!ai) return null;
  try {
    const r = await ai.run(MODEL, { messages: buildMessages(item), max_tokens: 600, temperature: 0.2 });
    return parseSummary(r?.response ?? r?.choices?.[0]?.message?.content);
  } catch {
    return null;
  }
}
```

- [ ] **Step 5：建立 `functions/api/ingest.js`**

寫入分兩次 `db.batch()`：先建新分組（需要拿回 id），再一次寫入新聞、標記、分組統計、`ingest_log`。第二次失敗時第一次建的分組會留下 `item_count=0`，無害（階段 3 查詢時過濾 `item_count > 0`）。

```javascript
// POST /api/ingest → GitHub Actions 送來的新聞，每批最多 10 則（spec §6.4）。
// header x-ingest-token 要與環境變數 INGEST_TOKEN 相符。
// body：{ run_id, skip_ai, items: [...] }，欄位見 functions/_ingest.js。
// 回傳：{ inserted, duplicates, ai_failed, errors: [{index, url, error}], clusters: {"new:<n>": id} }
import { json, getDB, noDB, checkToken, dbUnavailable } from "../_lib.js";
import { validateItem, MAX_BATCH } from "../_ingest.js";
import { summarize } from "../_ai.js";

// 重算分組的篇數、時間範圍與代表報導（分數最高者）
const CLUSTER_REFRESH = `UPDATE clusters SET
  item_count   = (SELECT COUNT(*) FROM news_items WHERE cluster_id = ?1),
  first_seen   = COALESCE((SELECT MIN(published_at) FROM news_items WHERE cluster_id = ?1), first_seen),
  last_seen    = COALESCE((SELECT MAX(published_at) FROM news_items WHERE cluster_id = ?1), last_seen),
  lead_item_id = (SELECT id FROM news_items WHERE cluster_id = ?1 ORDER BY score DESC, id ASC LIMIT 1),
  title_zh     = (SELECT title_zh FROM news_items WHERE cluster_id = ?1 ORDER BY score DESC, id ASC LIMIT 1)
  WHERE id = ?1`;

const INSERT_ITEM = `INSERT INTO news_items (url_canonical, url_original, url_resolved, title, title_zh, outlet,
  source_feed, tier, lang, published_at, fetched_at, summary, summary_by, score, cluster_id, added_by)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (url_canonical) DO NOTHING`;

const INSERT_TAG = `INSERT OR IGNORE INTO news_tags (news_id, kind, key)
  SELECT id, ?, ? FROM news_items WHERE url_canonical = ?`;

const placeholders = (n) => Array(n).fill("?").join(",");

export async function onRequestPost({ request, env }) {
  const denied = checkToken(request, env.INGEST_TOKEN, "x-ingest-token");
  if (denied) return denied;
  const db = getDB(env);
  if (!db) return noDB();
  let data;
  try {
    data = await request.json();
  } catch {
    return json({ error: "請送 JSON" }, 400);
  }
  const items = Array.isArray(data?.items) ? data.items : null;
  if (!items || items.length === 0 || items.length > MAX_BATCH) {
    return json({ error: `items 須為 1–${MAX_BATCH} 筆的陣列` }, 400);
  }
  const runId = typeof data.run_id === "string" ? data.run_id.slice(0, 100) : null;
  try {
    return json(await ingest(db, env.AI, items, data.skip_ai === true, runId));
  } catch (e) {
    console.error("ingest failed", e);
    return dbUnavailable();
  }
}

export async function ingest(db, ai, raw, skipAI, runId) {
  const errors = [];
  const valid = [];
  raw.forEach((r, index) => {
    const v = validateItem(r);
    if (v.error) errors.push({ index, url: typeof r?.url_canonical === "string" ? r.url_canonical : null, error: v.error });
    else valid.push(v.item);
  });

  // 網址重複：資料庫已有，或同一批前面已出現。重複不算錯誤。
  const urls = [...new Set(valid.map((i) => i.url_canonical))];
  const known = new Set();
  if (urls.length) {
    const { results } = await db
      .prepare(`SELECT url_canonical FROM news_items WHERE url_canonical IN (${placeholders(urls.length)})`)
      .bind(...urls).all();
    results.forEach((r) => known.add(r.url_canonical));
  }
  const fresh = [];
  for (const it of valid) {
    if (known.has(it.url_canonical)) continue;
    known.add(it.url_canonical);
    fresh.push(it);
  }
  const duplicates = valid.length - fresh.length;

  // 指向不存在的分組：改成開一個新組，不丟掉新聞
  const numRefs = [...new Set(fresh.map((i) => i.cluster_ref).filter(Number.isInteger))];
  if (numRefs.length) {
    const { results } = await db
      .prepare(`SELECT id FROM clusters WHERE id IN (${placeholders(numRefs.length)})`)
      .bind(...numRefs).all();
    const exists = new Set(results.map((r) => r.id));
    for (const it of fresh) {
      if (Number.isInteger(it.cluster_ref) && !exists.has(it.cluster_ref)) it.cluster_ref = `missing:${it.cluster_ref}`;
    }
  }

  // 新分組：只替真的要寫入的報導開，全是重複的就不開（避免留下空分組）
  const clusters = {};
  const newRefs = [...new Set(fresh.map((i) => i.cluster_ref).filter((r) => typeof r === "string"))];
  if (newRefs.length) {
    const now = new Date().toISOString();
    const res = await db.batch(newRefs.map(() =>
      db.prepare("INSERT INTO clusters (first_seen, last_seen, item_count) VALUES (?, ?, 0) RETURNING id").bind(now, now)));
    newRefs.forEach((ref, k) => { clusters[ref] = res[k].results[0].id; });
  }
  const clusterOf = (it) => (typeof it.cluster_ref === "string" ? clusters[it.cluster_ref] : it.cluster_ref);

  // AI 摘要平行呼叫；失敗的退回 RSS 摘要，不擋入庫
  const sums = skipAI ? fresh.map(() => null) : await Promise.all(fresh.map((it) => summarize(ai, it)));
  let aiFailed = 0;
  const fetchedAt = new Date().toISOString();
  const stmts = [];
  fresh.forEach((it, k) => {
    const s = sums[k];
    if (!skipAI && !s) aiFailed++;
    const useAI = Boolean(s && s.summary);
    const summary = useAI ? s.summary : it.rss_summary || null;
    const summaryBy = useAI ? "ai" : summary ? "rss" : null;
    stmts.push(db.prepare(INSERT_ITEM).bind(
      it.url_canonical, it.url_original, it.url_resolved, it.title, s?.title_zh ?? null, it.outlet,
      it.source_feed, it.tier, it.lang, it.published_at, fetchedAt, summary, summaryBy, it.score,
      clusterOf(it), it.added_by));
    for (const t of it.tags) stmts.push(db.prepare(INSERT_TAG).bind(t.kind, t.key, it.url_canonical));
  });
  for (const id of new Set(fresh.map(clusterOf))) stmts.push(db.prepare(CLUSTER_REFRESH).bind(id));
  stmts.push(db
    .prepare("INSERT INTO ingest_log (at, run_id, received, inserted, duplicates, ai_failed, errors) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .bind(fetchedAt, runId, raw.length, fresh.length, duplicates, aiFailed, errors.length ? JSON.stringify(errors) : null));
  await db.batch(stmts);

  const newOnly = Object.fromEntries(Object.entries(clusters).filter(([k]) => k.startsWith("new:")));
  return { inserted: fresh.length, duplicates, ai_failed: aiFailed, errors, clusters: newOnly };
}
```

- [ ] **Step 6：確認通過**

Run: `node --test "tests/js/*.test.js"`
Expected: `ℹ pass 14`、`ℹ fail 0`

- [ ] **Step 7：Commit**

```bash
git add functions/_ingest.js functions/_ai.js functions/api/ingest.js tests/js/ingest.test.js
git commit -m "feat: /api/ingest 驗證、Workers AI 摘要、分組與標記寫入 D1"
```

---

### Task 7：API client 與 `fetch_news.py` 重寫

**Files:**
- Create: `scripts/ingest_client.py`
- Rewrite: `scripts/fetch_news.py`
- Test: `tests/test_ingest_client.py`、`tests/test_fetch_news.py`

**Interfaces:**
- Consumes: `score()`（Task 1）、`tags_for()`、`note_terms()`（Task 1）、`news_utils`（Task 3）、`clustering`（Task 4）、API 合約（Task 5、6）。
- Produces: `Client(base_url, token, opener=urlopen, sleep=time.sleep)`、`.recent(days) -> list[dict]`、`.ingest(items, run_id, skip_ai=False, batch_size=10, retries=2) -> {inserted, duplicates, ai_failed, errors, failed_batches}`；`client_from_env(required: bool) -> Client | None`；`ApiError`。
- Produces: `fetch_news.prepare_payload(items, existing, tax, embed, added_by, limit=True, root=ROOT) -> list[dict]`（Task 8 用），items 需有 `title, url, url_canonical, url_resolved, outlet, source_feed, tier, lang, published_at, rss_summary, score`；`fetch_news.print_report(payload, stats, hours, method)`。

- [ ] **Step 1：寫失敗的測試**

`tests/test_ingest_client.py`：

```python
import io
import json
import urllib.error

import pytest

from ingest_client import Client, ApiError


class FakeServer:
    """記錄收到的請求，依序回傳預先設定的回應（dict 或 Exception）。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, req, timeout):
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.requests.append((req.get_method(), req.full_url, body, req.get_header("X-ingest-token")))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return io.BytesIO(json.dumps(r).encode("utf-8"))


def http_error(code):
    return urllib.error.HTTPError("https://s/api/ingest", code, "err", {}, io.BytesIO(b"boom"))


def ok(inserted=1, clusters=None):
    return {"inserted": inserted, "duplicates": 0, "ai_failed": 0, "errors": [], "clusters": clusters or {}}


def test_recent_follows_pages():
    srv = FakeServer([{"items": [{"id": 1}], "next_page": 1}, {"items": [{"id": 2}], "next_page": None}])
    c = Client("https://s/", "tok", opener=srv)
    assert c.recent(14) == [{"id": 1}, {"id": 2}]
    assert srv.requests[1][1] == "https://s/api/news/recent?days=14&page=1"
    assert srv.requests[0][3] == "tok"


def test_recent_raises_on_http_error():
    c = Client("https://s", "tok", opener=FakeServer([http_error(503)]))
    with pytest.raises(ApiError, match="503"):
        c.recent(14)


def test_new_cluster_split_across_batches_reuses_real_id():
    items = [{"url_canonical": f"u{i}", "cluster_ref": "new:1"} for i in range(3)]
    srv = FakeServer([ok(2, {"new:1": 77}), ok(1)])
    total = Client("https://s", "tok", opener=srv).ingest(items, "run", batch_size=2)
    assert [it["cluster_ref"] for it in srv.requests[1][2]["items"]] == [77]
    assert total["inserted"] == 3 and total["failed_batches"] == 0


def test_retries_then_counts_failed_batch():
    items = [{"url_canonical": "a", "cluster_ref": "new:1"}, {"url_canonical": "b", "cluster_ref": "new:2"}]
    sleeps = []
    srv = FakeServer([http_error(500), ok(1), http_error(500), http_error(500), http_error(500)])
    total = Client("https://s", "tok", opener=srv, sleep=sleeps.append).ingest(items, "run", batch_size=1, retries=2)
    assert total["inserted"] == 1
    assert total["failed_batches"] == 1
    assert sleeps == [5, 5, 10]


def test_skip_ai_flag_is_sent():
    srv = FakeServer([ok()])
    Client("https://s", "tok", opener=srv).ingest([{"url_canonical": "a", "cluster_ref": 3}], "r", skip_ai=True)
    assert srv.requests[0][2]["skip_ai"] is True
```

`tests/test_fetch_news.py`：

```python
import datetime as dt
import sys
import types

import pytest

import fetch_news
from fetch_news import parse_entry, decode_gnews, dedupe_urls, prepare_payload

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
CUTOFF = NOW - dt.timedelta(hours=36)
GN_SRC = {"name": "GN Chainlink", "query": "Chainlink", "assume_core": True}
RSS_SRC = {"name": "CoinDesk", "url": "https://coindesk.com/rss"}


def entry(**kw):
    base = {"title": "Chainlink CCIP powers tokenized fund - Reuters", "link": "https://news.google.com/rss/articles/abc",
            "summary": "", "source": {"title": "Reuters"}, "published_parsed": (2026, 9, 24, 12, 0, 0)}
    return {**base, **kw}


def test_parse_google_news_entry(tax):
    it = parse_entry(entry(), GN_SRC, "aggregator", tax["scoring"], CUTOFF, NOW)
    assert it["title"] == "Chainlink CCIP powers tokenized fund"
    assert (it["outlet"], it["source_feed"]) == ("Reuters", "GN Chainlink")
    assert it["published_at"] == "2026-09-24T12:00:00Z"
    assert it["lang"] == "en" and it["score"] > 0


def test_parse_entry_edge_cases(tax):
    sc = tax["scoring"]
    assert parse_entry(entry(link="javascript:x"), RSS_SRC, "trade", sc, CUTOFF, NOW) is None
    assert parse_entry(entry(title="  "), RSS_SRC, "trade", sc, CUTOFF, NOW) is None
    assert parse_entry(entry(published_parsed=(2026, 9, 1, 0, 0, 0)), RSS_SRC, "trade", sc, CUTOFF, NOW) is None
    no_date = parse_entry(entry(published_parsed=None), RSS_SRC, "trade", sc, CUTOFF, NOW)
    assert no_date["published_at"] == "2026-09-25T00:00:00Z"
    # 一般 RSS 不拆「 - 媒體名」，outlet 就是來源名
    assert no_date["outlet"] == "CoinDesk" and no_date["title"].endswith("- Reuters")


def _fake_decoder(monkeypatch, fn):
    mod = types.ModuleType("googlenewsdecoder")
    mod.gnewsdecoder = fn
    monkeypatch.setitem(sys.modules, "googlenewsdecoder", mod)


def test_decode_gnews_success_and_partial_failure(monkeypatch):
    items = [{"url": "https://news.google.com/rss/articles/1", "url_resolved": 1},
             {"url": "https://news.google.com/rss/articles/2", "url_resolved": 1},
             {"url": "https://coindesk.com/a", "url_resolved": 1}]
    _fake_decoder(monkeypatch, lambda urls: [{"success": True, "decoded_url": "https://reuters.com/x"},
                                             {"success": False, "message": "blocked"}])
    decode_gnews(items)
    assert [(i["url"], i["url_resolved"]) for i in items] == [
        ("https://reuters.com/x", 1), ("https://news.google.com/rss/articles/2", 0), ("https://coindesk.com/a", 1)]


def test_decode_gnews_library_crash_keeps_redirect(monkeypatch):
    def boom(urls):
        raise RuntimeError("Google changed batchexecute")
    _fake_decoder(monkeypatch, boom)
    items = [{"url": "https://news.google.com/rss/articles/1", "url_resolved": 1}]
    decode_gnews(items)
    assert items[0]["url_resolved"] == 0


def test_dedupe_urls_keeps_highest_score():
    out = dedupe_urls([{"url_canonical": "u", "score": 3, "n": 1}, {"url_canonical": "u", "score": 7, "n": 2}])
    assert [i["n"] for i in out] == [2]


def _news(title, url, score=5):
    return {"title": title, "url": url, "url_canonical": url, "url_resolved": 1, "outlet": "CoinDesk",
            "source_feed": "CoinDesk", "tier": "trade", "lang": "en", "published_at": "2026-09-24T00:00:00Z",
            "rss_summary": "", "score": score}


def test_prepare_payload_skips_known_urls_and_tags(tmp_vault, tax):
    existing = [{"url_canonical": "https://a.com/1", "title": "Canada big six banks tokenized deposits",
                 "title_zh": None, "cluster_id": 12}]
    items = [_news("Canada big six banks tokenized deposits", "https://a.com/1"),
             _news("Canada's big six banks explore tokenized deposits", "https://b.com/2"),
             _news("SEC approves stablecoin rule", "https://c.com/3", score=9)]
    payload = prepare_payload(items, existing, tax, None, "bot", root=tmp_vault)
    by_url = {p["url_canonical"]: p for p in payload}
    assert set(by_url) == {"https://b.com/2", "https://c.com/3"}
    assert by_url["https://b.com/2"]["cluster_ref"] == 12          # Jaccard 併入既有分組
    assert by_url["https://c.com/3"]["cluster_ref"] == "new:1"
    assert {"kind": "jurisdiction", "key": "美國"} in by_url["https://c.com/3"]["tags"]
    assert by_url["https://c.com/3"]["added_by"] == "bot"


def test_prepare_payload_limit(tmp_vault, tax, monkeypatch):
    monkeypatch.setitem(tax["limits"], "daily_top", 1)
    items = [_news("Alpha tokenized fund launches", "https://a.com/1", 9),
             _news("Completely different stablecoin law", "https://b.com/2", 4)]
    assert len(prepare_payload(items, [], tax, None, "bot", root=tmp_vault)) == 1
    assert len(prepare_payload(items, [], tax, None, "import", limit=False, root=tmp_vault)) == 2
```

- [ ] **Step 2：確認失敗**

Run: `PYTHONUTF8=1 python -m pytest tests/test_ingest_client.py tests/test_fetch_news.py -q`
Expected: FAIL，`No module named 'ingest_client'`、`cannot import name 'parse_entry'`

- [ ] **Step 3：建立 `scripts/ingest_client.py`**

```python
"""呼叫網站的新聞 API（/api/news/recent、/api/ingest）。只用標準庫。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request


class ApiError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url, token, opener=urllib.request.urlopen, sleep=time.sleep):
        self.base = base_url.rstrip("/")
        self.token = token
        self._open = opener
        self._sleep = sleep

    def _call(self, method, path, body=None):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "x-ingest-token": self.token, "content-type": "application/json",
            "user-agent": "blockchain-vault-news-bot"})
        try:
            with self._open(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", errors="replace")
            raise ApiError(f"{method} {path} → HTTP {e.code}：{detail}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise ApiError(f"{method} {path} 失敗：{e}") from e

    def recent(self, days):
        """近 days 天的新聞（網址、標題、分組），自動翻頁。"""
        out, page = [], 0
        while page is not None:
            r = self._call("GET", f"/api/news/recent?days={days}&page={page}")
            out += r["items"]
            page = r["next_page"]
        return out

    def ingest(self, items, run_id, skip_ai=False, batch_size=10, retries=2):
        """分批送出。回傳 {inserted, duplicates, ai_failed, errors, failed_batches}。

        同一個新分組（new:<n>）的報導排在一起；前一批回傳的真正分組 id 會套用到後面的批次，
        所以跨批的同組報導不會被開成兩組。
        """
        items = sorted(items, key=lambda it: str(it["cluster_ref"]))
        mapping = {}
        total = {"inserted": 0, "duplicates": 0, "ai_failed": 0, "errors": [], "failed_batches": 0}
        for start in range(0, len(items), batch_size):
            batch = [dict(it, cluster_ref=mapping.get(it["cluster_ref"], it["cluster_ref"]))
                     for it in items[start:start + batch_size]]
            r = None
            for attempt in range(retries + 1):
                try:
                    r = self._call("POST", "/api/ingest", {"run_id": run_id, "skip_ai": skip_ai, "items": batch})
                    break
                except ApiError as e:
                    print(f"  ! 第 {start // batch_size + 1} 批失敗（第 {attempt + 1} 次）：{e}", file=sys.stderr)
                    if attempt < retries:
                        self._sleep(5 * (attempt + 1))
            if r is None:
                total["failed_batches"] += 1
                continue
            mapping.update(r.get("clusters") or {})
            for k in ("inserted", "duplicates", "ai_failed"):
                total[k] += r[k]
            total["errors"] += r["errors"]
        return total


def client_from_env(required: bool):
    """從環境變數 SITE_URL、INGEST_TOKEN 建 Client。缺少時：required 就結束程式，否則回傳 None。"""
    base, token = os.environ.get("SITE_URL"), os.environ.get("INGEST_TOKEN")
    if base and token:
        return Client(base, token)
    if required:
        sys.exit("缺少環境變數 SITE_URL 或 INGEST_TOKEN")
    print("（沒有 SITE_URL／INGEST_TOKEN：不比對資料庫既有新聞）", file=sys.stderr)
    return None
```

- [ ] **Step 4：整個重寫 `scripts/fetch_news.py`**

舊版的事件卡寫檔、每日筆記、`--rescore`、`--top` 全部移除。`gnews_url()`、瀏覽器 UA 搬自 WIP 分支。

```python
#!/usr/bin/env python3
"""
每日新聞管線：抓取 → 評分 → 解轉址 → 正規化 → 去重 → 分組 → 取上限 → 標記 → 抓原文 → 送 /api/ingest。
新聞寫進 D1，不再寫 repo（spec §6.1）。

用法：
    python scripts/fetch_news.py --dry-run          # 只印排名、分組、來源健康度，不送出
    python scripts/fetch_news.py --hours 72         # 週一補週末

環境變數：SITE_URL、INGEST_TOKEN（正式執行必填；dry-run 有的話會拿來比對既有新聞）
相依：pip install -r requirements-news.txt
"""
import argparse
import datetime as dt
import html
import os
import socket
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import feedparser
import yaml

import clustering
from ingest_client import ApiError, client_from_env
from news_utils import clean_summary, detect_lang, normalize_url, utc_iso
from scoring import score
from tagging import note_terms, tags_for
from taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parent.parent
FEEDS = Path(__file__).parent / "feeds.yaml"
TIERS = ("primary", "trade", "aggregator")
CONTENT_MAX = 1500
# 有些站會擋 feedparser 預設 UA
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128 Safari/537.36")
GNEWS_LOCALE = {"en": "hl=en-US&gl=US&ceid=US:en", "tw": "hl=zh-TW&gl=TW&ceid=TW:zh-Hant"}
# feedparser 沒有逾時：任一來源不回應就會卡住整批
socket.setdefaulttimeout(20)


def gnews_url(query: str, lang: str, hours: int) -> str:
    """Google News 搜尋 RSS。when:Nd 限定時間窗，跟 --hours 對齊。"""
    days = max(1, -(-hours // 24))
    return (f"https://news.google.com/rss/search?q={urllib.parse.quote(f'{query} when:{days}d')}"
            f"&{GNEWS_LOCALE.get(lang, GNEWS_LOCALE['en'])}")


def parse_entry(e, src: dict, tier: str, sc: dict, cutoff: dt.datetime, now: dt.datetime):
    """一則 RSS 項目 → 新聞 dict；網址或標題不合格、或早於 cutoff 就回傳 None。"""
    link = (e.get("link") or "").strip()
    title = html.unescape((e.get("title") or "").strip())
    if not link.startswith(("http://", "https://")) or not title:
        return None
    st = e.get("published_parsed") or e.get("updated_parsed")
    when = dt.datetime(*st[:6], tzinfo=dt.timezone.utc) if st else now
    if when < cutoff:
        return None
    outlet = src["name"]
    if "query" in src:
        # Google News 標題結尾是「 - 媒體名」，拿掉才能跟其他來源比對；outlet 記真正的媒體
        real = (e.get("source") or {}).get("title") or ""
        if real and title.endswith(f" - {real}"):
            title = title[: -len(real) - 3].strip()
        outlet = real or src["name"]
    summary = clean_summary(e.get("summary", ""), title)
    s, hits = score(title, summary, tier, sc, src.get("assume_core", False))
    return {"title": title, "url": link, "url_resolved": 1, "outlet": outlet,
            "source_feed": src["name"], "tier": tier, "lang": detect_lang(title),
            "published_at": utc_iso(when), "rss_summary": summary, "score": s, "hits": hits}


def collect(hours: int, cfg: dict, sc: dict):
    """回傳 (新聞清單, 來源健康度 {名稱: (feed 總則數, 時間窗內則數, 錯誤)})。單一來源失敗就略過。"""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=hours)
    items, stats = [], {}
    for tier in TIERS:
        for src in cfg.get(tier) or []:
            t0 = time.monotonic()
            url = gnews_url(src["query"], src.get("lang", "en"), hours) if "query" in src else src["url"]
            try:
                fp = feedparser.parse(url, agent=UA)
            except Exception as e:
                stats[src["name"]] = (0, 0, str(e))
                continue
            err = f"HTTP {fp.get('status')}" if (fp.get("status") or 0) >= 400 else ""
            if not fp.entries and fp.get("bozo"):
                err = err or f"解析失敗：{fp.get('bozo_exception')}"
            got = [x for x in (parse_entry(e, src, tier, sc, cutoff, now) for e in fp.entries) if x]
            items += got
            secs = time.monotonic() - t0
            if secs > 10:
                err = (err + " " if err else "") + f"慢 {secs:.0f}s"
            stats[src["name"]] = (len(fp.entries), len(got), err)
    return items, stats


def decode_gnews(items):
    """Google News 轉址批次解碼。失敗就保留轉址並標 url_resolved=0。"""
    targets = [it for it in items if urllib.parse.urlsplit(it["url"]).netloc.endswith("news.google.com")]
    if not targets:
        return
    for it in targets:
        it["url_resolved"] = 0
    try:
        from googlenewsdecoder import gnewsdecoder
        results = gnewsdecoder([it["url"] for it in targets])
    except Exception as e:
        print(f"  ! Google News 轉址解碼失敗，保留轉址：{e}", file=sys.stderr)
        return
    for it, r in zip(targets, results):
        if r.get("success") and r.get("decoded_url"):
            it["url"] = r["decoded_url"]
            it["url_resolved"] = 1


def dedupe_urls(items):
    """同一網址只留分數最高的一則。"""
    best = {}
    for it in items:
        k = it["url_canonical"]
        if k not in best or it["score"] > best[k]["score"]:
            best[k] = it
    return list(best.values())


def to_payload(it: dict, ref, tags: list, added_by: str) -> dict:
    return {"url_canonical": it["url_canonical"], "url_original": it["url"], "url_resolved": it["url_resolved"],
            "title": it["title"], "outlet": it["outlet"], "source_feed": it["source_feed"], "tier": it["tier"],
            "lang": it["lang"], "published_at": it["published_at"], "score": it["score"],
            "rss_summary": it["rss_summary"], "cluster_ref": ref, "added_by": added_by, "tags": tags}


def prepare_payload(items, existing, tax, embed, added_by, limit=True, root=ROOT):
    """去掉資料庫已有的網址 → 分組 →（limit 時）取上限 → 標記，回傳要送出的 payload 清單。"""
    known = {e["url_canonical"] for e in existing}
    fresh = dedupe_urls([it for it in items if it["url_canonical"] not in known])
    cl = tax["clustering"]
    refs = clustering.assign_clusters(fresh, existing, embed, cl["threshold"], cl["jaccard_fallback"])
    chosen = clustering.apply_limit(fresh, refs, tax["limits"]["daily_top"]) if limit else list(zip(fresh, refs))
    terms = note_terms(root)
    return [to_payload(it, ref, tags_for(it, tax, terms), added_by) for it, ref in chosen]


def fetch_content(url: str) -> str:
    """抓原文取正文前 1,500 字；被擋、逾時、解析不出來都回傳空字串（改用 RSS 摘要）。"""
    try:
        req = urllib.request.Request(url, headers={"user-agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            page = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        import trafilatura
        return (trafilatura.extract(page) or "")[:CONTENT_MAX]
    except Exception:
        return ""


def add_content(payload):
    with ThreadPoolExecutor(max_workers=8) as ex:
        texts = ex.map(lambda p: fetch_content(p["url_original"]) if p["url_resolved"] else "", payload)
        for p, text in zip(payload, texts):
            p["content"] = text


def print_report(payload, stats, hours, method):
    groups = {}
    for p in payload:
        groups.setdefault(p["cluster_ref"], []).append(p)
    ordered = sorted(groups.items(), key=lambda kv: -max(p["score"] for p in kv[1]))
    print(f"── 送出 {len(payload)} 則，{len(groups)} 個分組（分組方法：{method}）──")
    for ref, ps in ordered:
        ps.sort(key=lambda p: -p["score"])
        where = "併入既有分組 #" + str(ref) if isinstance(ref, int) else "新分組"
        lead = ps[0]
        print(f"[{lead['score']:>2}] {lead['tier']:<10} {lead['title'][:70]}  〔{where}〕")
        for p in ps[1:]:
            print(f"       ↳ [{p['score']:>2}] {p['outlet'][:14]:<14} {p['title'][:52]}")
        tags = ", ".join(f"{t['kind']}:{t['key']}" for t in lead["tags"])
        if tags:
            print(f"       標記：{tags}")
    print(f"\n── 來源健康度（feed 總則數／{hours} 小時內）──")
    for name, (total, win, err) in stats.items():
        flag = "✗ 抓不到" if total == 0 else ("· 無新文" if win == 0 else "✓")
        print(f"  {flag:<8} {name:<28} {total:>3}／{win:<3} {err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=36)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tax = load_taxonomy()
    cfg = yaml.safe_load(FEEDS.read_text(encoding="utf-8"))
    items, stats = collect(a.hours, cfg, tax["scoring"])
    kept = [it for it in items if it["score"] >= tax["limits"]["min_score"]]
    decode_gnews(kept)
    for it in kept:
        it["url_canonical"] = normalize_url(it["url"])

    client = client_from_env(required=not a.dry_run)
    try:
        existing = client.recent(tax["clustering"]["window_days"]) if client else []
    except ApiError as e:
        sys.exit(f"讀取既有新聞失敗，中止（不寫半套）：{e}")

    embed = clustering.load_embedder(tax["clustering"]["model"])
    payload = prepare_payload(kept, existing, tax, embed, "bot")
    method = "語意模型" if embed else "標題 Jaccard（模型載入失敗）"
    print(f"抓到 {len(items)} 則，{len(kept)} 則達 {tax['limits']['min_score']} 分，"
          f"資料庫已有 {len(existing)} 則")
    print_report(payload, stats, a.hours, method)
    if a.dry_run or not payload:
        return

    add_content(payload)
    run_id = os.environ.get("GITHUB_RUN_ID") or dt.datetime.now().strftime("local-%Y%m%d%H%M%S")
    r = client.ingest(payload, run_id)
    print(f"\n寫入 {r['inserted']}、重複 {r['duplicates']}、AI 失敗 {r['ai_failed']}、"
          f"欄位錯誤 {len(r['errors'])}、失敗批次 {r['failed_batches']}")
    for err in r["errors"]:
        print(f"  ! {err}", file=sys.stderr)
    if r["failed_batches"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5：確認通過**

Run: `PYTHONUTF8=1 python -m pytest -q`
Expected: 全部 PASS

- [ ] **Step 6：真實來源試跑（不送出）**

```bash
PYTHONUTF8=1 python scripts/fetch_news.py --dry-run --hours 36
```

Expected：先印 `抓到 N 則，M 則達 3 分`，再印分組清單（有 `↳` 的是被併在一起的報導、`標記：` 列出標記），最後是來源健康度。本機沒裝 googlenewsdecoder／sentence-transformers 時會印「轉址解碼失敗」「退回標題 Jaccard」，這是預期的備援行為。撰寫計畫時實測：778 則 → 177 則 → 送出 93 則、60 個分組，SEC Peirce 零知識證明的 10 家報導正確併成一組。

- [ ] **Step 7：Commit**

```bash
git add scripts/ingest_client.py scripts/fetch_news.py tests/test_ingest_client.py tests/test_fetch_news.py
git commit -m "feat: fetch_news 改送 /api/ingest（解轉址、正規化、分組、取上限、標記、抓原文）"
```

---

### Task 8：舊自動卡匯入

**Files:**
- Create: `scripts/import_legacy.py`
- Test: `tests/test_import_legacy.py`

**Interfaces:**
- Consumes: `prepare_payload()`、`print_report()`（Task 7）、`Client`（Task 7）、`notes.iter_notes()`、`notes.is_legacy_auto()`（階段 1）。
- Produces: `card_to_item(note) -> dict | None`、`legacy_summary(body) -> str`；CLI `python scripts/import_legacy.py [--dry-run]`，數量對不上時 exit 非 0。

- [ ] **Step 1：寫失敗的測試** `tests/test_import_legacy.py`

```python
from import_legacy import card_to_item, legacy_summary
from notes import parse_note

OLD_CARD = """---
type: event
date: 2026-09-22
title: "SoFi begins stablecoin settlement on Mastercard network"
source_url: "https://www.theblock.co/post/1?utm_source=rss"
source_name: "The Block"
source_tier: trade
score: 9
auto: true
---

## 一句話
（待填）

## 事實（只放可查證的）
- SoFi said the program will exceed $25 billion.

## 我的判讀
-
"""

WIP_CARD = """---
type: event
date: 2026-09-24
title: "Chainlink CCIP powers fund"
source_url: "https://news.google.com/rss/articles/abc"
source_name: "Reuters（GN Chainlink）"
source_tier: aggregator
score: 6
auto: true
---

## 內容
Chainlink said X.
"""


def _card(tmp_path, text):
    p = tmp_path / "card.md"
    p.write_text(text, encoding="utf-8")
    return parse_note(p)


def test_old_card(tmp_path):
    it = card_to_item(_card(tmp_path, OLD_CARD))
    assert it["url_canonical"] == "https://www.theblock.co/post/1"
    assert (it["outlet"], it["source_feed"], it["tier"], it["score"]) == ("The Block", "The Block", "trade", 9)
    assert it["published_at"] == "2026-09-21T16:00:00Z"       # 台北 9/22 00:00
    assert it["rss_summary"] == "SoFi said the program will exceed $25 billion."
    assert it["url_resolved"] == 1 and it["lang"] == "en"


def test_wip_card_with_google_news_source(tmp_path):
    it = card_to_item(_card(tmp_path, WIP_CARD))
    assert (it["outlet"], it["source_feed"], it["tier"]) == ("Reuters", "GN Chainlink", "aggregator")
    assert it["url_resolved"] == 0
    assert it["rss_summary"] == "Chainlink said X."


def test_card_missing_url_or_bad_date(tmp_path):
    assert card_to_item(_card(tmp_path, OLD_CARD.replace("source_url:", "x:"))) is None
    assert card_to_item(_card(tmp_path, OLD_CARD.replace("date: 2026-09-22", "date: 昨天"))) is None


def test_placeholder_summary_is_empty():
    assert legacy_summary("## 事實\n- （待填）\n\n## 我的判讀\n-") == ""
```

- [ ] **Step 2：確認失敗**

Run: `PYTHONUTF8=1 python -m pytest tests/test_import_legacy.py -q`
Expected: FAIL，`No module named 'import_legacy'`

- [ ] **Step 3：建立 `scripts/import_legacy.py`**

```python
#!/usr/bin/env python3
"""把 10-events/ 的舊自動卡（auto: true）匯入 D1（spec §10 第 3 步）。

不呼叫 AI，沿用卡上的摘要（summary_by='rss'）。可重跑：已匯入的網址算重複，不會重複寫入。
卡片檔案這一階段不刪，階段 3 新聞頁改讀 D1 之後才刪。

用法：
    python scripts/import_legacy.py --dry-run     # 只列出會送什麼
    python scripts/import_legacy.py               # 需要 SITE_URL、INGEST_TOKEN
"""
import argparse
import datetime as dt
import re
import sys
import urllib.parse
from pathlib import Path

import clustering
from fetch_news import prepare_payload, print_report
from ingest_client import ApiError, client_from_env
from news_utils import detect_lang, normalize_url, utc_iso
from notes import is_legacy_auto, iter_notes
from taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parent.parent
TPE = dt.timezone(dt.timedelta(hours=8))
GN_SOURCE = re.compile(r"^(.*)（(GN .+)）$")      # WIP 分支的格式：「Reuters（GN Chainlink）」
LOOKBACK_DAYS = 60                                # 比對既有分組的範圍：要涵蓋最舊的卡


def legacy_summary(body: str) -> str:
    m = re.search(r"^## (?:內容|事實)[^\n]*\n(.*?)(?=^##\s|\Z)", body, re.S | re.M)
    if not m:
        return ""
    t = re.sub(r"^\s*-\s*", "", m.group(1).strip(), flags=re.M).strip()
    return "" if t in ("", "（待填）") else t[:2000]


def card_to_item(note):
    """舊自動卡 → 新聞 dict；缺網址、標題或日期回傳 None。"""
    fm = note.fm
    url = str(fm.get("source_url") or "").strip()
    title = str(fm.get("title") or "").strip()
    try:
        day = dt.date.fromisoformat(str(fm.get("date")))
    except ValueError:
        return None
    if not url.startswith(("http://", "https://")) or not title:
        return None
    src = str(fm.get("source_name") or "").strip() or "unknown"
    m = GN_SOURCE.match(src)
    outlet, feed = (m.group(1), m.group(2)) if m else (src, src)
    tier = fm.get("source_tier") if fm.get("source_tier") in ("primary", "trade", "aggregator") else "trade"
    score = fm.get("score") if isinstance(fm.get("score"), int) else 0
    return {"title": title, "url": url, "url_canonical": normalize_url(url),
            "url_resolved": 0 if urllib.parse.urlsplit(url).netloc.endswith("news.google.com") else 1,
            "outlet": outlet, "source_feed": feed, "tier": tier, "lang": detect_lang(title),
            "published_at": utc_iso(dt.datetime.combine(day, dt.time(0), TPE)),
            "rss_summary": legacy_summary(note.body), "score": score}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tax = load_taxonomy()
    cards = [n for n in iter_notes(ROOT, ("10-events",)) if n.error or is_legacy_auto(n)]
    items, bad = [], []
    for n in cards:
        it = None if n.error else card_to_item(n)
        (items.append(it) if it else bad.append(f"{n.path.name}：{n.error or '缺網址、標題或日期'}"))
    print(f"舊自動卡 {len(cards)} 張，可匯入 {len(items)} 張，無法匯入 {len(bad)} 張")
    for b in bad:
        print(f"  ! {b}")

    client = client_from_env(required=not a.dry_run)
    try:
        existing = client.recent(LOOKBACK_DAYS) if client else []
    except ApiError as e:
        sys.exit(f"讀取既有新聞失敗：{e}")
    embed = clustering.load_embedder(tax["clustering"]["model"])
    # 資料庫已有的網址不送（prepare_payload 會濾掉），所以重跑時 payload 只剩沒匯入過的
    payload = prepare_payload(items, existing, tax, embed, "import", limit=False)
    already = len(items) - len(payload)
    print_report(payload, {}, 0, "語意模型" if embed else "標題 Jaccard")
    if a.dry_run or not payload:
        print(f"\n資料庫已有 {already} 張，待送 {len(payload)} 張")
        return

    r = client.ingest(payload, run_id="import-legacy", skip_ai=True)
    print(f"\n寫入 {r['inserted']}、重複 {r['duplicates']}、欄位錯誤 {len(r['errors'])}、失敗批次 {r['failed_batches']}")
    for err in r["errors"]:
        print(f"  ! {err}", file=sys.stderr)
    if r["inserted"] + r["duplicates"] != len(payload) or r["failed_batches"]:
        sys.exit("數量對不上：寫入＋重複 ≠ 待送張數，請看上面的錯誤")
    print(f"✓ 全部 {len(items)} 張已在 D1（本次寫入 {r['inserted']}，先前已有 {already + r['duplicates']}）")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4：確認通過並試跑**

```bash
PYTHONUTF8=1 python -m pytest -q
git merge --no-commit --no-ff origin/main     # 暫時合進 main 最新的自動卡，只為了試跑
PYTHONUTF8=1 python scripts/import_legacy.py --dry-run | head -5
git merge --abort
```

Expected：測試全過；dry-run 第一行 `舊自動卡 N 張，可匯入 N 張，無法匯入 0 張`（2026-09-25 時 main 上有 53 張，之後每天增加，直到上線）。若有「無法匯入」，逐張看原因：YAML 壞掉的卡要手動修好再匯入，不能靜默丟掉。

- [ ] **Step 5：Commit**

```bash
git add scripts/import_legacy.py tests/test_import_legacy.py
git commit -m "feat: import_legacy.py 把舊自動卡匯入 D1（不呼叫 AI，可重跑）"
```

---

### Task 9：Actions、相依、Makefile、說明文件

**Files:**
- Rewrite: `.github/workflows/news.yml`、`scripts/README.md`
- Create: `requirements-news.txt`
- Modify: `Makefile`、`docs/superpowers/specs/2026-09-24-vault-v2-design.md`

**Interfaces:**
- Consumes: `fetch_news.py`、`import_legacy.py` 的 CLI；GitHub secrets `SITE_URL`、`INGEST_TOKEN`。
- Produces: `workflow_dispatch` 輸入 `mode: daily | import`。

- [ ] **Step 1：建立 `requirements-news.txt`**

```
# GitHub Actions 每日新聞管線的相依（scripts/fetch_news.py、import_legacy.py、calibrate_clusters.py）
# torch 用 CPU 版，避免下載 2 GB 的 CUDA 版
--extra-index-url https://download.pytorch.org/whl/cpu
torch
sentence-transformers>=3
feedparser
pyyaml
trafilatura
googlenewsdecoder==0.2.1
```

- [ ] **Step 2：重寫 `.github/workflows/news.yml`**

```yaml
# 每天抓新聞並送進 D1（POST /api/ingest）。不 commit、不重建網站。
# 手動執行時可選 mode=import：把 10-events/ 的舊自動卡匯入 D1（只需跑一次，重跑無害）。
name: news

on:
  schedule:
    - cron: "0 23 * * *"      # UTC 23:00 = 台北 07:00
  workflow_dispatch:
    inputs:
      mode:
        description: "daily＝每日抓取；import＝匯入舊自動卡"
        type: choice
        options: [daily, import]
        default: daily

permissions:
  contents: read              # 不再 push

concurrency:
  group: news
  cancel-in-progress: false

jobs:
  fetch:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      SITE_URL: ${{ secrets.SITE_URL }}
      INGEST_TOKEN: ${{ secrets.INGEST_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements-news.txt
      - run: pip install -r requirements-news.txt
      - name: 快取分組模型
        uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: hf-sentence-transformers-LaBSE     # 換模型時改這裡

      - name: 每日抓取（週一改抓 72 小時補週末）
        if: github.event.inputs.mode != 'import'
        run: |
          HOURS=36
          # 用台北時間判斷星期：cron 在 UTC 週日 23:00 觸發，那時台北已是週一
          [ "$(TZ=Asia/Taipei date +%u)" = "1" ] && HOURS=72
          python scripts/fetch_news.py --hours "$HOURS"

      - name: 匯入舊自動卡
        if: github.event.inputs.mode == 'import'
        run: python scripts/import_legacy.py
```

確認語法：

```bash
python -c "import yaml;d=yaml.safe_load(open('.github/workflows/news.yml',encoding='utf-8'));print(d[True]['workflow_dispatch']['inputs']['mode']['options'])"
```

Expected: `['daily', 'import']`

- [ ] **Step 3：修改 `Makefile`**

```diff
@@ -11,27 +11,31 @@ help: ## 顯示所有指令
 	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
 	 | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
 
-install: ## 安裝相依（python 套件）
-	$(PY) -m pip install --quiet --upgrade feedparser pyyaml markdown
+install: ## 安裝建站與測試相依
+	$(PY) -m pip install --quiet -r requirements-dev.txt
 	@echo "✓ 相依安裝完成"
 
+install-news: ## 安裝新聞管線相依（含 CPU 版 torch，約 1 GB）
+	$(PY) -m pip install -r requirements-news.txt
+
 check: ## 檢查環境
 	@$(PY) --version
 	@$(PY) -c "import feedparser, yaml, markdown; print('✓ python 套件齊全')"
 	@git --version >/dev/null && echo "✓ git"
 	@echo "✓ vault: $(VAULT)"
 
-peek: ## 試抓不寫檔（看排序準不準）
+peek: ## 試抓不送出（看排序、分組、來源健康度）
 	$(PY) scripts/fetch_news.py --dry-run --hours 36
 
-peek-week: ## 試抓一週（週一補週末用）
+peek-week: ## 試抓一週不送出
 	$(PY) scripts/fetch_news.py --dry-run --hours 168
 
-fetch: ## 真的抓取並寫入事件卡＋每日筆記
-	$(PY) scripts/fetch_news.py --hours 36 --top 15
+calibrate: ## 事件分組門檻校準（需先 make install-news）
+	$(PY) scripts/calibrate_clusters.py
 
-fetch-week: ## 抓 72 小時（週一用）
-	$(PY) scripts/fetch_news.py --hours 72 --top 20
+test: ## 跑 Python 與 Functions 測試
+	$(PY) -m pytest -q
+	node --test "tests/js/*.test.js"
 
 build: ## 產生靜態網站到 site/
 	$(PY) scripts/build_site.py
@@ -40,9 +44,6 @@ serve: build ## 產生後在本機 8080 預覽
 	@echo "→ http://localhost:8080"
 	@cd $(SITE) && $(PY) -m http.server 8080
 
-update: fetch build ## 抓取＋重建網站（日常一鍵）
-	@echo "✓ 已更新"
-
 status: ## vault 統計
 	@$(PY) scripts/status.py
 
@@ -62,4 +63,4 @@ publish: ## commit + push（觸發 GitHub Pages 部署）
 clean: ## 刪除產出的網站
 	rm -rf $(SITE)
 
-.PHONY: help install check peek peek-week fetch fetch-week build serve update status unread new-event new-concept publish clean
+.PHONY: help install install-news check peek peek-week calibrate test build serve status unread new-event new-concept publish clean
```

- [ ] **Step 4：重寫 `scripts/README.md`**

````markdown
# 新聞管線

每天台北 07:00 由 GitHub Actions（`.github/workflows/news.yml`）執行 `fetch_news.py`，
結果送進 D1（`POST /api/ingest`），**不再寫 repo**。

```
抓取 → 評分 → 解 Google News 轉址 → 網址正規化 → 去重 → 分組 → 取上限 → 標記 → 抓原文 → 送出
```

## 本機試跑
```bash
pip install -r requirements-news.txt           # 含 CPU 版 torch，約 1 GB
python scripts/fetch_news.py --dry-run         # 印排名、分組、標記、來源健康度，不送出
```
有設 `SITE_URL`、`INGEST_TOKEN` 時，dry-run 會讀資料庫既有新聞來比對；沒設就當資料庫是空的。
Windows 要加 `PYTHONUTF8=1`；torch 要裝在短路徑的 venv（例如 `C:\bvv`），否則會撞到 260 字元路徑上限。

## 檔案
| 檔案 | 職責 |
|---|---|
| `feeds.yaml` | 來源清單：`primary`（一手）、`trade`（媒體）、`aggregator`（Google News 查詢） |
| `../taxonomy.yaml` | 評分權重、雜訊詞、主題對應、轄區規則、分組模型與門檻、每日上限 |
| `tagging.py` | 唯一的關鍵詞比對 `matches()`，以及 topic／watch／note／jurisdiction 標記 |
| `scoring.py` | 評分 |
| `clustering.py` | 事件分組（語意模型，失敗退回標題 Jaccard） |
| `ingest_client.py` | 呼叫 `/api/news/recent`、`/api/ingest` |
| `import_legacy.py` | 一次性：把舊自動卡匯入 D1 |
| `calibrate_clusters.py` | 分組門檻校準，結果記在 `docs/decisions.md` |

## 評分（`scoring.py`，規則在 `taxonomy.yaml` 的 `scoring`）
1. **標題命中加倍**：權重詞在標題得 2 倍，只在摘要得 1 倍。
2. **組合加分**：`combos` 的 a、b 兩組同時命中才加。
3. **封頂** `cap: 20`，再每個雜訊詞扣 6。
4. **核心主題閘**：沒命中 `core` 扣 8；命中才給 tier 加分（一手 +4、Google News −2）。
   Google News 查詢本身已限定主題（`assume_core: true`），不必再命中 core。
5. **泛用詞**（`generic`：Polygon、Fidelity、富達、Onyx）只在標題也命中 core 詞時才計分。

低於 `limits.min_score`（3）的不送。每天最多開 `limits.daily_top`（60）個**新分組**；併入既有分組的報導不佔名額。

## 比對規則（`tagging.matches()`）
- 英數關鍵詞做**單字邊界**比對，否則 `SSI` 會命中 `Commission`、`SEC` 會命中 `Securities`。
- **全大寫縮寫區分大小寫**：`DID` 不會命中英文動詞 did。
- 尾端 `*` 表示字根，只放寬右邊界（`tokeniz*` 命中 tokenized）。縮寫不要加 `*`。YAML 裡要加引號。
- 中文做子字串比對，雙方先轉繁體（`稳定币` 也命中 `穩定幣`）；只轉字，不轉詞彙（`监管` 不等於 `監理`）。

## 分組（`clustering.py`）
新報導依分數高到低，跟 14 天內的報導與本次已處理的報導比 cosine 相似度，
≥ `clustering.threshold` 就併進最像的那組，否則開新組。模型與門檻的校準見 `docs/decisions.md`。
模型載入失敗時退回標題 Jaccard（門檻 0.35），log 會標出來。
````

- [ ] **Step 5：spec 同步校準結果**

`docs/superpowers/specs/2026-09-24-vault-v2-design.md` §6.2 前兩條改成：

```markdown
- 模型：`sentence-transformers/LaBSE`（中英文，768 維）。用 `actions/cache` 快取模型。原訂 `paraphrase-multilingual-MiniLM-L12-v2`，校準時漏併 5 對，換掉；比較見 `docs/decisions.md`。
- 輸入：`title` 加上 `title_zh`（有的話）。新進報導跟 14 天內所有報導比較。
```

第四條的「門檻初值 0.75」改成「門檻 0.67（2026-09-25 校準）」。§6.3 第一條後面加一句：「關鍵詞比對一律用 `tagging.matches()`：全大寫縮寫區分大小寫，中文先簡轉繁。」

- [ ] **Step 6：全部測試與建站**

```bash
PYTHONUTF8=1 python -m pytest -q
node --test "tests/js/*.test.js"
PYTHONUTF8=1 python scripts/build_site.py
```

Expected：pytest 87 passed；node `ℹ fail 0`；建站印 `驗證完成：0 個錯誤` 與 `✓ 網站已產生`。

- [ ] **Step 7：Commit**

```bash
git add requirements-news.txt .github/workflows/news.yml Makefile scripts/README.md docs/superpowers/specs/2026-09-24-vault-v2-design.md
git commit -m "feat: news workflow 改送 D1、加 import 模式；更新 Makefile 與說明"
```

---

### Task 10：上線（需要使用者與 repo 擁有者）

這個 task 會動到線上資料庫與 secrets，**每一步先跟使用者確認再做**。

**前提：** PR #1 已合併；本分支的 PR 已開、base 改成 main、審閱通過但**還沒合併**。

- [ ] **Step 1：使用者登入 wrangler**

請使用者在 Claude Code 輸入 `! npx wrangler login`（瀏覽器授權有 120 秒時限，帳號要有 `blockchain-vault` Pages 專案的權限）。

- [ ] **Step 2：查線上 D1 現況**

```bash
npx wrangler d1 execute blockchain-vault-comments --remote --command "SELECT name, type FROM sqlite_master ORDER BY name;"
```

Expected：只有 `comments` 與 `idx_comments_slug`（加上 SQLite 內部表）。若已有 `news_items`，先問使用者再繼續。

- [ ] **Step 3：套用 migration 並確認**

```bash
npx wrangler d1 execute blockchain-vault-comments --remote --file db/migrations/0001_news.sql
npx wrangler d1 execute blockchain-vault-comments --remote --command "SELECT name, type FROM sqlite_master WHERE name LIKE 'news%' OR name IN ('clusters','ingest_log') ORDER BY name;"
```

Expected：`clusters`、`ingest_log`、`news_fts`（table）、`news_items`、`news_tags`、三個 trigger `news_fts_ai`／`news_fts_ad`／`news_fts_au`、索引 `idx_news_pub`／`idx_news_cluster`／`idx_tags_key`。缺 trigger 表示 wrangler 切錯 `BEGIN…END`，改用 `--command` 逐條建 trigger。

- [ ] **Step 4：設定 Pages secret 與 AI binding**

```bash
python -c "import secrets;print(secrets.token_urlsafe(32))" > "$TEMP/ingest_token.txt"
npx wrangler pages secret put INGEST_TOKEN --project-name blockchain-vault < "$TEMP/ingest_token.txt"
```

請使用者：
1. 把 `$TEMP/ingest_token.txt` 的內容存進密碼管理器，並交給 repo 擁有者 zuemen。存好後刪掉這個檔。
2. Cloudflare dashboard → Pages → blockchain-vault → Settings → Bindings → Add → Workers AI，變數名 `AI`，環境 Production。

- [ ] **Step 5：repo 擁有者設定 GitHub secrets**

先試 `gh secret set INGEST_TOKEN < "$TEMP/ingest_token.txt"`；被拒（協作者沒有權限）就請 zuemen 在 GitHub → Settings → Secrets and variables → Actions 設定：
- `INGEST_TOKEN`：同上
- `SITE_URL`：production 網址（`https://blockchain-vault-cvm.pages.dev`，有自訂網域就用自訂網域）

- [ ] **Step 6：合併本分支的 PR，等 Cloudflare 部署完成後冒煙測試**

```bash
SITE_URL=https://blockchain-vault-cvm.pages.dev     # 與 Step 5 設定的相同
curl -s -o /dev/null -w "%{http_code}\n" -H "x-ingest-token: wrong" "$SITE_URL/api/news/recent"
curl -s -H "x-ingest-token: $(cat "$TEMP/ingest_token.txt")" "$SITE_URL/api/news/recent?days=14"
```

Expected：第一行 `403`；第二行 `{"items":[],"next_page":null}`。

- [ ] **Step 7：匯入舊自動卡**

```bash
gh workflow run news.yml -f mode=import
gh run watch "$(gh run list --workflow news.yml --limit 1 --json databaseId -q '.[0].databaseId')"
npx wrangler d1 execute blockchain-vault-comments --remote --command "SELECT added_by, COUNT(*) FROM news_items GROUP BY added_by;"
```

Expected：log 最後一行 `✓ 全部 N 張已在 D1`；SQL 顯示 `import` 的數量等於 N。

- [ ] **Step 8：第一次每日執行**

```bash
gh workflow run news.yml -f mode=daily
gh run watch "$(gh run list --workflow news.yml --limit 1 --json databaseId -q '.[0].databaseId')"
npx wrangler d1 execute blockchain-vault-comments --remote --command "SELECT at, received, inserted, duplicates, ai_failed, errors FROM ingest_log ORDER BY id DESC LIMIT 10;"
npx wrangler d1 execute blockchain-vault-comments --remote --command "SELECT c.id, c.item_count, n.title FROM clusters c JOIN news_items n ON n.id = c.lead_item_id ORDER BY c.item_count DESC LIMIT 10;"
```

Expected：job 綠燈、log 的分組方法是「語意模型」；`ingest_log` 每批 `ai_failed` 大多為 0（若全部失敗，檢查 AI binding 是否在 Production）；分組清單沒有明顯把不同事件併在一起。

- [ ] **Step 9：AI 摘要抽查（spec §12）**

```bash
npx wrangler d1 execute blockchain-vault-comments --remote --command "SELECT id, title, title_zh, summary, url_original FROM news_items WHERE summary_by = 'ai' ORDER BY RANDOM() LIMIT 10;"
```

請使用者逐則打開原文比對：數字、日期、機構名是否正確，有沒有原文沒寫的內容。結果（幾則正確、錯在哪）寫進 `docs/decisions.md` 的「AI 摘要抽查」一節，commit：

```bash
git add docs/decisions.md
git commit -m "docs: 階段 2 上線驗收與 AI 摘要抽查"
```

- [ ] **Step 10：更新記憶與待辦**

- 記憶 `vault-v2-redesign.md`：階段 2 完成、下一步階段 3。
- repo 外 `_繳交說明與待辦.md`：勾掉「GitHub Actions 寫 D1 的 token」那一項（本設計改用 `INGEST_TOKEN`，不需要 Cloudflare API token）。
