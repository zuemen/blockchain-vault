# 發佈成網站（Quartz 4）

Obsidian vault 是純 markdown，發佈幾乎零成本。

```bash
git clone https://github.com/jackyzha0/quartz.git site
cd site && npm install
# 把 vault 內容放進 content/（或做 symlink）
ln -s ../.. content
npx quartz build --serve     # 本機預覽 http://localhost:8080
```

`quartz.config.ts` 建議調整：
- `baseUrl`: `zuemen.net/vault` 或 `<user>.github.io/blockchain-vault`
- 開啟 `Plugin.Graph()`（關係圖）、`Plugin.Backlinks()`、`Plugin.Search()`
- **排除不想公開的資料夾**：`ignorePatterns: ["00-inbox", "99-daily", "60-outputs"]`
  （日報週報與工作中的內部備註不要公開）

部署：GitHub Pages（Quartz 內建 workflow）。

## 手機
Quartz 產出的是響應式靜態站，直接「加到主畫面」就有 app 體感。
離線要寫筆記則用 Obsidian 手機版 + Obsidian Sync 或 iCloud／Git。
