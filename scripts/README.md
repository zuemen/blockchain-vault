# 自動化

## 本機跑一次
```bash
pip install feedparser pyyaml
python3 scripts/fetch_news.py --dry-run     # 先看抓到什麼、分數合不合理
python3 scripts/fetch_news.py --top 8       # 真的寫入 vault
```

週一補週末：`python3 scripts/fetch_news.py --hours 72`

## 調整
- **來源**：改 `feeds.yaml` 的 `primary` / `trade`
- **權重**：改 `feeds.yaml` 的 `weights`。一手來源自動 +4 分（`fetch_news.py` 的 `TIER_BONUS`）
- **主題歸類**：改 `fetch_news.py` 的 `topics_of()`

## 它會做什麼／不會做什麼
會：寫 `10-events/` 事件卡骨架（判讀欄位留空）、在 `99-daily/` 列出今天新增與命中理由。
不會：寫 `20-concepts/`、填「我的判讀」、產生連結到不存在的概念筆記。

## 第一週建議
先跑 `--dry-run` 一週，只觀察分數排序準不準，再開始真的寫檔。
權重調準之後再接 GitHub Actions。

## 怎麼看分數
| 分數 | 動作 |
|---|---|
| **10 分以上** | 值得展開寫（補判讀、連概念筆記） |
| **5–9 分** | 掃一眼標題與摘要就好 |
| **5 分以下** | 忽略 |

上限 20 分（關鍵詞＋組合加分封頂 20，再加 tier 加分／扣分）。

計分機制（`fetch_news.py` 的 `score()`）：
1. **標題命中加倍**：關鍵詞出現在標題得 2 倍權重，只在摘要出現得 1 倍。標題是編輯判斷過的重點，摘要常是順帶一提。
2. **組合加分**：兩組主題詞同時出現才是真正要找的訊號，單獨出現只是背景雜訊。
   - 代幣化 × 結算／DvP／CBDC：+4
   - 穩定幣 × 法規／監理／license：+3
   - SSI／DID／VC × KYC／AML／法規：+4
   - ZK × 身分／隱私／法遵：+4
   - RWA／代幣化 × 基金／債券／黃金／存款：+3
3. **核心主題閘**：沒命中任何核心詞扣 8 分；命中才給一手來源 +4。

如果某天最高分不到 5 分，通常代表那天真的沒事，不是程式壞了。

## 已知的坑（已修掉，但改權重時要小心）
短英文縮寫必須做**單字邊界**比對：
- `SSI` 會命中 `Commission`
- `SEC` 會命中 `Securities`

不做邊界比對的話，監理機關的例行處分公告會因為 tier 加分霸佔榜首。
處理在 `fetch_news.py` 的 `matches()`；新增 ASCII 縮寫關鍵字時沿用它就好。

**字根要加 `*`**：雙邊界會讓 `tokeniz` 永遠比不到 `tokenized`。關鍵詞尾端加 `*`（如 `tokeniz*`、`settle*`、`regulat*`）
只放寬右邊界；縮寫（SSI、SEC、DID…）**不要加** `*`，否則防護失效。YAML 裡要加引號：`"tokeniz*": 2`。
