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
