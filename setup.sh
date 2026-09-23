#!/usr/bin/env bash
# 一鍵落地。用法： bash setup.sh
set -euo pipefail

cd "$(dirname "$0")"
VAULT="$(pwd)"
echo "▸ Vault: $VAULT"

# 1. Python
command -v python3 >/dev/null || { echo "✗ 找不到 python3。Mac: brew install python3"; exit 1; }
echo "▸ $(python3 --version)"

# 2. 相依套件
echo "▸ 安裝 python 套件…"
python3 -m pip install --quiet --upgrade feedparser pyyaml markdown 2>/dev/null \
  || python3 -m pip install --quiet --upgrade --break-system-packages feedparser pyyaml markdown
python3 -c "import feedparser, yaml, markdown" && echo "  ✓ feedparser / pyyaml / markdown"

# 3. git
if [ ! -d .git ]; then
  git init -q && git add -A && git commit -qm "init vault" && echo "▸ git repo 已建立"
else
  echo "▸ git repo 已存在"
fi

# 4. 首次試抓（不寫檔）
echo "▸ 試抓最近 36 小時（不寫檔）…"
python3 scripts/fetch_news.py --dry-run --hours 36 || echo "  （抓取失敗不影響後續，檢查網路或 feeds.yaml）"

# 5. 首次建站
echo "▸ 產生網站…"
python3 scripts/build_site.py

cat <<'TXT'

──────────────────────────────────────────────
完成。接下來：

  make help          看所有指令
  make peek          試抓，只看排序（建議先跑一週）
  make update        抓取 + 重建網站
  make serve         本機預覽 http://localhost:8080

Obsidian：Open folder as vault → 選這個資料夾
啟動頁設成 HOME.md（Settings → Appearance 或直接 pin）

上線（GitHub Pages）：
  gh repo create blockchain-vault --private --source=. --push
  repo → Settings → Pages → Source 選 "GitHub Actions"
  repo → Settings → Actions → General → 勾 "Read and write permissions"
──────────────────────────────────────────────
TXT
