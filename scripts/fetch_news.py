#!/usr/bin/env python3
"""
每日新聞管線：抓取 → 評分 → 解轉址 → 正規化 → 去重 → 分組 → 取上限 → 標記 → 抓原文 → 送 /api/ingest。
新聞寫進 D1，不再寫 repo（spec §6.1）。

用法：
    python scripts/fetch_news.py --dry-run          # 只印排名、分組、來源健康度，不送出
    python scripts/fetch_news.py --hours 72         # 週一補週末

環境變數：SITE_URL、INGEST_TOKEN（正式執行必填；dry-run 有的話會拿來比對既有新聞）
相依：pip install -r requirements-news.txt
"""
import argparse
import datetime as dt
import html
import os
import socket
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import feedparser
import yaml

import clustering
from ingest_client import ApiError, client_from_env
from news_utils import clean_summary, detect_lang, normalize_url, utc_iso
from scoring import score
from tagging import note_terms, tags_for
from taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parent.parent
FEEDS = Path(__file__).parent / "feeds.yaml"
TIERS = ("primary", "trade", "aggregator")
CONTENT_MAX = 1500
# 有些站會擋 feedparser 預設 UA
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128 Safari/537.36")
GNEWS_LOCALE = {"en": "hl=en-US&gl=US&ceid=US:en", "tw": "hl=zh-TW&gl=TW&ceid=TW:zh-Hant"}
# feedparser 沒有逾時：任一來源不回應就會卡住整批
socket.setdefaulttimeout(20)


def gnews_url(query: str, lang: str, hours: int) -> str:
    """Google News 搜尋 RSS。when:Nd 限定時間窗，跟 --hours 對齊。"""
    days = max(1, -(-hours // 24))
    return (f"https://news.google.com/rss/search?q={urllib.parse.quote(f'{query} when:{days}d')}"
            f"&{GNEWS_LOCALE.get(lang, GNEWS_LOCALE['en'])}")


def parse_entry(e, src: dict, tier: str, sc: dict, cutoff: dt.datetime, now: dt.datetime):
    """一則 RSS 項目 → 新聞 dict；網址或標題不合格、或早於 cutoff 就回傳 None。"""
    link = (e.get("link") or "").strip()
    title = html.unescape((e.get("title") or "").strip())
    if not link.startswith(("http://", "https://")) or not title:
        return None
    st = e.get("published_parsed") or e.get("updated_parsed")
    when = dt.datetime(*st[:6], tzinfo=dt.timezone.utc) if st else now
    if when < cutoff:
        return None
    outlet = src["name"]
    if "query" in src:
        # Google News 標題結尾是「 - 媒體名」，拿掉才能跟其他來源比對；outlet 記真正的媒體
        real = (e.get("source") or {}).get("title") or ""
        if real and title.endswith(f" - {real}"):
            title = title[: -len(real) - 3].strip()
        outlet = real or src["name"]
    summary = clean_summary(e.get("summary", ""), title)
    s, hits = score(title, summary, tier, sc, src.get("assume_core", False))
    return {"title": title, "url": link, "url_resolved": 1, "outlet": outlet,
            "source_feed": src["name"], "tier": tier, "lang": detect_lang(title),
            "published_at": utc_iso(when), "rss_summary": summary, "score": s, "hits": hits}


def collect(hours: int, cfg: dict, sc: dict):
    """回傳 (新聞清單, 來源健康度 {名稱: (feed 總則數, 時間窗內則數, 錯誤)})。單一來源失敗就略過。"""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=hours)
    items, stats = [], {}
    for tier in TIERS:
        for src in cfg.get(tier) or []:
            t0 = time.monotonic()
            url = gnews_url(src["query"], src.get("lang", "en"), hours) if "query" in src else src["url"]
            try:
                fp = feedparser.parse(url, agent=UA)
            except Exception as e:
                stats[src["name"]] = (0, 0, str(e))
                continue
            err = f"HTTP {fp.get('status')}" if (fp.get("status") or 0) >= 400 else ""
            if not fp.entries and fp.get("bozo"):
                err = err or f"解析失敗：{fp.get('bozo_exception')}"
            got = [x for x in (parse_entry(e, src, tier, sc, cutoff, now) for e in fp.entries) if x]
            items += got
            secs = time.monotonic() - t0
            if secs > 10:
                err = (err + " " if err else "") + f"慢 {secs:.0f}s"
            stats[src["name"]] = (len(fp.entries), len(got), err)
    return items, stats


def decode_gnews(items):
    """Google News 轉址批次解碼。失敗就保留轉址並標 url_resolved=0。"""
    targets = [it for it in items if urllib.parse.urlsplit(it["url"]).netloc.endswith("news.google.com")]
    if not targets:
        return
    for it in targets:
        it["url_resolved"] = 0
    try:
        from googlenewsdecoder import gnewsdecoder
        results = gnewsdecoder([it["url"] for it in targets])
    except Exception as e:
        print(f"  ! Google News 轉址解碼失敗，保留轉址：{e}", file=sys.stderr)
        return
    for it, r in zip(targets, results):
        if r.get("success") and r.get("decoded_url"):
            it["url"] = r["decoded_url"]
            it["url_resolved"] = 1


def dedupe_urls(items):
    """同一網址只留分數最高的一則。"""
    best = {}
    for it in items:
        k = it["url_canonical"]
        if k not in best or it["score"] > best[k]["score"]:
            best[k] = it
    return list(best.values())


def to_payload(it: dict, ref, tags: list, added_by: str) -> dict:
    return {"url_canonical": it["url_canonical"], "url_original": it["url"], "url_resolved": it["url_resolved"],
            "title": it["title"], "outlet": it["outlet"], "source_feed": it["source_feed"], "tier": it["tier"],
            "lang": it["lang"], "published_at": it["published_at"], "score": it["score"],
            "rss_summary": it["rss_summary"], "cluster_ref": ref, "added_by": added_by, "tags": tags}


def prepare_payload(items, existing, tax, embed, added_by, limit=True, root=ROOT):
    """去掉資料庫已有的網址 → 分組 →（limit 時）取上限 → 標記，回傳要送出的 payload 清單。"""
    known = {e["url_canonical"] for e in existing}
    fresh = dedupe_urls([it for it in items if it["url_canonical"] not in known])
    cl = tax["clustering"]
    refs = clustering.assign_clusters(fresh, existing, embed, cl["threshold"], cl["jaccard_fallback"])
    chosen = clustering.apply_limit(fresh, refs, tax["limits"]["daily_top"]) if limit else list(zip(fresh, refs))
    terms = note_terms(root)
    return [to_payload(it, ref, tags_for(it, tax, terms), added_by) for it, ref in chosen]


def fetch_content(url: str) -> str:
    """抓原文取正文前 1,500 字；被擋、逾時、解析不出來都回傳空字串（改用 RSS 摘要）。"""
    try:
        req = urllib.request.Request(url, headers={"user-agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            page = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        import trafilatura
        return (trafilatura.extract(page) or "")[:CONTENT_MAX]
    except Exception:
        return ""


def add_content(payload):
    with ThreadPoolExecutor(max_workers=8) as ex:
        texts = ex.map(lambda p: fetch_content(p["url_original"]) if p["url_resolved"] else "", payload)
        for p, text in zip(payload, texts):
            p["content"] = text


def print_report(payload, stats, hours, method):
    groups = {}
    for p in payload:
        groups.setdefault(p["cluster_ref"], []).append(p)
    ordered = sorted(groups.items(), key=lambda kv: -max(p["score"] for p in kv[1]))
    print(f"── 送出 {len(payload)} 則，{len(groups)} 個分組（分組方法：{method}）──")
    for ref, ps in ordered:
        ps.sort(key=lambda p: -p["score"])
        where = "併入既有分組 #" + str(ref) if isinstance(ref, int) else "新分組"
        lead = ps[0]
        print(f"[{lead['score']:>2}] {lead['tier']:<10} {lead['title'][:70]}  〔{where}〕")
        for p in ps[1:]:
            print(f"       ↳ [{p['score']:>2}] {p['outlet'][:14]:<14} {p['title'][:52]}")
        tags = ", ".join(f"{t['kind']}:{t['key']}" for t in lead["tags"])
        if tags:
            print(f"       標記：{tags}")
    print(f"\n── 來源健康度（feed 總則數／{hours} 小時內）──")
    for name, (total, win, err) in stats.items():
        flag = "✗ 抓不到" if total == 0 else ("· 無新文" if win == 0 else "✓")
        print(f"  {flag:<8} {name:<28} {total:>3}／{win:<3} {err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=36)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tax = load_taxonomy()
    cfg = yaml.safe_load(FEEDS.read_text(encoding="utf-8"))
    items, stats = collect(a.hours, cfg, tax["scoring"])
    kept = [it for it in items if it["score"] >= tax["limits"]["min_score"]]
    decode_gnews(kept)
    for it in kept:
        it["url_canonical"] = normalize_url(it["url"])

    client = client_from_env(required=not a.dry_run)
    try:
        existing = client.recent(tax["clustering"]["window_days"]) if client else []
    except ApiError as e:
        sys.exit(f"讀取既有新聞失敗，中止（不寫半套）：{e}")

    embed = clustering.load_embedder(tax["clustering"]["model"])
    payload = prepare_payload(kept, existing, tax, embed, "bot")
    method = "語意模型" if embed else "標題 Jaccard（模型載入失敗）"
    print(f"抓到 {len(items)} 則，{len(kept)} 則達 {tax['limits']['min_score']} 分，"
          f"資料庫已有 {len(existing)} 則")
    print_report(payload, stats, a.hours, method)
    if a.dry_run or not payload:
        return

    add_content(payload)
    run_id = os.environ.get("GITHUB_RUN_ID") or dt.datetime.now().strftime("local-%Y%m%d%H%M%S")
    r = client.ingest(payload, run_id)
    print(f"\n寫入 {r['inserted']}、重複 {r['duplicates']}、AI 失敗 {r['ai_failed']}、"
          f"欄位錯誤 {len(r['errors'])}、失敗批次 {r['failed_batches']}")
    for err in r["errors"]:
        print(f"  ! {err}", file=sys.stderr)
    if r["failed_batches"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
