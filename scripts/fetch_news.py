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
        "可驗證憑證", "數位身分", "rwa", "tokeniz*", "tokenis*", "代幣化", "stablecoin", "穩定幣",
        "cbdc", "dvp", "blockchain", "區塊鏈", "distributed ledger", "digital asset",
        "虛擬資產", "數位資產", "settlement asset", "結算資產"]
CORE_MISS_PENALTY = -8

# 雜訊詞（活動宣傳、空投等）每命中一個扣分；清單在 feeds.yaml 的 noise
NOISE_PENALTY = -6

# 事件級去重：標題關鍵詞集合的 Jaccard 相似度 >= 此值視為同一事件。
# 用真實資料校準過：不同媒體報導同一事件，標題相似度多落在 0.36–0.50，
# 設 0.5 會漏掉大半；0.35 以上的配對實測全是真重複。可在 feeds.yaml 用 dedup_threshold 覆寫。
DEDUP_THRESHOLD = float(CFG.get("dedup_threshold", 0.35))

# 正規化時去掉的雜訊詞（不代表事件內容）
TITLE_NOISE = ["news", "breaking", "exclusive", "update", "report", "報導", "快訊",
               "獨家", "最新", "消息", "新聞"]
# 英文停用詞：功能詞不算關鍵詞，否則會稀釋相似度
STOPWORDS = {"a", "an", "the", "to", "of", "for", "in", "on", "and", "or", "with", "as",
             "by", "at", "from", "is", "are", "be", "its", "it", "s", "into", "over",
             "after", "via", "new", "says", "said", "will", "could", "may", "than"}
STEM_LEN = 5          # 英文字截前 5 字母當粗略詞幹：tokenized/tokenised/tokenization → token


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
        (["代幣化", "tokeniz*", "tokenis*"], ["結算", "settle*", "dvp", "cbdc"], 4),
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

    # 雜訊詞：活動宣傳稿、空投等，每命中一個扣分（宣傳詞越多越像宣傳稿）
    noise_hits = [n for n in CFG.get("noise", []) if matches(n, low)]
    s += NOISE_PENALTY * len(noise_hits)
    core_hit = any(matches(c, low) for c in CORE)
    # tier 加分只在命中核心主題時才給，否則一手來源的例行公告會蓋掉真正相關的報導
    s += TIER_BONUS.get(tier, 0) if core_hit else CORE_MISS_PENALTY
    return s, hits


def topics_of(hits):
    """把命中的詞歸到我的四大主題。"""
    m = {
        "ZK": ["ZK", "零知識", "zero-knowledge", "zk-proof"],
        "SSI": ["SSI", "DID", "verifiable credential", "可驗證憑證", "數位身分"],
        "RWA": ["RWA", "tokeniz", "tokenis", "代幣化", "代幣化存款", "deposit token", "DvP", "settle", "結算"],
        "金融法規": ["regulat", "licens", "法規", "監理", "金管會", "FinCEN", "SEC", "HKMA", "SFC", "BIS"],
        "穩定幣": ["stablecoin", "穩定幣", "CBDC", "wCBDC"],
    }
    out = [t for t, kws in m.items() if any(k in hits for k in kws)]
    return out or ["其他"]


def title_tokens(title: str) -> frozenset:
    """把標題轉成關鍵詞集合：英文取詞幹、中文取 2-gram。

    正規化：NFKC、轉小寫、去掉雜訊詞與所有格 's、去停用詞；
    標點與空白自然被切詞時丟掉。只用標準庫。
    """
    t = unicodedata.normalize("NFKC", title).lower().replace("’", "'")
    for w in TITLE_NOISE:
        t = t.replace(w, " ")
    t = re.sub(r"'s\b", " ", t)
    words = {w[:STEM_LEN] for w in re.findall(r"[a-z0-9]+", t) if w not in STOPWORDS}
    grams = set()
    for run in re.findall(r"[一-鿿]+", t):          # 每段連續中文各自切 2-gram，不跨標點
        grams |= {run[i:i + 2] for i in range(len(run) - 1)} or {run}
    return frozenset(words | grams)


def jaccard(a, b) -> float:
    """兩個集合的 Jaccard 相似度：交集 / 聯集。"""
    return len(a & b) / len(a | b) if (a or b) else 0.0


def same_event(a, b) -> bool:
    return jaccard(a, b) >= DEDUP_THRESHOLD


def existing_events():
    """已存在的事件卡：回傳 [(標題, 關鍵詞集合)]，供跨日去重。"""
    out = []
    for f in EVENTS.glob("*.md"):
        head = f.read_text(encoding="utf-8")[:600]
        mt = re.search(r"^title:\s*(.+)$", head, re.M)
        if mt:
            title = mt.group(1).strip()
            out.append((title, title_tokens(title)))
    return out


def dedup(items):
    """本次抓取內部的事件級去重。

    用 union-find 把相似的報導串成同一群（A 像 B、B 像 C 時三者同群），
    每群保留分數最高者；同分時一手來源優先。其餘報導記在 dupes 供 dry-run 檢視。
    """
    toks = [title_tokens(it["title"]) for it in items]
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if same_event(toks[i], toks[j]):
                parent[find(i)] = find(j)

    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for idx in groups.values():
        idx.sort(key=lambda i: (-items[i]["score"], items[i]["tier"] != "primary"))
        keep = dict(items[idx[0]], tokens=toks[idx[0]])
        keep["dupes"] = [items[i] for i in idx[1:]]
        out.append(keep)
    return out


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
    # 事件級去重：不同媒體報導同一件事只留一則，保留分數高者（等於優先一手來源）
    return sorted(dedup(items), key=lambda x: -x["score"])


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

    seen = existing_events()
    fresh, skipped = [], []
    for it in collect(a.hours):
        # 跟已存在的事件卡比對，同一事件就不再開新卡
        match = next((t for t, tk in seen if same_event(it["tokens"], tk)), None)
        (skipped if match else fresh).append((it, match))
    items = [it for it, _ in fresh][: a.top]
    today = dt.datetime.now(TZ).date().isoformat()

    lines = []
    for it in items:
        if a.dry_run:
            print(f"[{it['score']:>2}] {it['tier']:<7} {it['title'][:70]}")
            for d in it["dupes"]:                      # 被合併的同事件報導
                print(f"       ↳ 合併 [{d['score']:>2}] {d['source'][:14]:<14} {d['title'][:52]}")
            continue
        p = write_event(it)
        if p:
            reason = "、".join(it["hits"][:4]) or "無明確命中"
            tag = "**一手來源**｜" if it["tier"] == "primary" else ""
            lines.append(f"- [[{p.stem}]] — score {it['score']} — {tag}命中：{reason}")

    if a.dry_run:
        if skipped:
            print(f"\n── 已有事件卡、略過 {len(skipped)} 則 ──")
            for it, match in skipped:
                print(f"[{it['score']:>2}] {it['title'][:48]}  ≈ 既有：{match[:30]}")
                for d in it["dupes"]:
                    print(f"       ↳ 合併 [{d['score']:>2}] {d['source'][:14]:<14} {d['title'][:52]}")
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
