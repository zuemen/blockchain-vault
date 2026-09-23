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
1. 建私有 repo 並推上去（已完成：`zuemen/blockchain-vault`）：
   ```bash
   gh repo create blockchain-vault --private --source=. --push
   ```
2. GitHub repo → Settings → Actions → General → Workflow permissions 勾 **Read and write permissions**（否則 bot 推不上事件卡）。
3. Cloudflare dashboard → Workers & Pages → Create → Pages → **Connect to Git** → 授權 GitHub 並選 `zuemen/blockchain-vault`，設定值：

   | 欄位 | 值 |
   |---|---|
   | Production branch | `main` |
   | Framework preset | **None** |
   | Build command | `python -m pip install pyyaml markdown && python scripts/build_site.py` |
   | Build output directory | `site` |
   | Root directory | 留空 |
   | 環境變數 `PYTHON_VERSION` | `3.12`（鎖定版本，不受 Cloudflare 預設版本變動影響；程式在 3.10 以上都能跑） |
   | 環境變數 `SITE_URL` | 第一次先**不設**；部署完拿到網址後再補（見第 4 步） |

   Build command 只裝 `pyyaml markdown`：建站用不到 `feedparser`（那是抓新聞用的，在 Actions 上裝）。
   用 `python -m pip` 而不是 `pip`，確保套件裝進 `PYTHON_VERSION` 指定的那個 Python。
4. **第一次部署完成後**：拿到網址（例：`https://blockchain-vault.pages.dev`）→ Settings → Variables and Secrets → 加 `SITE_URL`（**結尾不要斜線**，程式會自動去掉但仍建議不加）→ Deployments → 最新一筆 **Retry deployment**。
   不補的話網站照常運作，只是 `feed.xml` 裡的連結是相對路徑，RSS 閱讀器點不開。
5. （可選）只讓自己看得到：Cloudflare Zero Trust → Access → Applications → Add → **Self-hosted**
   - Domain：`blockchain-vault.pages.dev`，**再加一條** `*.blockchain-vault.pages.dev`（每次部署的預覽網址長這樣，不擋的話筆記一樣會外流）
   - Policy：Action **Allow**，Include → Emails → 你的 email（登入方式：One-time PIN）
6. （開了第 5 步才需要）讓 RSS 能訂閱：再建一個 Self-hosted application
   - Domain：`blockchain-vault.pages.dev`，Path：`feed.xml`
   - Policy：Action **Bypass**，Include → **Everyone**
   - 路徑較精確的 application 優先，所以只有 `/feed.xml` 公開，其餘頁面仍需登入。
   - 代價：事件標題與「一句話」會公開（RSS 本來就包含這些）。不能接受就別開 bypass，只在網站上看。

RSS：網站會產生 `feed.xml`（最新 30 則事件），各頁都有 autodiscovery，閱讀器貼網站網址就能訂閱。

## 各國進度（tracker.html）
國家 × 議題的矩陣，回答「同一件事在各國走到哪一步」。規則全在 `scripts/tracker.py`（國家、議題、關鍵詞、階段對照）。

| 階段 | 意思 | status 裡出現這些字就自動判定 |
|---|---|---|
| 1 研議 | 諮詢、研究、評估 | 研議、研究、評估、諮詢 |
| 2 草案 | 提案、草案、預告 | 提案、草案、預告、徵詢 |
| 3 已通過 | 已立法／核定，待子法或施行 | 三讀、通過、公布、簽署、核定 |
| 4 施行中 | 已生效，或主管機關發布可依循的規範 | 生效、施行、實施、釋義、指引、開放、試辦 |
| 5 市場運作 | 已有業者實際上線 | 上線、營運中、商轉 |

- **階段只來自 `40-regulations/` 的法規筆記**：`jurisdiction` 決定國家，標題＋`topics` 決定議題，`status` 換算階段。
  判斷不準時在 frontmatter 直接寫 `stage: 4`、`tracks: [穩定幣, 結算／存款代幣]` 覆寫。
- **事件卡只當動態**：依來源機構、標題（含主要業者名稱，如 SoFi → 美國）、內文機構名自動歸類，不會改階段。
- 格子沒有法規筆記時顯示「動態觀察」——那就是該補法規筆記的地方：
  `python scripts/new_note.py regulation "美國-穩定幣法案"`

## 留言（Pages Functions + D1）
網址只分享給朋友，所以設計成**簡單可靠優先**：不做 Turnstile、不做速率限制、不記錄 IP。
不用 giscus／utterances（兩者都要求 repo 公開）或 Disqus（廣告與追蹤）。

```
瀏覽器（site/assets/app.js）──fetch──▶ /api/comments*（functions/，Cloudflare Pages Functions）──▶ D1（binding：DB）
```

| 檔案 | 作用 |
|---|---|
| `functions/api/comments/index.js` | `GET ?slug=` 該篇留言（時間正序）、`POST` 新增 |
| `functions/api/comments/recent.js` | `GET` 全站最近 10 筆，附筆記標題（從網站自己的 `search.json` 對照） |
| `functions/api/comments/[id].js` | `DELETE` 刪一則，需 `x-admin-token` |
| `functions/_lib.js` | 共用工具（不是路由） |
| `db/schema.sql` | D1 資料表，建一次 |

- `functions/` 必須在 **repo 根目錄**（官方文件：放在專案根目錄，不是靜態輸出目錄），不用複製進 `site/`。Cloudflare 會在每次 build 時自動編譯。
- **repo 根目錄不要放 `wrangler.toml`**：有它的話 Cloudflare 會以它為準，蓋掉 dashboard 上的 bindings 與變數。
- 限制：內容必填、1000 字；暱稱 40 字（空的存 null，顯示「訪客」）；評分 1–5 可省略，評的是「這篇判讀」。只收網站上存在的筆記 slug。
- 安全：前端一律用 `textContent` 插入留言，**不用 innerHTML**。
- 本機 `run serve` 沒有 `/api`，留言區會顯示「留言功能僅在線上版可用」。

### 刪留言
先在網頁上找到留言的 id（或查 API），再帶 token 刪：

```bash
# 查某篇的留言與 id（slug＝檔名去掉 .md，中文要 URL 編碼）
curl -s "https://blockchain-vault-cvm.pages.dev/api/comments?slug=2026-09-08-fincen-vdc-cip-faq"

# 刪 id 12
curl -X DELETE https://blockchain-vault-cvm.pages.dev/api/comments/12 \
  -H "x-admin-token: <你的 ADMIN_TOKEN>"
# → {"deleted":12}；token 錯 403，id 不存在 404
```

PowerShell 版：`Invoke-RestMethod -Method Delete -Uri https://blockchain-vault-cvm.pages.dev/api/comments/12 -Headers @{"x-admin-token"="<token>"}`

也可以直接在 Cloudflare D1 Console 下 SQL：`DELETE FROM comments WHERE id = 12;`

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
