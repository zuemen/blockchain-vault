#!/usr/bin/env python3
"""把 10-events/ 的舊自動卡（auto: true）匯入 D1（spec §10 第 3 步）。

不呼叫 AI，沿用卡上的摘要（summary_by='rss'）。可重跑：已匯入的網址算重複，不會重複寫入。
卡片檔案這一階段不刪，階段 3 新聞頁改讀 D1 之後才刪。

用法：
    python scripts/import_legacy.py --dry-run     # 只列出會送什麼
    python scripts/import_legacy.py               # 需要 SITE_URL、INGEST_TOKEN
"""
import argparse
import datetime as dt
import re
import sys
import urllib.parse
from pathlib import Path

import clustering
from fetch_news import prepare_payload, print_report
from ingest_client import ApiError, client_from_env
from news_utils import detect_lang, normalize_url, utc_iso
from notes import is_legacy_auto, iter_notes
from taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parent.parent
TPE = dt.timezone(dt.timedelta(hours=8))
GN_SOURCE = re.compile(r"^(.*)（(GN .+)）$")      # WIP 分支的格式：「Reuters（GN Chainlink）」
LOOKBACK_DAYS = 60                                # 比對既有分組的範圍：要涵蓋最舊的卡


def legacy_summary(body: str) -> str:
    m = re.search(r"^## (?:內容|事實)[^\n]*\n(.*?)(?=^##\s|\Z)", body, re.S | re.M)
    if not m:
        return ""
    t = re.sub(r"^\s*-\s*", "", m.group(1).strip(), flags=re.M).strip()
    return "" if t in ("", "（待填）") else t[:2000]


def card_to_item(note):
    """舊自動卡 → 新聞 dict；缺網址、標題或日期回傳 None。"""
    fm = note.fm
    url = str(fm.get("source_url") or "").strip()
    title = str(fm.get("title") or "").strip()
    try:
        day = dt.date.fromisoformat(str(fm.get("date")))
    except ValueError:
        return None
    if not url.startswith(("http://", "https://")) or not title:
        return None
    src = str(fm.get("source_name") or "").strip() or "unknown"
    m = GN_SOURCE.match(src)
    outlet, feed = (m.group(1), m.group(2)) if m else (src, src)
    tier = fm.get("source_tier") if fm.get("source_tier") in ("primary", "trade", "aggregator") else "trade"
    score = fm.get("score") if isinstance(fm.get("score"), int) else 0
    return {"title": title, "url": url, "url_canonical": normalize_url(url),
            "url_resolved": 0 if urllib.parse.urlsplit(url).netloc.endswith("news.google.com") else 1,
            "outlet": outlet, "source_feed": feed, "tier": tier, "lang": detect_lang(title),
            "published_at": utc_iso(dt.datetime.combine(day, dt.time(0), TPE)),
            "rss_summary": legacy_summary(note.body), "score": score}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tax = load_taxonomy()
    cards = [n for n in iter_notes(ROOT, ("10-events",)) if n.error or is_legacy_auto(n)]
    items, bad = [], []
    for n in cards:
        it = None if n.error else card_to_item(n)
        (items.append(it) if it else bad.append(f"{n.path.name}：{n.error or '缺網址、標題或日期'}"))
    print(f"舊自動卡 {len(cards)} 張，可匯入 {len(items)} 張，無法匯入 {len(bad)} 張")
    for b in bad:
        print(f"  ! {b}")

    client = client_from_env(required=not a.dry_run)
    try:
        existing = client.recent(LOOKBACK_DAYS) if client else []
    except ApiError as e:
        sys.exit(f"讀取既有新聞失敗：{e}")
    embed = clustering.load_embedder(tax["clustering"]["model"])
    # 資料庫已有的網址不送（prepare_payload 會濾掉），所以重跑時 payload 只剩沒匯入過的
    payload = prepare_payload(items, existing, tax, embed, "import", limit=False)
    already = len(items) - len(payload)
    print_report(payload, {}, 0, "語意模型" if embed else "標題 Jaccard")
    if a.dry_run or not payload:
        print(f"\n資料庫已有 {already} 張，待送 {len(payload)} 張")
        return

    r = client.ingest(payload, run_id="import-legacy", skip_ai=True)
    print(f"\n寫入 {r['inserted']}、重複 {r['duplicates']}、欄位錯誤 {len(r['errors'])}、失敗批次 {r['failed_batches']}")
    for err in r["errors"]:
        print(f"  ! {err}", file=sys.stderr)
    if r["inserted"] + r["duplicates"] != len(payload) or r["failed_batches"]:
        sys.exit("數量對不上：寫入＋重複 ≠ 待送張數，請看上面的錯誤")
    print(f"✓ 全部 {len(items)} 張已在 D1（本次寫入 {r['inserted']}，先前已有 {already + r['duplicates']}）")


if __name__ == "__main__":
    main()
