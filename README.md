# Blockchain Knowledge Vault

Zuemen 的區塊鏈／數位資產知識庫。主題：ZK、SSI／DID／VC、RWA、金融法規。

**核心原則：自動化只寫事件，概念筆記自己寫。**
事件卡是原料，三個月後多半沒用；概念筆記長得慢，但那是三年後還用得到的東西。
若讓 AI 自動長概念筆記，vault 會很豐富但知識沒進到腦袋——那跟訂閱一個網站沒差別。

---

## 一分鐘上手

```bash
bash setup.sh          # 裝相依、建 git、試抓、首次建站
make help              # 看所有指令
```

## CLI

| 指令 | 做什麼 |
| --- | --- |
| `make peek` | 試抓最近 36 小時，**只印不寫檔**（調權重時用這個） |
| `make peek-week` | 試抓一週 |
| `make fetch` | 真的抓取，寫入事件卡＋當日筆記 |
| `make fetch-week` | 抓 72 小時（週一補週末） |
| `make build` | 產生靜態網站到 `site/` |
| `make serve` | 建站後本機預覽 <http://localhost:8080> |
| `make update` | `fetch` + `build`，日常一鍵 |
| `make status` | vault 統計（事件狀態、概念成熟度、來源分布） |
| `make unread` | 未讀事件清單，分數高者在前，`★` 標一手來源 |
| `make new-event T="標題"` | 手動開一張事件卡 |
| `make new-concept T="名稱"` | 開一篇概念筆記 |
| `make publish` | commit + push（觸發網站自動部署） |
| `make check` | 檢查環境 |

## 資料夾

| 資料夾 | 放什麼 | 誰寫 | 上網站 |
| --- | --- | --- | --- |
| `00-inbox/` | 抓進來還沒分類的 | 自動 | ✗ |
| `10-events/` | 事件卡，一則新聞一個檔 | 自動骨架＋人工判讀 | ✓ |
| `20-concepts/` | 概念筆記 | **只能自己寫** | ✓ |
| `30-entities/` | 機構、公司、平台 | 半自動 | ✓ |
| `40-regulations/` | 法規與監理文件追蹤 | 自己寫 | ✓ |
| `50-maps/` | MOC，主題入口 | 自己維護 | ✓ |
| `60-outputs/` | 交出去的日報、週報、講稿 | 自己 | ✗（內部） |
| `99-daily/` | 每日筆記 | 自動列清單＋自己補想法 | ✗（內部） |

## frontmatter 兩個關鍵欄位
- `source_tier`：`primary`（監理機關、公司 IR）/ `trade` / `aggregator`。網站上一手來源有綠色標記，可一鍵過濾。
- `used_in`：這則用在哪份日報或週報。半年後回溯時省掉大量重看。

概念筆記的 `maturity`：`seed`（只有一個案例、講不深）→ `growing`（有案例）→ `stable`（能上台講十分鐘）。
`make status` 會提醒你 seed 是不是太多——那代表在囤積不在消化。

## 自動化怎麼跑
分工：**GitHub Actions 只抓新聞，建站與部署交給 Cloudflare Pages。**

```
Actions（台北 07:00）抓新聞 → commit 事件卡＋每日筆記 → push
        ↓（Cloudflare 監聽 repo 的 push）
Cloudflare Pages 自動 build（python scripts/build_site.py）→ 網站更新
```

- `.github/workflows/news.yml`：每天 UTC 23:00（台北 07:00）跑，週一自動改抓 72 小時補週末；Actions 頁面也能手動觸發。
- 你自己 push 筆記上來，一樣會觸發 Cloudflare 重建（但不會重抓新聞）。
- 沒抓到新事件就不 commit，Cloudflare 也不會重建。
- 筆記 repo **保持私有**：Cloudflare Pages 可以連私有 repo，不用像免費版 GitHub Pages 那樣公開。

細節與調權重：`scripts/README.md`。網站產生器：`scripts/build_site.py`（純 Python，無 npm）。

## 上線（一次性，Cloudflare Pages）
1. 建私有 repo 並推上去：
   ```bash
   gh repo create blockchain-vault --private --source=. --push
   ```
2. GitHub repo → Settings → Actions → General → Workflow permissions 勾 **Read and write permissions**（否則 bot 推不上事件卡）。
3. Cloudflare dashboard → Workers & Pages → Create → Pages → **Connect to Git** → 授權並選這個私有 repo：
   - Build command：`pip install feedparser pyyaml markdown && python scripts/build_site.py`
   - Build output directory：`site`
   - 環境變數 `SITE_URL`：設成部署後的網址（例：`https://blockchain-vault.pages.dev`），RSS 的連結才會是絕對網址。第一次部署完拿到網址再回來補，然後 Retry deployment。
4. （可選）Cloudflare Zero Trust → Access → 對這個網域加一條 Application，只允許你的 email（一次性驗證碼登入），網站就只有你看得到。

RSS：網站會產生 `feed.xml`（最新 30 則事件），首頁有 autodiscovery，閱讀器貼網站網址就能訂閱。
若開了 Cloudflare Access，外部 RSS 閱讀器會被擋在登入頁外——要訂閱就得對 `/feed.xml` 另開 bypass 規則，或接受只在本機看。

## Obsidian
Open folder as vault → 選這個資料夾。四個設定：
- Files & Links → Default location for new notes：`00-inbox`
- Templates → Template folder location：`templates`
- Appearance → 開 Graph view
- Community plugins：**Dataview**（`HOME.md` 需要）、**Templater**、**Obsidian Git**（Pull every 60 min，就能收到自動抓的卡）

## 三條紀律（比技術重要）
1. **一張事件卡至少一行「我的判讀」，否則刪掉。** 只有摘要的卡＝書籤，價值等於零。
2. **`20-concepts/` 只能自己寫。** 驗證方式：隨便打開一篇，闔上螢幕講三分鐘。講不出來的，`maturity` 就還是 seed。
3. **每週看一次 `make status`。** 它就是你的學習儀表板。
