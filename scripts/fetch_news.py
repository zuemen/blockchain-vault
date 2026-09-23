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
import argparse, datetime as dt, hashlib, html, json, os, re, sys, unicodedata
import socket, time, urllib.parse
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
# feedparser 本身沒有逾時：任一來源不回應就會卡住整批（Actions 上會跑到超時）。統一設 20 秒
socket.setdefaulttimeout(20)
FEED_STATS = {}   # 來源名稱 → (feed 總則數, 時間窗內則數, 錯誤訊息)；dry-run 時印出健康度

TIER_BONUS = {"primary": 4, "trade": 0, "aggregator": -2}

# 必須至少命中一個「核心詞」，否則扣重分。
# 沒有這道閘，監理機關的例行公告（處分、人事、研討會）會靠 tier 加分霸佔榜首。
CORE = ["zk", "零知識", "zero-knowledge", "ssi", "did", "verifiable credential",
        "可驗證憑證", "數位身分", "rwa", "tokeniz*", "tokenis*", "代幣化", "stablecoin", "穩定幣",
        "cbdc", "dvp", "blockchain", "區塊鏈", "distributed ledger", "digital asset",
        "虛擬資產", "數位資產", "settlement asset", "結算資產",
        # 重點追蹤對象：本身就是區塊鏈金融主題，命中即算核心
        "chainlink", "ccip", "kinexys", "fireblocks", "polygon", "polygon id", "privado id",
        "zero knowledge", "zkp", "zkevm", "hyperledger"]
CORE_MISS_PENALTY = -8

# 有些站（動區等）會擋 feedparser 預設 UA，統一用一般瀏覽器 UA
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128 Safari/537.36")

# 摘要尾巴的 RSS 樣板句，存了只是佔空間
BOILERPLATE = [r"The post .{0,200}? appeared first on .{0,80}?\.?$", r"\[?…\]?\s*$",
               r"(Continue|Read) (reading|more).{0,40}$", r"本文.{0,20}(首發|原文)於.{0,40}$"]
SUMMARY_MAX = 600      # 事件卡內容上限（字）

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


def score(title: str, summary: str, tier: str, assume_core: bool = False):
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
    # assume_core：來源本身就是主題查詢（例：Google News「JPMorgan + tokenization」），不再要求命中核心詞
    core_hit = assume_core or any(matches(c, low) for c in CORE)
    # tier 加分只在命中核心主題時才給，否則一手來源的例行公告會蓋掉真正相關的報導
    s += TIER_BONUS.get(tier, 0) if core_hit else CORE_MISS_PENALTY
    return s, hits


def topics_of(hits):
    """把命中的詞歸到我的四大主題。"""
    m = {
        "ZK": ["ZK", "零知識", "zero-knowledge", "zk-proof", "zero knowledge", "ZKP", "zkEVM"],
        "重點機構": ["Chainlink", "CCIP", "Kinexys", "Onyx", "JPMorgan", "J.P. Morgan", "JP Morgan", "摩根大通",
                 "Fidelity", "富達", "BNY", "紐約梅隆", "Fireblocks", "Polygon", "Polygon ID", "Privado ID",
                 "Hyperledger"],
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


def read_frontmatter(text):
    """解析筆記開頭的 YAML frontmatter；壞掉就回傳空 dict。"""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def yq(v) -> str:
    """寫 YAML 用的雙引號字串（JSON 字串即合法 YAML）。
    標題常含冒號（"...project: FT"），不加引號會讓整個 frontmatter 解析失敗。"""
    return json.dumps(str(v), ensure_ascii=False)


def existing_events():
    """已存在的事件卡：回傳 [(標題, 關鍵詞集合)]，供跨日去重。"""
    out = []
    for f in EVENTS.glob("*.md"):
        title = str(read_frontmatter(f.read_text(encoding="utf-8")).get("title") or "").strip()
        if title:
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


def clean_summary(raw: str, title: str = "") -> str:
    """RSS 摘要轉乾淨純文字：去標籤、解 HTML 實體、去樣板句，在句尾截斷。
    摘要只是標題重述（Google News 就是這樣）時回傳空字串，不存廢話。"""
    # 先解碼再去標籤：反過來的話，編碼過的 &lt;script&gt; 會在解碼後變成真的 HTML 被寫進卡片
    t = re.sub(r"<[^>]+>", " ", html.unescape(raw or ""))
    t = re.sub(r"\s+", " ", t).strip()
    for pat in BOILERPLATE:
        t = re.sub(pat, "", t, flags=re.I).strip()
    if title:
        tl = re.sub(r"\W+", "", title.lower())
        if not t or re.sub(r"\W+", "", t.lower()).startswith(tl[: max(20, len(tl) - 5)]):
            return ""
    if len(t) > SUMMARY_MAX:
        cut = t[:SUMMARY_MAX]
        end = max(cut.rfind(x) for x in ("。", "！", "？", ". ", "! ", "? "))
        t = cut[: end + 1] if end > SUMMARY_MAX // 2 else cut.rstrip() + "…"
    return t


GNEWS_LOCALE = {"en": "hl=en-US&gl=US&ceid=US:en", "tw": "hl=zh-TW&gl=TW&ceid=TW:zh-Hant"}


def gnews_url(query: str, lang: str, hours: int) -> str:
    """Google News 搜尋 RSS：一次涵蓋數千家媒體。when:Nd 限定時間窗，跟 --hours 對齊。"""
    days = max(1, -(-hours // 24))
    return (f"https://news.google.com/rss/search?q={urllib.parse.quote(f'{query} when:{days}d')}"
            f"&{GNEWS_LOCALE.get(lang, GNEWS_LOCALE['en'])}")


def collect(hours):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    items = []
    for tier in ("primary", "trade", "aggregator"):
        for src in CFG.get(tier, []):
            t0 = time.monotonic()
            gnews = "query" in src          # aggregator 用關鍵字查詢，不寫死網址
            url = gnews_url(src["query"], src.get("lang", "en"), hours) if gnews else src["url"]
            try:
                fp = feedparser.parse(url, agent=UA)
            except Exception as e:
                print(f"  ! {src['name']} 抓取失敗：{e}", file=sys.stderr)
                FEED_STATS[src["name"]] = (0, 0, str(e))
                continue
            status = fp.get("status")
            err = f"HTTP {status}" if status and status >= 400 else ""
            if not fp.entries and fp.get("bozo"):
                err = err or f"解析失敗：{fp.get('bozo_exception')}"
            in_window = 0
            for e in fp.entries:
                st = e.get("published_parsed") or e.get("updated_parsed")
                if st:
                    when = dt.datetime(*st[:6], tzinfo=dt.timezone.utc)
                    if when < cutoff:
                        continue
                else:
                    when = dt.datetime.now(dt.timezone.utc)
                in_window += 1
                title = html.unescape((e.get("title") or "").strip())
                source = src["name"]
                if gnews:
                    # Google News 標題結尾是「 - 媒體名」，拿掉才能跟其他來源去重；來源改記真正的媒體
                    outlet = (e.get("source") or {}).get("title") or ""
                    if outlet and title.endswith(f" - {outlet}"):
                        title = title[: -len(outlet) - 3].strip()
                    source = f"{outlet}（{src['name']}）" if outlet else src["name"]
                summary = clean_summary(e.get("summary", ""), title)
                sc, hits = score(title, summary, tier, src.get("assume_core", False))
                items.append(dict(title=title, url=e.get("link", ""), source=source,
                                  tier=tier, when=when.astimezone(TZ), score=sc,
                                  hits=hits, summary=summary.strip()))
            secs = time.monotonic() - t0
            if secs > 10:                          # 慢來源標出來，方便決定去留
                err = (err + " " if err else "") + f"慢 {secs:.0f}s"
            FEED_STATS[src["name"]] = (len(fp.entries), in_window, err)
    # 事件級去重：不同媒體報導同一件事只留一則，保留分數高者（等於優先一手來源）
    return sorted(dedup(items), key=lambda x: -x["score"])


def write_event(it):
    date = it["when"].date().isoformat()
    path = EVENTS / f"{date}-{slugify(it['title'])}.md"
    if path.exists():
        return None
    topics = ", ".join(topics_of(it["hits"]))
    # 只存連結與內容：entities／判讀等人工欄位由人寫筆記時再加，自動卡不預留空殼
    body = f"""---
type: event
date: {date}
title: {yq(it['title'])}
source_url: {yq(it['url'])}
source_name: {yq(it['source'])}
source_tier: {it['tier']}
topics: [{topics}]
score: {it['score']}
status: unread
auto: true
---
"""
    if it["summary"]:
        body += f"\n## 內容\n{it['summary']}\n"
    path.write_text(body, encoding="utf-8")
    return path


def rescore_existing(dry_run=False):
    """用目前的 score() 重算自動卡的分數。

    評分規則改過之後（例如加了雜訊詞扣分），舊卡的 score 還是舊值，頭版排序會失真。
    只動 auto: true 的卡、只改 score 那一行；標題取 title，摘要取「事實」段落。
    """
    changed = 0
    for f in sorted(EVENTS.glob("*.md")):
        txt = f.read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
        if not fm or not re.search(r"^auto:\s*true\s*$", fm.group(1), re.M):
            continue
        meta = read_frontmatter(txt)
        title_s = str(meta.get("title") or "").strip()
        tier_s = str(meta.get("source_tier") or "trade")
        old = re.search(r"^score:\s*(-?\d+)", fm.group(1), re.M)
        facts = re.search(r"^## (?:內容|事實)[^\n]*\n(.*?)(?=^##\s|\Z)", txt, re.S | re.M)
        summary = re.sub(r"^\s*-\s*", "", facts.group(1).strip(), flags=re.M) if facts else ""
        if not (title_s and old):
            continue
        new, _ = score(title_s, summary, tier_s, tier_s == "aggregator")
        if new != int(old.group(1)):
            changed += 1
            print(f"  {int(old.group(1)):>3} → {new:>3}  {title_s[:56]}")
            if not dry_run:
                head = fm.group(1)
                head = re.sub(r"^score:\s*-?\d+", f"score: {new}", head, count=1, flags=re.M)
                f.write_text(txt.replace(fm.group(1), head, 1), encoding="utf-8")
    print(f"{'（試算）' if dry_run else ''}共 {changed} 張卡分數有變動")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=36)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--min-score", type=int, default=3,
                    help="低於此分數不開事件卡（預設 3：至少命中一個核心主題且非宣傳稿）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rescore", action="store_true",
                    help="用目前的評分規則重算 10-events/ 裡自動卡（auto: true）的 score，不抓新聞")
    a = ap.parse_args()
    if a.rescore:
        rescore_existing(a.dry_run)
        return

    seen = existing_events()
    fresh, skipped = [], []
    for it in collect(a.hours):
        # 跟已存在的事件卡比對，同一事件就不再開新卡
        match = next((t for t, tk in seen if same_event(it["tokens"], tk)), None)
        (skipped if match else fresh).append((it, match))
    # 分數門檻：數量上限拉高後，靠門檻擋掉偏題與宣傳稿
    below = [it for it, _ in fresh if it["score"] < a.min_score]
    items = [it for it, _ in fresh if it["score"] >= a.min_score][: a.top]
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
        if below:
            print(f"\n（低於 {a.min_score} 分、不開卡：{len(below)} 則）")
        print(f"\n── 來源健康度（feed 總則數／{a.hours} 小時內）──")
        for name, (total, win, err) in FEED_STATS.items():
            flag = "✗ 抓不到" if total == 0 else ("· 時間窗內無新文" if win == 0 else "✓")
            print(f"  {flag:<10} {name:<24} {total:>3}／{win:<3} {err}")
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
