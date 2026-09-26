# Blockchain Vault — CLI
# 所有操作都從這裡進。`make` 或 `make help` 看清單。

PY := python3
VAULT := $(CURDIR)
SITE := $(CURDIR)/site

.DEFAULT_GOAL := help

help: ## 顯示所有指令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	 | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## 安裝建站與測試相依
	$(PY) -m pip install --quiet -r requirements-dev.txt
	@echo "✓ 相依安裝完成"

install-news: ## 安裝新聞管線相依（含 CPU 版 torch，約 1 GB）
	$(PY) -m pip install -r requirements-news.txt

check: ## 檢查環境
	@$(PY) --version
	@$(PY) -c "import feedparser, yaml, markdown; print('✓ python 套件齊全')"
	@git --version >/dev/null && echo "✓ git"
	@echo "✓ vault: $(VAULT)"

peek: ## 試抓不送出（看排序、分組、來源健康度）
	$(PY) scripts/fetch_news.py --dry-run --hours 36

peek-week: ## 試抓一週不送出
	$(PY) scripts/fetch_news.py --dry-run --hours 168

calibrate: ## 事件分組門檻校準（需先 make install-news）
	$(PY) scripts/calibrate_clusters.py

test: ## 跑 Python 與 Functions 測試
	$(PY) -m pytest -q
	node --test "tests/js/*.test.js"

build: ## 產生靜態網站到 site/
	$(PY) scripts/build_site.py

serve: build ## 產生後在本機 8080 預覽
	@echo "→ http://localhost:8080"
	@cd $(SITE) && $(PY) -m http.server 8080

status: ## vault 統計
	@$(PY) scripts/status.py

unread: ## 列出未讀事件（分數高者在前）
	@$(PY) scripts/status.py --unread

new-event: ## 手動開一張事件卡：make new-event T="標題"
	@$(PY) scripts/new_note.py event "$(T)"

new-concept: ## 開一篇概念筆記：make new-concept T="名稱"
	@$(PY) scripts/new_note.py concept "$(T)"

publish: ## commit + push（觸發 GitHub Pages 部署）
	@git add -A && git commit -m "vault: $$(date +%Y-%m-%d\ %H:%M)" || echo "無變更"
	@git push

clean: ## 刪除產出的網站
	rm -rf $(SITE)

.PHONY: help install install-news check peek peek-week calibrate test build serve status unread new-event new-concept publish clean
