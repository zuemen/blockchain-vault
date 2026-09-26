# blockchain-vault v2 設計規格

- 日期：2026-09-24
- 狀態：待使用者審閱
- 分支：`redesign/vault-v2`
- 前提文件：交接檔 `_交接給下一個_SESSION.md`、`repo現況盤點_20260924.md`（repo 外）

---

## 1. 這個 vault 要做什麼

**用途：替每週研究分享產出週報。** 主題是區塊鏈進入正規金融（銀行、監理、結算基礎設施）。

工作流是一條鏈：

```
新聞（原料，三個月就過期）
  → 概念／機構／法規筆記（解讀框架與背景，長期累積）
  → 週報與講稿（產出，這才是目的）
```

網站與留言是第二目的：公開當作品集，給朋友圈留言。

### 1.1 設計原則

1. **新聞是原料，放資料庫；會長期累積的東西放 repo。**
2. **AI 可以寫，但每篇要標出處；你讀過、改過才算你的知識。**
   取代舊 README 的「概念筆記自己寫」。舊原則實際上沒有落實：現有 35 篇永久筆記多半由 AI 撰寫（使用者 2026-09-24 確認）。
3. **自動化不寫結論。** 週報、判讀、永久筆記正文不由排程自動產生或改寫。
4. **外部事實要能回溯到原始來源。** AI 摘要一律標「未核對」，週報引用前要回原文核對。
5. **不花錢。** 全部在免費額度內，超出額度是被限流，不會收費。

### 1.2 不做的事

- 不抓 X（Twitter）：官方 API 要付費。改由手動收錄補洞（§6.4）。
- 不做 AI 自動週報，也不讓 AI 自動改寫永久筆記正文。
- 不做本機 Obsidian 同步機制。README 只寫一行 `git pull` 的做法。
- 不處理 Dune Analytics：它是數據看板，不是新聞源。

---

## 2. 查證過的平台限制（2026-09-24）

| 項目 | 免費額度 | 對設計的影響 |
|---|---|---|
| Workers／Pages Functions | 每請求 **10 ms CPU**、50 個子請求、每天 10 萬次請求 | 重運算（語意比對、標記）放 Actions。Function 只做驗證、I/O、呼叫 AI。大量資料要分頁 |
| Workers Cron | 每次 10 ms CPU | 無法抓 58 個 RSS，所以抓取留在 GitHub Actions |
| D1 | 單庫 500 MB、每天讀 500 萬列、寫 10 萬列、Time Travel 7 天 | 容量足夠。7 天回溯不夠當備份，所以另做 JSONL 備份（§9） |
| D1 FTS5 | 支援，含 trigram tokenizer；官方匯出不支援含虛擬表的庫 | 搜尋用 FTS5。備份不走官方匯出 |
| Workers AI | 每天 10,000 neurons；`qwen3-30b-a3b-fp8` 每百萬 token 輸入 4,625、輸出 30,475 neurons | 每天 60 則摘要約 700 neurons |
| GitHub Actions（私有 repo） | 每月 2,000 分鐘 | 每天約 5 分鐘，一個月約 150 分鐘 |
| Google News 轉址 | 2024 年底後無法離線解碼，要打 `batchexecute` | 用 `gnews-decoder` 批次解碼，失敗就保留轉址 |

---

## 3. 架構總覽

```
GitHub Actions（每天台北 07:00）── Python
  fetch → score → decode URL → normalize → dedupe → cluster → tag → extract
  └─ POST /api/ingest（INGEST_TOKEN，每批 10 則）
                    ↓
Pages Functions ── 驗證 → AI 摘要（Workers AI binding）→ 寫 D1
                    ↓
D1 ◀── 瀏覽器（新聞、事件、搜尋、候選題材：即時查）
repo Markdown ──▶ build_site.py ──▶ 靜態頁（筆記、週報）＋ 索引 JSON
```

- bot 不再 commit 新聞，每天也不用重建網站。
- 只有人或 AI 協作修改筆記時才 push，由 Cloudflare 重建靜態頁。
- 每週一 Actions 另外跑備份（§9），這是唯一會自動 commit 的工作。

---

## 4. repo 內容與筆記 schema

### 4.1 資料夾

| 資料夾 | 內容 | 變動 |
|---|---|---|
| `10-events/` | **精選事件**：被週報引用而升級的事件，加上現有 5 張人寫卡 | 38 張自動卡匯入 D1 後刪除 |
| `20-concepts/` | 概念 | 加欄位 |
| `30-entities/` | 機構 | 加欄位 |
| `40-regulations/` | 法規 | 加欄位 |
| `50-maps/` | MOC | 加欄位 |
| `60-outputs/` | 週報、講稿 | 開始上網站 |
| `archive/` | 每月新聞備份 `YYYY-MM.jsonl` | 新增 |
| `taxonomy.yaml` | 分類詞彙唯一來源（§4.3） | 新增 |
| `00-inbox/`、`99-daily/`、`sources.opml` | 遺留 | 刪除（99-daily 的內容已在 D1） |

### 4.2 共用 frontmatter 欄位

所有筆記（home 除外）都要有：

| 欄位 | 規格 |
|---|---|
| `id` | 8 碼小寫 base32 亂碼，建立後永不改。網址、留言、連結都用它 |
| `type` | `event`／`concept`／`entity`／`regulation`／`moc`／`output` |
| `title` | 字串，必填（目前多數筆記用 H1 當標題，遷移時補上） |
| `origin` | `ai`／`ai-reviewed`／`human`。現有筆記一律先標 `ai`；5 張人寫事件卡與 2 篇週報由使用者判定 |
| `reviewed` | 日期，`origin: ai-reviewed` 時必填 |
| `aliases` | 字串陣列，選填。新聞標記用（§6.3），例如 cash-leg：`[現金腿, cash leg, DvP, settlement asset]` |
| `topics` | 陣列，值必須存在於 `taxonomy.yaml` |
| `updated` | 日期 |

各類型另有：

| 類型 | 額外欄位 |
|---|---|
| concept | `maturity: seed|growing|stable` |
| entity | `category`、`jurisdiction`（值在 taxonomy）、`watch`（對應 watchlist id，選填） |
| regulation | `jurisdiction`、`regulator`、`stage: 1–5`、`tracks`、`review: 待核對|已核對`；`effective_date` 改成 `YYYY`／`YYYY-MM`／`YYYY-MM-DD` 或空值；原本的附註文字（例如「最晚」「提案日」）移到 `effective_note` |
| event（精選） | `date`、`cluster`（D1 分組 id）、`source_url` |
| output | `kind: 週報|講稿`、`date`、`week`、`clusters`（陣列） |

移除沒有程式讀、也沒有用途的欄位：`keyword_hits`、`used_in`（改由連結反推）、事件卡的 `status`。

### 4.3 `taxonomy.yaml`

抓取、評分、標記、建站、驗證都只讀這一份：

```yaml
limits: { daily_top: 60, min_score: 3 }
topics:        [RWA, 穩定幣, 金融法規, SSI, ZK, 支付, 重點機構]
jurisdictions: { 美國: [US, SEC, ...], 歐盟: [...], ... }   # 取代 tracker.py 的 COUNTRIES
tracks:        [穩定幣, 結算／存款代幣, 代幣化證券／RWA, 數位身分, 虛擬資產業者]
stages:        { 1: 研議, 2: 草案, 3: 已通過, 4: 施行中, 5: 市場運作 }
watchlist:     # 8 個重點關注對象
  - { id: chainlink,  name: Chainlink,  aliases: [Chainlink, CCIP] }
  - { id: kinexys,    name: Kinexys（原 Onyx）, aliases: [Kinexys, Onyx by J.P. Morgan] }
  - { id: jpmorgan,   name: JPMorgan,   aliases: [JPMorgan, J.P. Morgan, JP Morgan, 摩根大通] }
  - { id: fidelity,   name: Fidelity,   aliases: [Fidelity, 富達] }
  - { id: bny,        name: BNY,        aliases: [BNY, BNY Mellon, 紐約梅隆] }
  - { id: fireblocks, name: Fireblocks, aliases: [Fireblocks] }
  - { id: zk,         name: Zero knowledge, aliases: [zero knowledge, ZKP, zkEVM, 零知識] }
  - { id: polygon,    name: Polygon／Privado ID, aliases: [Polygon, Polygon ID, Privado ID] }
scoring:       { weights: {...}, combos: [...], noise: [...], core: [...] }  # 自 fetch_news.py 與 WIP 分支搬出
```

泛用詞（Polygon、Fidelity、Onyx）單獨出現時，標題必須同時命中 `core` 詞才計分。這是為了壓低 WIP 分支觀察到的雜訊。

### 4.4 筆記內的新聞連結

- `[[news:123]]`：連到單則報導。
- `[[event:45]]`：連到事件分組。
- Obsidian 會把它們顯示成不存在的筆記，這是可以接受的代價。網站則渲染成正確連結並附標題。
- 建站時掃描所有筆記，輸出 `site/note-links.json`（news／event id → 引用它的筆記 id 陣列），新聞頁讀這個檔顯示「被哪些筆記引用」。

### 4.5 schema 驗證

`scripts/validate.py`，建站第一步執行，**有錯就讓 build 失敗**並列出檔案、欄位、原因：

- YAML 解析失敗、缺必填欄位、列舉值不合法
- `id` 重複
- `topics`／`jurisdiction`／`tracks` 值不在 taxonomy
- wikilink 指向不存在的筆記（警告，不讓 build 失敗）

---

## 5. D1 資料表

沿用資料庫 `blockchain-vault-comments`（id `97b604a1-…`），不改名。migration 檔放 `db/migrations/NNNN_*.sql`。

```sql
CREATE TABLE news_items (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  url_canonical TEXT NOT NULL UNIQUE,
  url_original  TEXT NOT NULL,
  url_resolved  INTEGER NOT NULL DEFAULT 1,     -- 0＝Google News 轉址沒解開
  title         TEXT NOT NULL,
  title_zh      TEXT,
  outlet        TEXT NOT NULL,                  -- 真正的媒體名
  source_feed   TEXT NOT NULL,                  -- feeds 設定裡的來源名
  tier          TEXT NOT NULL CHECK (tier IN ('primary','trade','aggregator','manual')),
  lang          TEXT NOT NULL,                  -- en / zh / ...
  published_at  TEXT NOT NULL,                  -- ISO 8601 UTC
  fetched_at    TEXT NOT NULL,
  summary       TEXT,
  summary_by    TEXT CHECK (summary_by IN ('ai','rss') OR summary_by IS NULL),
  score         INTEGER NOT NULL,
  cluster_id    INTEGER REFERENCES clusters(id),
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','hidden')),
  added_by      TEXT NOT NULL CHECK (added_by IN ('bot','manual','import')),
  needs_annotate INTEGER NOT NULL DEFAULT 0     -- 1＝手動收錄，等 Actions 補分組與標記
);
CREATE INDEX idx_news_pub     ON news_items (published_at);
CREATE INDEX idx_news_cluster ON news_items (cluster_id);

CREATE TABLE clusters (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title_zh     TEXT,
  lead_item_id INTEGER,
  first_seen   TEXT NOT NULL,
  last_seen    TEXT NOT NULL,
  item_count   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE news_tags (                        -- 取代原設計的 entities / news_entities
  news_id INTEGER NOT NULL REFERENCES news_items(id),
  kind    TEXT NOT NULL CHECK (kind IN ('topic','watch','note','jurisdiction')),
  key     TEXT NOT NULL,                        -- topic 名／watchlist id／筆記 id／轄區
  PRIMARY KEY (news_id, kind, key)
);
CREATE INDEX idx_tags_key ON news_tags (kind, key);

CREATE VIRTUAL TABLE news_fts USING fts5 (
  title, title_zh, summary, content='news_items', content_rowid='id', tokenize='trigram'
);
-- 以 trigger 同步 news_items 的 insert／update／delete

CREATE TABLE ingest_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL, run_id TEXT, received INTEGER, inserted INTEGER,
  duplicates INTEGER, ai_failed INTEGER, errors TEXT
);

-- 留言：刪除舊表重建（使用者 2026-09-24 同意；執行前再確認為 0 筆）
DROP TABLE comments;
CREATE TABLE comments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  target     TEXT NOT NULL,                     -- 'note:<id>' | 'news:<id>' | 'event:<id>'
  name       TEXT,
  body       TEXT NOT NULL,
  rating     INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_comments_target ON comments (target);
```

**與對話中第 2 段的差異**
- `entities`／`news_entities` 合併成 `news_tags`，機構、主題、概念、轄區用同一套標記。
- `news_vectors` 拿掉，語意比對在 Actions 做（§6.2）。

**容量（一年）**：新聞約 36,000 則 × 約 2 KB ≈ 73 MB，加上 FTS 索引，估計不到 200 MB。

---

## 6. 新聞管線

### 6.1 每日 Actions：`scripts/fetch_news.py`（重寫）

| 步驟 | 做什麼 | 失敗處理 |
|---|---|---|
| 1 抓取 | `feeds.yaml`：一手 21＋媒體 26＋Google News 查詢 11，全部帶瀏覽器 UA | 單一來源失敗就略過，寫進健康報告 |
| 2 評分 | 讀 `taxonomy.yaml.scoring`，規則沿用現行版，加上 §4.3 的泛用詞規則 | — |
| 3 解轉址 | `gnews-decoder` 一次批次解碼 | 失敗就保留轉址，`url_resolved=0` |
| 4 正規化 | 小寫 host、去 `utm_*`／`fbclid`／`gclid`／`ref`、去 fragment 與結尾斜線 | — |
| 5 取既有 | `GET /api/news/recent?days=14`（分頁，每頁 500） | API 失敗就中止並讓 job 失敗，不寫半套 |
| 6 網址去重 | `url_canonical` 已存在就丟掉 | — |
| 7 分組 | §6.2 | — |
| 8 取上限 | 取分數最高的 `daily_top` 個**新分組**；併入既有分組的報導不佔上限 | — |
| 9 標記 | §6.3 | — |
| 10 抓原文 | `trafilatura` 取正文前 1,500 字，逾時 10 秒 | 被擋就用 RSS 摘要 |
| 11 送出 | `POST /api/ingest`，每批 10 則 | 每批重試 2 次，仍失敗就記錄並繼續；最後有失敗批次就讓 job 顯示失敗 |
| 12 補註 | 取 `needs_annotate=1` 的手動收錄，跑 7 與 9，`POST /api/news/annotate` | 同上 |

CLI：保留 `--dry-run`、`--hours`，其餘上限一律讀 taxonomy。dry-run 印出排名、分組結果、來源健康度，不打寫入 API。

### 6.2 事件分組

- 模型：`sentence-transformers/LaBSE`（中英文，768 維）。用 `actions/cache` 快取模型。原訂 `paraphrase-multilingual-MiniLM-L12-v2`，校準時漏併 5 對，換掉；比較見 `docs/decisions.md`。
- 輸入：`title` 加上 `title_zh`（有的話）。新進報導跟 14 天內所有報導比較。
- 規則：cosine ≥ 門檻就併進相似度最高的分組，否則開新組。
- 門檻 0.67（2026-09-25 校準）。**上線前要用已知重複校準**：SoFi／Mastercard 3 張、加拿大六大銀行 3 張、a16z 2 張、CFTC 中英各 1 張都要合併，而 9/24 那批裡明顯不同的事件不能合併。校準結果寫進 `docs/decisions.md`。
- 標題 Jaccard 保留當備援：模型載入失敗時退回舊方法，並在 log 標記。

### 6.3 標記（在 Actions 做）

- `topic`：沿用評分詞表對應。關鍵詞比對一律用 `tagging.matches()`：全大寫縮寫區分大小寫，中文先簡轉繁。
- `watch`：命中 watchlist 別名。
- `note`：命中任一筆記的 `aliases` 或 `title`（ASCII 用單字邊界，CJK 用子字串，長度 ≥ 2）。
- `jurisdiction`：沿用 tracker.py 規則，搬到 taxonomy。
- 所有匹配邏輯只寫在一個 Python 模組 `scripts/tagging.py`，避免 JS 和 Python 各寫一套。
- 筆記別名改了之後，`make retag DAYS=90` 重算最近 90 天並送 `/api/news/annotate`。

### 6.4 `/api/ingest`（Function）

1. 驗 `INGEST_TOKEN`（固定時間比較）。
2. 驗每筆欄位：網址 `https?://`、長度上限、tier 與 lang 在允許值內、score 為整數。不合格的單筆回報錯誤，不擋整批。
3. 對每筆呼叫 Workers AI `@cf/qwen/qwen3-30b-a3b-fp8`，要求回傳 JSON `{title_zh, summary}`。提示詞要點：
   - 只根據提供的原文，原文沒寫的不要補
   - 2–3 句繁體中文，保留數字、日期、機構原名
   - 原文不足以摘要就回空字串
4. AI 失敗或回傳格式不對：`summary` 用 RSS 摘要、`summary_by='rss'`、`title_zh` 留空。不擋入庫。
5. 分組：payload 帶 `cluster_ref`，內容是既有 `cluster_id`，或批次內的暫時代號 `new:<n>`。Function 負責建新分組、更新 `item_count` 與 `last_seen`。
6. 用 `db.batch()` 寫入 `news_items`、`clusters`、`news_tags`、`ingest_log`。遇到 `url_canonical` UNIQUE 衝突算重複，不算錯誤。
7. 回傳 `{inserted, duplicates, ai_failed, errors:[…]}`。

**手動收錄** `POST /api/admin/capture`（ADMIN_TOKEN）：只收網址和選填備註。Function 抓網頁 `<title>` 與 meta description 呼叫 AI，寫入時 `tier='manual'`、`added_by='manual'`、`needs_annotate=1`、`score=0`、自成一組。隔天由 Actions 補分組與標記。

---

## 7. 使用流程的支援工具

### 7.1 本週候選題材

`GET /api/candidates?week=2026-W39`。以 D1 SQL 聚合當週分組，Function 只做排序，每週最多約 300 組，不會超過 CPU 上限。

候選分數：

| 項目 | 分數 |
|---|---|
| 分組內最高新聞分數 | +1× |
| 不同媒體家數 | 每家 +2，最多 +10 |
| 含一手來源 | +4 |
| 命中概念或法規筆記 | 每篇 +3，最多 +9 |
| 命中 watchlist | 每個 +2 |

每組附「入選原因」字串，例如「5 家報導，含一手來源，觸及 cash-leg、香港穩定幣條例」。**不產生任何結論或摘要以外的文字。**

### 7.2 週報骨架 `make new-output C=<分組id>`

`scripts/new_output.py` 呼叫公開的 `GET /api/events/<id>`，產生兩個檔：

1. `10-events/<日期>-<slug>.md`：升級的精選事件。`origin: human`，列出所有報導，每則附原文網址、媒體、一手或二手、AI 摘要，並標「未核對」。
2. `60-outputs/<日期>-週報-<slug>.md`：frontmatter 已填好（`clusters`、`topics`）。正文只放章節標題和素材區塊：來源清單、命中的概念與法規（附各自的 `origin`／`review` 狀態）。**判讀段落留空。**

### 7.3 筆記審閱 `make review-note N=<筆記id或檔名>`

`scripts/review_note.py` 呼叫 `GET /api/news?note=<id>&since=<updated>`，把筆記上次更新後的相關新聞整理成 Markdown，印到終端機，同時寫進 `.review/<id>.md`（被 gitignore）。之後在 Claude Code 裡跟 AI 一起改正文。改完由使用者把 `origin` 改成 `ai-reviewed` 並填 `reviewed`。

---

## 8. 網站

### 8.1 頁面

| 路徑 | 產生方式 | 內容 |
|---|---|---|
| `/` | 靜態外殼＋API | 候選題材前 5、今日新聞（依分組）、最新週報、審閱進度（例如「35 篇中已審 3 篇」） |
| `/news` | 靜態外殼＋API | 列表，可分頁；可依 topic、watch、tier、日期篩選 |
| `/event/?id=` | 靜態外殼＋API | 分組內所有報導（中英文並列）、標記、留言 |
| `/news/?id=` | 靜態外殼＋API | 原文連結、AI 摘要（標「AI 摘要，未核對」）、被引用的筆記 |
| `/candidates` | 靜態外殼＋API | 候選完整排序 |
| `/n/<id>.html` | 靜態 | 筆記正文、`origin` 標籤、連出與連入；最下方「最近相關新聞」由 API 載入。法規頁若 `updated` 之後有新標記新聞，顯示「近期有新聞，請核對 stage」 |
| `/outputs` | 靜態 | 週報列表 |
| `/review` | 靜態＋API | 待審閱筆記（`origin: ai`）、待核對法規、週報中的 🔍 行、法規更新提示 |
| `/tracker` | 靜態＋API | 國家×議題矩陣，改讀 taxonomy 與 D1（最後階段） |
| `/admin` | 靜態外殼 | 手動收錄、隱藏新聞、刪留言。token 只存在該分頁的 sessionStorage |

「靜態外殼＋API」是指 HTML 由建站產生，資料由前端 fetch API 取得。不用 Functions 產生 HTML，所以 CPU 用量最低。

### 8.2 公開 API

| 端點 | 說明 |
|---|---|
| `GET /api/news?page=&topic=&watch=&tier=&note=&since=&from=&to=` | 每頁 30 筆 |
| `GET /api/news/<id>` | 單則加標記 |
| `GET /api/events/<id>` | 分組加所有報導 |
| `GET /api/search?q=` | `q` 字數 ≥ 3 用 FTS5 trigram，< 3 用 `LIKE`（限最近 180 天）。回傳時合併 `site/notes-index.json` 的筆記結果 |
| `GET /api/candidates?week=` | §7.1 |
| `/api/comments?target=`、`POST /api/comments`、`GET /api/comments/recent`、`DELETE /api/comments/<id>` | 行為同現行版，`slug` 改成 `target`；`target` 要存在（筆記查 `notes-index.json`，新聞與分組查 D1） |

受保護的端點：`GET /api/news/recent`、`POST /api/ingest`、`POST /api/news/annotate`、`GET /api/export` 用 `INGEST_TOKEN`；`/api/admin/*` 與刪留言用 `ADMIN_TOKEN`。

### 8.3 共通規則

- 所有 D1 呼叫包 try/catch，錯誤回 `503 {error:"db_unavailable"}`，不回 500。
- 公開 GET 加 `cache-control: public, max-age=300`。留言相關維持 `no-store`。
- 使用者內容一律用 `textContent` 插入。
- preview 環境沒有 D1 binding，API 回 503，前端顯示「預覽環境無資料」。

---

## 9. 備份

- 每週一台北 08:00，Actions 呼叫 `GET /api/export?month=YYYY-MM&offset=`，分頁每頁 500 筆。取本月與上月資料，寫入 `archive/YYYY-MM.jsonl`，每行一則新聞，附分組與標記。
- 有變更才以 `archive-bot` commit `archive: YYYY-MM-DD`。
- 還原：`scripts/restore_archive.py` 讀 JSONL 轉 SQL，交給 `wrangler d1 execute` 執行。上線前在本機 D1 實際演練一次。

---

## 10. 遷移

依序執行，每步可重跑：

1. D1 migration：建新表。刪 `comments` 前先 `SELECT COUNT(*)`，不是 0 就停下來問使用者。
2. 筆記：`scripts/migrate_notes.py` 為每篇補 `id`、`title`、`origin: ai`；5 張人寫事件卡與 2 篇週報的 `origin` 列出來讓使用者判定。刪除 `keyword_hits`、`used_in`、事件 `status`。
3. 舊自動卡：`scripts/import_legacy.py` 把 38 張自動卡轉成 ingest payload，`added_by='import'`，跑分組與標記後送入 D1，**不呼叫 AI**，沿用卡上的摘要。確認數量正確後才刪檔。
4. 刪除 `99-daily/`、`00-inbox/`、`sources.opml`、`.nojekyll` 產生邏輯；HOME.md 改成不依賴 Dataview 的純索引。
5. `wip/news-sources-expansion` 分支：搬走來源清單、GN 查詢、`clean_summary()` 後不合併，保留分支不刪。

---

## 11. 部署與設定

| 項目 | 誰做 | 說明 |
|---|---|---|
| 產生 `INGEST_TOKEN` | Claude | `secrets.token_urlsafe(32)` |
| Pages secret `INGEST_TOKEN` | Claude（需 wrangler 登入） | 這台電腦尚未登入 wrangler，要使用者執行 `! npx wrangler login`，而且帳號要有該 Cloudflare 專案的權限 |
| Pages AI binding `AI` | Claude 或使用者 | 在 Pages 專案設定加上 Workers AI binding（production） |
| GitHub secret `INGEST_TOKEN`、`SITE_URL` | **repo 擁有者 zuemen** | 協作者帳號 wein2004 通常不能管 secret；若 `gh secret set` 被拒，就請擁有者操作 |
| Cloudflare `PYTHON_VERSION` | Claude | 若 build 再因 3.12.12 失敗，改成 `3.11.5` |

`wrangler.toml` 維持不放，原因見 README。

---

## 12. 測試

- **Python**（pytest，`tests/`）：網址正規化、評分（含泛用詞規則）、標記、分組門檻（以已知重複為 fixture）、schema 驗證（壞 YAML、未知 topic、重複 id）、JSONL 備份與還原的往返測試。
- **Functions**：輸入驗證等純函式抽成模組，用 `node --test` 測；整合測試用 `wrangler pages dev` 加本機 D1，跑 ingest → 查詢 → 留言 → 刪除。
- **線上驗收**：一次真實的 Actions 執行，檢查 `ingest_log`、首頁、事件頁、搜尋（2 字與 3 字查詢）、留言四支 API。
- **AI 摘要抽查**：上線前取 10 則，人工比對原文，確認沒有編造數字或機構。結果記錄在 `docs/decisions.md`。

---

## 13. 施工階段

| 階段 | 內容 | 預估 |
|---|---|---|
| 1 | `taxonomy.yaml`、`validate.py`、`migrate_notes.py`、建站接驗證 | 半天 |
| 2 | D1 migration、`/api/ingest`、`/api/news/recent`、`fetch_news.py` 重寫、分組校準、舊卡匯入 | 1 天 |
| 3 | 新聞、事件、搜尋頁與 API，留言改 `target` | 1 天 |
| 4 | 候選題材、`new-output`、`review-note`、`/review`、`/admin` | 半天 |
| 5 | 備份與還原演練、矩陣、清理、README、`docs/decisions.md` | 半天 |

每階段結束都要可部署、可驗收，不留半套功能在 main。

---

## 14. 風險

| 風險 | 對策 |
|---|---|
| `gnews-decoder` 依賴 Google 非公開端點，隨時可能失效 | 失效就保留轉址，`url_resolved=0`；網址去重對這類新聞失效，靠分組補救 |
| MiniLM 對專業短標題的分組品質不確定 | 階段 2 校準；不理想就換 `multilingual-e5-small` 再測 |
| qwen3 摘要編造內容 | 提示詞限制加上 10 則抽查；網站一律標「未核對」 |
| 抓原文被媒體擋 | 退回 RSS 摘要 |
| Function 10 ms CPU 不夠 | 批次維持 10 則、API 分頁；超出時先縮小批次 |
| 協作者無法設定 GitHub secret | 由 repo 擁有者操作（§11） |
