#!/usr/bin/env python3
"""
每日抓取 → 去重 → 評分 → 寫入 vault。
只寫 10-events/ 與 99-daily/，不碰 20-concepts/（概念筆記自己寫）。

用法：
    python3 scripts/fetch_news.py                # 抓最近 36 小時
    python3 scripts/fetch_news.py --hours 72     # 週一補週末
    python3 scripts/fetch_news.py --top 5        # 只留前 5 則
    python3 scripts/fetch_news.py --dry-run      # 只印不寫檔

相依：pip install feedparser pyyaml
"""
import argparse, datetime as dt, hashlib, os, re, sys, unicodedata
from pathlib import Path

try:
    import feedparser, yaml
except ImportError:
    sys.exit("請先安裝：pip install feedparser pyyaml")

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "10-events"
DAILY = ROOT / "99-daily"
CFG = yaml.safe_load((Path(__file__).parent / "feeds.yaml").read_text(encoding="utf-8"))
TZ = dt.timezone(dt.timedelta(hours=8))          # Asia/Taipei

TIER_BONUS = {"primary": 4, "trade": 0, "aggregator": -2}

# 必須至少命中一個「核心詞」，否則扣重分。
# 沒有這道閘，監理機關的例行公告（處分、人事、研討會）會靠 tier 加分霸佔榜首。
CORE = ["zk", "零知識", "zero-knowledge", "ssi", "did", "verifiable credential",
        "可驗證憑證", "數位身分", "rwa", "tokeniz*", "代幣化", "stablecoin", "穩定幣",
        "cbdc", "dvp", "blockchain", "區塊鏈", "distributed ledger", "digital asset",
        "虛擬資產", "數位資產", "settlement asset", "結算資產"]
CORE_MISS_PENALTY = -8


def slugify(title: str) -> str:
    """保留中日韓字元，其餘轉 kebab-case。"""
    t = unicodedata.normalize("NFKC", title).lower()
    t = re.sub(r"[^\w一-鿿]+", "-", t).strip("-")
    return t[:60] or hashlib.md5(title.encode()).hexdigest()[:8]


def matches(kw: str, low: str) -> bool:
    """ASCII 關鍵字用單字邊界，CJK 用子字串。

    關鍵詞尾端加 * 表示字根，只放寬右邊界（tokeniz* 命中 tokenized、
    tokenization）。沒加 * 的維持雙邊界，這是必要的防護——否則
    "SSI" 會命中 "Commission"、"SEC" 會命中 "Securities"，
    監理機關的例行公告會霸佔榜首。
    """
    k = kw.lower()
    stem = k.endswith("*")
    if stem:
        k = k[:-1]
    if re.fullmatch(r"[a-z0-9\-\. ]+", k):
        right = "" if stem else r"(?![a-z0-9])"
        return re.search(rf"(?<![a-z0-9]){re.escape(k)}{right}", low) is not None
    return k in low


def score(title: str, summary: str, tier: str):
    """標題命中加倍，並對主題組合額外加分——讓分數真的有區分度。"""
    t, sm = title.lower(), summary.lower()
    hits, s = [], 0
    for kw, w in CFG["weights"].items():
        in_t, in_s = matches(kw, t), matches(kw, sm)
        if in_t or in_s:
            s += w * 2 if in_t else w      # 標題命中加倍
            hits.append(kw.rstrip("*"))   # 去掉字根標記，清單才乾淨

    # 主題組合加分：兩組詞同時出現才是真正要找的訊號，單獨出現只是背景雜訊
    low = f"{t} {sm}"
    combos = [
        (["代幣化", "tokeniz*"], ["結算", "settle*", "dvp", "cbdc"], 4),
        (["穩定幣", "stablecoin"], ["法規", "監理", "regulat*", "licence", "license"], 3),
        (["ssi", "did", "verifiable credential", "可驗證憑證", "數位身分"],
         ["kyc", "aml", "法規", "監理", "regulat*"], 4),
        (["zk", "零知識", "zero-knowledge"],
         ["身分", "identity", "隱私", "privacy", "compliance", "法遵"], 4),
        (["rwa", "代幣化"],
         ["基金", "fund", "債券", "bond", "黃金", "gold", "存款", "deposit"], 3),
    ]
    for a, b, bonus in combos:
        if any(matches(x, low) for x in a) and any(matches(y, low) for y in b):
            s += bonus

    s = min(s, 20)                          # 上限 20
    core_hit = any(matches(c, low) for c in CORE)
    # tier 加分只在命中核心主題時才給，否則一手來源的例行公告會蓋掉真正相關的報導
    s += TIER_BONUS.get(tier, 0) if core_hit else CORE_MISS_PENALTY
    return s, hits


def topics_of(hits):
    """把命中的詞歸到我的四大主題。"""
    m = {
        "ZK": ["ZK", "零知識", "zero-knowledge", "zk-proof"],
        "SSI": ["SSI", "DID", "verifiable credential", "可驗證憑證", "數位身分"],
        "RWA": ["RWA", "tokeniz", "代幣化", "代幣化存款", "deposit token", "DvP", "settle", "結算"],
        "金融法規": ["regulat", "licens", "法規", "監理", "金管會", "FinCEN", "SEC", "HKMA", "SFC", "BIS"],
        "穩定幣": ["stablecoin", "穩定幣", "CBDC", "wCBDC"],
    }
    out = [t for t, kws in m.items() if any(k in hits for k in kws)]
    return out or ["其他"]


def existing_keys():
    """已存在的事件：用標題前 20 字去重。"""
    keys = set()
    for f in EVENTS.glob("*.md"):
        head = f.read_text(encoding="utf-8")[:600]
        mt = re.search(r"^title:\s*(.+)$", head, re.M)
        if mt:
            keys.add(mt.group(1).strip()[:20])
    return keys


def collect(hours):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    items = []
    for tier in ("primary", "trade"):
        for src in CFG.get(tier, []):
            try:
                fp = feedparser.parse(src["url"])
            except Exception as e:
                print(f"  ! {src['name']} 抓取失敗：{e}", file=sys.stderr)
                continue
            for e in fp.entries:
                st = e.get("published_parsed") or e.get("updated_parsed")
                if st:
                    when = dt.datetime(*st[:6], tzinfo=dt.timezone.utc)
                    if when < cutoff:
                        continue
                else:
                    when = dt.datetime.now(dt.timezone.utc)
                title = (e.get("title") or "").strip()
                summary = re.sub(r"<[^>]+>", " ", e.get("summary", ""))[:800]
                sc, hits = score(title, summary, tier)
                items.append(dict(title=title, url=e.get("link", ""), source=src["name"],
                                  tier=tier, when=when.astimezone(TZ), score=sc,
                                  hits=hits, summary=summary.strip()))
    # 同標題去重，保留分數高者（等於優先一手來源）
    best = {}
    for it in items:
        k = it["title"][:20]
        if k not in best or it["score"] > best[k]["score"]:
            best[k] = it
    return sorted(best.values(), key=lambda x: -x["score"])


def write_event(it):
    date = it["when"].date().isoformat()
    path = EVENTS / f"{date}-{slugify(it['title'])}.md"
    if path.exists():
        return None
    topics = ", ".join(topics_of(it["hits"]))
    body = f"""---
type: event
date: {date}
title: {it['title']}
source_url: {it['url']}
source_name: {it['source']}
source_tier: {it['tier']}
topics: [{topics}]
entities: []
regulations: []
concepts: []
score: {it['score']}
status: unread
used_in: []
auto: true
keyword_hits: [{", ".join(it['hits'][:8])}]
---

## 一句話
（待填）

## 事實（只放可查證的）
- {it['summary'][:300]}

## 我的判讀
-

## 未解
-
"""
    path.write_text(body, encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=36)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    seen = existing_keys()
    items = [i for i in collect(a.hours) if i["title"][:20] not in seen][: a.top]
    today = dt.datetime.now(TZ).date().isoformat()

    lines = []
    for it in items:
        if a.dry_run:
            print(f"[{it['score']:>2}] {it['tier']:<7} {it['title'][:70]}")
            continue
        p = write_event(it)
        if p:
            reason = "、".join(it["hits"][:4]) or "無明確命中"
            tag = "**一手來源**｜" if it["tier"] == "primary" else ""
            lines.append(f"- [[{p.stem}]] — score {it['score']} — {tag}命中：{reason}")

    if a.dry_run:
        return

    dpath = DAILY / f"{today}.md"
    if not dpath.exists():
        dpath.write_text(f"---\ntype: daily\ndate: {today}\n---\n\n## 今天抓到的\n\n## 我想到的\n-\n\n## 要展開的概念\n-\n",
                         encoding="utf-8")
    txt = dpath.read_text(encoding="utf-8")
    block = "\n".join(lines) if lines else "- （今天沒有新命中）"
    txt = txt.replace("## 今天抓到的\n", f"## 今天抓到的\n{block}\n", 1)
    dpath.write_text(txt, encoding="utf-8")
    print(f"寫入 {len(lines)} 則事件卡，已更新 {dpath.name}")


if __name__ == "__main__":
    main()
