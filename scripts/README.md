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
