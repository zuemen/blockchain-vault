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
**只看相對排序，不要看絕對值。** 一則同時命中「代幣化 + 結算 + 監理」的報導大概 6–8 分，
單一命中約 2–4 分；一手來源命中核心主題才額外 +4。
如果某天最高分只有 2 分，通常代表那天真的沒事，不是程式壞了。

## 已知的坑（已修掉，但改權重時要小心）
短英文縮寫必須做**單字邊界**比對：
- `SSI` 會命中 `Commission`
- `SEC` 會命中 `Securities`

不做邊界比對的話，監理機關的例行處分公告會因為 tier 加分霸佔榜首。
處理在 `fetch_news.py` 的 `matches()`；新增 ASCII 縮寫關鍵字時沿用它就好。
