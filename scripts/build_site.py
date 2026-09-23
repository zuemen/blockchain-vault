#!/usr/bin/env python3
"""把 vault 建成靜態網站（純 Python，無 npm）。

產出：site/index.html、site/n/<slug>.html、site/search.json、site/feed.xml、site/assets/*
公開：10-events / 20-concepts / 30-entities / 40-regulations / 50-maps
不公開：00-inbox、99-daily（每日筆記）、60-outputs（日報週報）、templates、scripts

用法： python3 scripts/build_site.py
"""
import html as html_lib, json, os, re, shutil, sys, urllib.parse
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml, markdown
except ImportError:
    sys.exit("請先安裝：pip install pyyaml markdown")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"
TZ = timezone(timedelta(hours=8))

PUBLIC_DIRS = {
    "10-events": ("事件", "event"),
    "20-concepts": ("概念", "concept"),
    "30-entities": ("機構", "entity"),
    "40-regulations": ("法規", "regulation"),
    "50-maps": ("地圖", "moc"),
}
SITE_TITLE = "Blockchain Vault"
SITE_DESC = "ZK · SSI · RWA · 金融法規 — 每日自動抓取，人工判讀"
# 站台網址（例：https://blockchain-vault.pages.dev）。沒設就用相對路徑，RSS 連結會是 n/<slug>.html
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
FEED_SIZE = 30                                   # RSS 最多收幾則事件

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
DV_RE = re.compile(r"```dataview.*?```", re.S)


def slugify(name: str) -> str:
    return re.sub(r"\s+", "-", name.strip())


def url_for(slug: str) -> str:
    return "n/" + urllib.parse.quote(slug) + ".html"


def parse(path: Path):
    raw = path.read_text(encoding="utf-8")
    fm, body = {}, raw
    m = FM_RE.match(raw)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        body = raw[m.end():]
    return fm, body


def clean_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    out = []
    for x in v:
        s = str(x).strip()
        s = re.sub(r"^\[\[|\]\]$", "", s).strip('"').strip("'")
        if s:
            out.append(s)
    return out


def collect():
    notes = {}
    for d, (label, kind) in PUBLIC_DIRS.items():
        for f in sorted((ROOT / d).glob("*.md")):
            fm, body = parse(f)
            slug = f.stem
            notes[slug] = dict(
                slug=slug, path=f, folder=d, folder_label=label, kind=fm.get("type", kind),
                title=str(fm.get("title") or slug.replace("-", " ")),
                date=str(fm.get("date") or fm.get("updated") or ""),
                topics=clean_list(fm.get("topics")),
                source_name=fm.get("source_name", ""), source_url=fm.get("source_url", ""),
                source_tier=fm.get("source_tier", ""), score=fm.get("score", ""),
                maturity=fm.get("maturity", ""), jurisdiction=fm.get("jurisdiction", ""),
                regulator=fm.get("regulator", ""), status=fm.get("status", ""),
                body=body, links=[], backlinks=[],
            )
    return notes


def resolve_links(notes):
    by_name = {}
    for n in notes.values():
        by_name[n["slug"].lower()] = n["slug"]
        by_name[n["title"].lower()] = n["slug"]

    def render_body(note):
        body = strip_empty_sections(DV_RE.sub("", note["body"]))

        def sub(m):
            target, alias = m.group(1).strip(), (m.group(2) or "").strip()
            text = alias or target
            hit = by_name.get(target.lower())
            if hit:
                if hit not in note["links"] and hit != note["slug"]:
                    note["links"].append(hit)
                return f'<a class="wl" href="../{url_for(hit)}">{text}</a>'
            return f'<span class="wl-miss" title="尚未建立">{text}</span>'

        body = WIKI_RE.sub(sub, body)
        return markdown.markdown(body, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])

    for n in notes.values():
        n["html"] = render_body(n)
    for n in notes.values():
        for t in n["links"]:
            if n["slug"] not in notes[t]["backlinks"]:
                notes[t]["backlinks"].append(n["slug"])
    return notes


def esc(v):
    """HTML 跳脫：標題可能來自 RSS，含 < & 等字元。"""
    return html_lib.escape(str(v), quote=True)


# 空段落：標題底下只有「-」或「（待填）」——自動抓的事件卡骨架，網站上不顯示
EMPTY_SECTION_RE = re.compile(r"^##[^\n]*\n(?:[ \t]*(?:-|（待填）)?[ \t]*\n)*(?=^##\s|\Z)", re.M)


def strip_empty_sections(body):
    return EMPTY_SECTION_RE.sub("", body.rstrip() + "\n")


def excerpt(note, k=150):
    """純文字摘要：先拿掉標題（h1–h6）再去標籤，避免摘要開頭是「一句話 事實…」這種段落名。"""
    txt = re.sub(r"<h[1-6][^>]*>.*?</h[1-6]>", " ", note["html"], flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = html_lib.unescape(re.sub(r"\s+", " ", txt)).strip()
    return txt[:k] + ("…" if len(txt) > k else "")


def lede(note):
    """「一句話」段落的內容；沒填回傳空字串。"""
    m = re.search(r"^##\s*一句話\s*\n(.*?)(?=^##\s|\Z)", note["body"], re.S | re.M)
    txt = m.group(1).strip() if m else ""
    txt = WIKI_RE.sub(lambda w: w.group(2) or w.group(1), txt)
    txt = re.sub(r"[*_`]", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return "" if (not txt or txt.startswith("（待填") or txt == "-") else txt


def summary(note, k=120):
    """卡片用的一段話：優先「一句話」，否則用內文摘要。"""
    s = lede(note)
    if s:
        return s[:k] + ("…" if len(s) > k else "")
    return excerpt(note, k)


def score_of(n):
    try:
        return int(n["score"])
    except (TypeError, ValueError):
        return 5          # 手寫筆記沒有 score，視為中等


TIER_LABEL = {"primary": "一手來源", "trade": "產業媒體", "aggregator": "彙整"}
WEEKDAY = "一二三四五六日"


def signal(score):
    """訊號條：分數 0–20 對應 5 格。"""
    lit = max(0, min(5, round(score / 4)))
    bars = "".join(f'<i class="{"on" if i < lit else ""}"></i>' for i in range(5))
    return f'<span class="signal" title="訊號分數 {score}"><span class="bars">{bars}</span>{score}</span>'


def kicker(n):
    """標題上方的小標：主題＋一手章。"""
    bits = [f'<span class="k-topic">{esc(t)}</span>' for t in n["topics"][:3]]
    if not bits:
        bits.append(f'<span class="k-topic">{esc(n["folder_label"])}</span>')
    seal = '<span class="seal">一手</span>' if n["source_tier"] == "primary" else ""
    return f'<p class="kicker">{seal}{"".join(bits)}</p>'


def source_link(n, cls="src"):
    if not n["source_url"]:
        return ""
    return (f'<a class="{cls}" href="{esc(n["source_url"])}" target="_blank" rel="noopener">'
            f'{esc(n["source_name"] or "來源")} ↗</a>')


def shell(title, body, depth=0, desc=SITE_DESC, masthead=False):
    up = "../" * depth
    now = datetime.now(TZ)
    if masthead:
        top = f"""<header class="masthead">
  <div class="mh-rule"></div>
  <div class="mh-meta"><span>{now.year} 年 {now.month} 月 {now.day} 日 星期{WEEKDAY[now.weekday()]}</span>
    <span class="mh-issue">{{ISSUE}}</span><span>每日 07:00 更新</span></div>
  <h1 class="mh-title"><a href="{up}index.html">Blockchain <em>Vault</em></a></h1>
  <p class="mh-tag">鏈上金融的監理與基礎設施 — 自動抓取，人工判讀</p>
  <div class="mh-rule double"></div>
</header>"""
    else:
        top = f"""<header class="bar">
  <a class="bar-brand" href="{up}index.html">Blockchain <em>Vault</em></a>
  <span class="bar-tag">ZK · SSI · RWA · 金融法規</span>
</header>"""
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{esc(desc)}">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&family=Newsreader:wght@400;600;800&family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@400;600;900&display=swap">
<link rel="stylesheet" href="{up}assets/style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_TITLE} — 事件" href="{up}feed.xml">
</head>
<body>
{top}
<main>
{body}
</main>
<footer class="colophon">
  <div class="mh-rule"></div>
  <p><span>Blockchain <em>Vault</em></span>
     <span>事件卡由腳本抓取骨架，判讀與概念筆記為人工撰寫</span>
     <span>最後更新 {now.strftime('%Y-%m-%d %H:%M')}（台北）</span>
     <span><a href="{up}feed.xml">訂閱 RSS</a></span></p>
</footer>
<script src="{up}assets/app.js"></script>
</body>
</html>
"""


def build_index(notes):
    events = [n for n in notes.values() if n["folder"] == "10-events"]
    by_title = lambda x: x["title"]
    concepts = sorted([n for n in notes.values() if n["folder"] == "20-concepts"], key=by_title)
    entities = sorted([n for n in notes.values() if n["folder"] == "30-entities"], key=by_title)
    regs = sorted([n for n in notes.values() if n["folder"] == "40-regulations"], key=by_title)
    mocs = sorted([n for n in notes.values() if n["folder"] == "50-maps"], key=by_title)

    # 頭版只放正分事件；負分（活動宣傳、偏題）仍有個別頁面、可搜尋，但不上頭版
    live = sorted([n for n in events if score_of(n) >= 0],
                  key=lambda x: (x["date"], score_of(x)), reverse=True)
    window = live[:30]                                   # 最近 30 則當「本期」
    ranked = sorted(window, key=lambda x: (score_of(x), x["date"]), reverse=True)
    lead = ranked[0] if ranked else None
    seconds = ranked[1:4]
    used = {n["slug"] for n in ranked[:4]}
    briefs = [n for n in window if n["slug"] not in used]

    all_topics = sorted({t for n in notes.values() for t in n["topics"]})
    chips = "".join(f'<button class="filter" data-topic="{esc(t)}">{esc(t)}</button>' for t in all_topics)

    def lead_html(n):
        return f"""<article class="lead rise" style="--i:0">
  {kicker(n)}
  <h2 class="lead-h"><a href="{url_for(n['slug'])}">{esc(n['title'])}</a></h2>
  <p class="lead-deck">{esc(summary(n, 220))}</p>
  <p class="byline"><time>{esc(n['date'])}</time>{source_link(n)}{signal(score_of(n))}</p>
</article>"""

    def second_html(n, i):
        return f"""<article class="story rise" style="--i:{i}">
  {kicker(n)}
  <h3><a href="{url_for(n['slug'])}">{esc(n['title'])}</a></h3>
  <p class="deck">{esc(summary(n, 110))}</p>
  <p class="byline"><time>{esc(n['date'][5:])}</time>{source_link(n)}{signal(score_of(n))}</p>
</article>"""

    def brief_html(n):
        seal = '<span class="seal sm">一手</span>' if n["source_tier"] == "primary" else ""
        return (f'<li><time>{esc(n["date"][5:])}</time>'
                f'<a href="{url_for(n["slug"])}">{seal}{esc(n["title"])}</a>'
                f'<span class="b-src">{esc(n["source_name"])}{signal(score_of(n))}</span></li>')

    def index_col(title, items, fmt):
        if not items:
            return ""
        lis = "".join(f"<li>{fmt(n)}</li>" for n in items)
        return f'<section class="idx-col"><h3>{title}<span>{len(items)}</span></h3><ul>{lis}</ul></section>'

    link = lambda n: f'<a href="{url_for(n["slug"])}">{esc(n["title"])}</a>'
    concept_fmt = lambda n: link(n) + (f'<span class="mat mat-{esc(n["maturity"])}">{esc(n["maturity"])}</span>' if n["maturity"] else "")
    reg_fmt = lambda n: link(n) + (f'<span class="mat">{esc(n["jurisdiction"])}</span>' if n["jurisdiction"] else "")

    n_primary = sum(1 for n in window if n["source_tier"] == "primary")
    front = ""
    if lead:
        front = f"""
<div class="front">
  <div class="front-main">
    {lead_html(lead)}
    <div class="seconds">{''.join(second_html(n, i + 1) for i, n in enumerate(seconds))}</div>
  </div>
  <aside class="rail">
    <section class="rail-box">
      <h3>本期</h3>
      <p class="stat"><b>{len(window)}</b> 則事件　<b>{n_primary}</b> 則一手</p>
      <p class="stat-note">分數＝主題關鍵詞＋組合訊號；一手來源加權。10 分以上值得細讀。</p>
    </section>
    <section class="rail-box" id="recent-comments">
      <h3>最近留言</h3>
      <p class="note c-status">載入中…</p>
      <ul class="linklist c-recent"></ul>
    </section>
    {f'<section class="rail-box"><h3>主題地圖</h3><ul class="rail-list">{"".join(f"<li>{link(n)}</li>" for n in mocs)}</ul></section>' if mocs else ""}
  </aside>
</div>"""

    body = f"""
<nav class="toolbar">
  <div class="filters"><button class="filter active" data-topic="">全部</button>{chips}</div>
  <input id="q" type="search" placeholder="搜尋標題、內容、主題…" autocomplete="off">
</nav>
<div id="results" class="hidden"></div>

<div id="main-view">
{front}
  <section class="briefs">
    <h2 class="sec-h"><span>簡訊</span></h2>
    <ul>{''.join(brief_html(n) for n in briefs)}</ul>
  </section>

  <section class="index">
    <h2 class="sec-h"><span>索引</span></h2>
    <div class="idx-grid">
      {index_col("概念", concepts, concept_fmt)}
      {index_col("法規追蹤", regs, reg_fmt)}
      {index_col("機構", entities, link)}
    </div>
  </section>
</div>
"""
    first = min((n["date"] for n in events if n["date"]), default="")
    try:
        issue = (datetime.now(TZ).date() - datetime.strptime(first[:10], "%Y-%m-%d").date()).days + 1
        issue_txt = f"第 {issue} 號"
    except ValueError:
        issue_txt = ""
    page = shell(SITE_TITLE, body, 0, masthead=True).replace("{ISSUE}", issue_txt)
    (OUT / "index.html").write_text(page, encoding="utf-8")


def comments_block(slug):
    """筆記頁底部的留言區骨架。內容由 app.js 以 textContent 填入，不在這裡插入任何使用者輸入。"""
    stars = "".join(
        f'<button type="button" class="star" data-v="{i}" aria-label="{i} 顆星" aria-pressed="false">★</button>'
        for i in range(1, 6))
    return f"""<section class="comments" id="comments" data-slug="{html_attr(slug)}">
  <h2 class="sec-h"><span>留言</span></h2>
  <p class="note c-status">載入中…</p>
  <ol class="c-list"></ol>
  <form class="c-form" hidden>
    <p class="c-hint">這篇判讀對你有幫助嗎？（選填）</p>
    <div class="stars" role="group" aria-label="評分">{stars}<button type="button" class="star-clear">不評分</button></div>
    <input class="c-name" type="text" maxlength="40" placeholder="暱稱（可空，顯示為訪客）" autocomplete="nickname">
    <textarea class="c-body" maxlength="1000" rows="4" required placeholder="想法、補充、反對意見都歡迎（上限 1000 字）"></textarea>
    <div class="c-actions"><span class="c-count">0 / 1000</span><button type="submit" class="c-submit">送出</button></div>
    <p class="c-msg" role="status"></p>
  </form>
</section>"""


def html_attr(v):
    """屬性值跳脫（slug 可能含引號等字元）。"""
    return (str(v).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def build_notes(notes):
    nd = OUT / "n"
    nd.mkdir(parents=True, exist_ok=True)
    for n in notes.values():
        rel = lambda items, title: (
            f'<section class="rel"><h3>{title}</h3><ul>'
            + "".join(f'<li><a href="../{url_for(s)}">{esc(notes[s]["title"])}</a></li>' for s in items)
            + "</ul></section>") if items else ""

        deck = lede(n)
        prose = n["html"]
        if deck:   # 「一句話」已提到標題下當導言，內文就不重複
            prose = re.sub(r"<h2>\s*一句話\s*</h2>\s*<p>.*?</p>", "", prose, count=1, flags=re.S)

        byline = [f"<time>{esc(n['date'])}</time>"] if n["date"] else []
        if n["source_url"]:
            byline.append(source_link(n))
        if n["folder"] == "10-events" and n["score"] != "":
            byline.append(signal(score_of(n)))
        if n["maturity"]:
            byline.append(f'<span class="mat mat-{esc(n["maturity"])}">{esc(n["maturity"])}</span>')
        if n["jurisdiction"]:
            byline.append(f'<span class="mat">{esc(n["jurisdiction"])}</span>')

        body = f"""
<article class="note">
  <p class="crumb"><a href="../index.html">← 頭版</a><span>{esc(n['folder_label'])}</span></p>
  {kicker(n)}
  <h1>{esc(n['title'])} <span class="c-stat" id="c-stat"></span></h1>
  {f'<p class="note-deck">{esc(deck)}</p>' if deck else ''}
  <p class="byline">{''.join(byline)}</p>
  <div class="prose">{prose}</div>
  <div class="rels">{rel(n["links"], "這篇連出去")}{rel(sorted(n["backlinks"]), "連到這裡的筆記")}</div>
  {comments_block(n['slug'])}
</article>
"""
        (nd / f"{n['slug']}.html").write_text(
            shell(f"{n['title']} — {SITE_TITLE}", body, 1, excerpt(n, 120)), encoding="utf-8")


def build_search(notes):
    idx = []
    for n in notes.values():
        txt = re.sub(r"<[^>]+>", " ", n["html"])
        idx.append(dict(t=n["title"], u=url_for(n["slug"]), k=n["folder_label"],
                        p=n["topics"], d=n["date"],
                        s=re.sub(r"\s+", " ", txt)[:1200]))
    (OUT / "search.json").write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")


CSS = """
/* Blockchain Vault — 晨報版面：米白紙、墨黑字、一抹印章紅 */
:root{
  --paper:#f4efe5; --paper-2:#ebe4d6; --card:#faf7f0;
  --ink:#1c1915; --ink-2:#4b443b; --dim:#877e71; --hair:#d6cdbd; --rule:#1c1915;
  --red:#ae2a1f; --red-soft:#f1dfd6; --green:#2f6b47; --miss:#b3a998;
  /* 舊名稱沿用（搜尋結果、留言區） */
  --bg:var(--paper); --fg:var(--ink); --line:var(--hair); --accent:var(--red); --accent-soft:var(--red-soft);
  --serif:"Newsreader","Noto Serif TC","Songti TC","PMingLiU",serif;
  --sans:"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  --display:"Instrument Serif","Noto Serif TC",serif;
  color-scheme:light dark;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#16140f; --paper-2:#1e1b16; --card:#1b1813;
    --ink:#ece4d4; --ink-2:#c3b9a8; --dim:#8e8577; --hair:#35302a; --rule:#ece4d4;
    --red:#e2694f; --red-soft:#3a221b; --green:#7fb893; --miss:#5d564c;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:15.5px/1.75 var(--sans);
  padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom);
  /* 紙張顆粒 */
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0.5 0 0 0 0 0.45 0 0 0 0 0.4 0 0 0 .055 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
a{color:inherit;text-decoration:none}
a:hover{color:var(--red)}
::selection{background:var(--red);color:var(--paper)}
main{max-width:1180px;margin:0 auto;padding:0 24px}

/* ── 報頭 ── */
.masthead{max-width:1180px;margin:0 auto;padding:22px 24px 0;text-align:center}
.mh-rule{border-top:1px solid var(--rule)}
.mh-rule.double{border-top:3px double var(--rule);margin-top:14px}
.mh-meta{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:7px 0;
  font:500 11.5px/1.4 var(--mono);letter-spacing:.06em;color:var(--ink-2);border-bottom:1px solid var(--hair)}
.mh-issue{color:var(--red)}
.mh-title{font:400 clamp(44px,8.5vw,104px)/.95 var(--display);letter-spacing:-.01em;margin:18px 0 6px}
.mh-title em{font-style:italic;color:var(--red)}
.mh-title a:hover{color:inherit}
.mh-tag{margin:0;font:600 14px/1.5 var(--serif);letter-spacing:.18em;color:var(--ink-2)}

.bar{max-width:1180px;margin:0 auto;padding:16px 24px 12px;display:flex;gap:14px;align-items:baseline;
  flex-wrap:wrap;border-bottom:3px double var(--rule)}
.bar-brand{font:400 30px/1 var(--display)}
.bar-brand em{font-style:italic;color:var(--red)}
.bar-tag{font:500 11.5px var(--mono);letter-spacing:.08em;color:var(--dim)}

/* ── 導覽列：主題＋搜尋 ── */
.toolbar{display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap;
  padding:10px 0;border-bottom:1px solid var(--rule);margin-bottom:26px}
.filters{display:flex;gap:2px;flex-wrap:wrap}
.filter{border:0;background:none;color:var(--ink-2);font:500 13.5px var(--sans);padding:5px 10px;cursor:pointer;
  border-radius:0;position:relative}
.filter:hover{color:var(--red)}
.filter.active{color:var(--ink)}
.filter.active::after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:var(--red)}
#q{flex:0 1 280px;min-width:180px;padding:7px 2px;border:0;border-bottom:1px solid var(--ink-2);background:transparent;
  color:var(--ink);font:15px var(--sans);border-radius:0}
#q:focus{outline:none;border-bottom-color:var(--red)}
#q::placeholder{color:var(--dim)}

/* ── 頭版 ── */
.front{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:0 40px;margin-bottom:34px}
.front-main{min-width:0}
.kicker{margin:0 0 8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;
  font:500 11.5px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--red)}
.k-topic+.k-topic::before{content:"／";margin-right:10px;color:var(--hair)}
.seal{display:inline-block;font:900 11px/1 var(--serif);letter-spacing:.1em;color:var(--red);
  border:1.5px solid var(--red);padding:4px 5px 3px;transform:rotate(-4deg);border-radius:2px}
.seal.sm{font-size:10px;padding:2px 3px 1px;margin-right:6px;vertical-align:2px}
.lead{padding-bottom:26px;border-bottom:1px solid var(--rule)}
.lead-h{font:900 clamp(28px,4vw,46px)/1.22 var(--serif);letter-spacing:-.005em;margin:4px 0 14px;text-wrap:balance}
.lead-deck{font:600 18px/1.75 var(--serif);color:var(--ink-2);margin:0 0 14px;max-width:44em}
.byline{display:flex;gap:6px 14px;align-items:center;flex-wrap:wrap;margin:0;
  font:400 12px/1.5 var(--mono);color:var(--dim)}
.byline .src{color:var(--ink-2);border-bottom:1px solid var(--hair)}
.byline .src:hover{color:var(--red);border-color:var(--red)}
.signal{display:inline-flex;gap:6px;align-items:center;font:500 12px var(--mono);color:var(--ink-2)}
.bars{display:inline-flex;gap:2px;align-items:flex-end}
.bars i{display:block;width:4px;background:var(--hair)}
.bars i:nth-child(1){height:5px}.bars i:nth-child(2){height:7px}.bars i:nth-child(3){height:9px}
.bars i:nth-child(4){height:11px}.bars i:nth-child(5){height:13px}
.bars i.on{background:var(--red)}

.seconds{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}
.story{padding:20px 20px 22px;border-right:1px solid var(--hair)}
.story:first-child{padding-left:0}
.story:last-child{border-right:0;padding-right:0}
.story h3{font:700 19px/1.45 var(--serif);margin:2px 0 10px;text-wrap:pretty}
.story .deck{font-size:13.5px;line-height:1.75;color:var(--ink-2);margin:0 0 12px}

/* 右欄 */
.rail{border-left:1px solid var(--rule);padding-left:24px;min-width:0}
.rail-box{padding:0 0 18px;margin-bottom:18px;border-bottom:1px solid var(--hair)}
.rail-box:last-child{border-bottom:0}
.rail h3,.idx-col h3{font:500 11.5px/1 var(--mono);letter-spacing:.16em;color:var(--red);margin:0 0 12px;
  display:flex;justify-content:space-between}
.idx-col h3 span{color:var(--dim)}
.stat{margin:0;font:600 15px var(--serif)}
.stat b{font:400 34px/1 var(--display);margin-right:2px}
.stat-note{margin:8px 0 0;font-size:12.5px;line-height:1.65;color:var(--dim)}
.rail-list{list-style:none;margin:0;padding:0}
.rail-list li{padding:6px 0;border-top:1px dotted var(--hair);font:600 14px/1.5 var(--serif)}
.rail-list li:first-child{border-top:0;padding-top:0}

/* 區段標題：左右細線夾字 */
.sec-h{display:flex;align-items:center;gap:14px;margin:0 0 14px;font:500 11.5px/1 var(--mono);
  letter-spacing:.24em;color:var(--ink)}
.sec-h::before,.sec-h::after{content:"";flex:1;border-top:1px solid var(--rule)}

/* 簡訊 */
.briefs{margin-bottom:40px}
.briefs ul{list-style:none;margin:0;padding:0;columns:2;column-gap:40px;column-rule:1px solid var(--hair)}
.briefs li{break-inside:avoid;display:grid;grid-template-columns:44px minmax(0,1fr);gap:2px 10px;
  padding:10px 0;border-bottom:1px dotted var(--hair)}
.briefs time{font:400 11.5px/1.9 var(--mono);color:var(--dim);grid-row:span 2}
.briefs li a{font:600 15px/1.5 var(--serif)}
.briefs .b-src{font-size:11.5px;color:var(--dim);display:flex;gap:10px}

/* 索引 */
.index{margin-bottom:30px}
.idx-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 34px}
.idx-col ul{list-style:none;margin:0;padding:0}
.idx-col li{display:flex;justify-content:space-between;gap:10px;align-items:baseline;
  padding:7px 0;border-top:1px dotted var(--hair);font:600 14.5px/1.5 var(--serif)}
.mat{font:400 11px var(--mono);color:var(--dim);white-space:nowrap}
.mat-seed{color:#a8741f}.mat-growing{color:var(--green)}.mat-stable{color:var(--ink-2)}

/* 進場動畫 */
.rise{animation:rise .7s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--i,0) * 90ms)}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.rise{animation:none}}

/* ── 搜尋結果（app.js 產生） ── */
.hidden{display:none}
#results{margin-bottom:40px}
.card{padding:14px 0;border-bottom:1px solid var(--hair)}
.card .t{display:block;font:700 18px/1.45 var(--serif);margin-bottom:6px}
.card .x{color:var(--ink-2);font-size:13.5px;margin:6px 0 0}
.m{display:flex;gap:6px;flex-wrap:wrap}
.chip{font:400 11px/1.6 var(--mono);color:var(--dim);border:1px solid var(--hair);padding:0 6px}
.chip.topic{color:var(--red);border-color:transparent;background:var(--red-soft)}
p.note{color:var(--dim);font-size:13px;margin:0 0 10px}

/* ── 筆記頁 ── */
article.note{max-width:720px;margin:30px auto 0}
.crumb{display:flex;gap:12px;margin:0 0 22px;font:400 12px var(--mono);color:var(--dim);letter-spacing:.06em}
.crumb span::before{content:"／";margin-right:12px;color:var(--hair)}
article.note h1{font:900 clamp(28px,4.4vw,42px)/1.28 var(--serif);margin:6px 0 16px;text-wrap:balance}
.c-stat{font:400 12.5px var(--mono);color:var(--dim);white-space:nowrap;vertical-align:middle}
.note-deck{font:600 19px/1.8 var(--serif);color:var(--ink-2);margin:0 0 16px;padding-left:16px;border-left:3px solid var(--red)}
article.note .byline{padding:10px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--hair);margin-bottom:8px}
.prose{font:400 16.5px/1.95 var(--serif);color:var(--ink)}
.prose>p:first-child::first-letter{float:left;font:900 3.3em/.9 var(--serif);margin:.08em .1em 0 0;color:var(--red)}
.prose h2{font:500 12px/1 var(--mono);letter-spacing:.2em;color:var(--red);margin:2.4em 0 .9em;
  display:flex;align-items:center;gap:12px}
.prose h2::after{content:"";flex:1;border-top:1px solid var(--hair)}
.prose h3{font:700 17px var(--serif);margin:1.6em 0 .5em}
.prose ul,.prose ol{padding-left:1.3em}
.prose li{margin:.35em 0}
.prose li::marker{color:var(--red)}
.prose strong{font-weight:900}
.prose a,.wl{color:var(--ink);text-decoration:underline;text-decoration-color:var(--red);text-underline-offset:3px}
.prose a:hover,.wl:hover{color:var(--red)}
.wl-miss{color:var(--dim);border-bottom:1px dotted var(--miss)}
.prose table{border-collapse:collapse;width:100%;font:400 14px/1.6 var(--sans);display:block;overflow-x:auto;margin:1.2em 0}
.prose th,.prose td{border-bottom:1px solid var(--hair);padding:8px 10px;text-align:left;vertical-align:top}
.prose th{font:500 11.5px var(--mono);letter-spacing:.08em;color:var(--dim);border-bottom:1px solid var(--rule)}
.prose code{font:13px var(--mono);background:var(--paper-2);padding:1px 5px}
.prose pre{background:var(--paper-2);padding:14px;overflow-x:auto}
.prose blockquote{margin:1.4em 0;padding:0 0 0 18px;border-left:3px solid var(--red);font-weight:600;color:var(--ink-2)}
.prose img{max-width:100%}
.rels{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:40px 0 10px}
.rel h3{font:500 11.5px var(--mono);letter-spacing:.16em;color:var(--red);margin:0 0 8px}
.rel ul{list-style:none;margin:0;padding:0}
.rel li{padding:6px 0;border-top:1px dotted var(--hair);font:600 14.5px/1.5 var(--serif)}

/* ── 留言 ── */
.comments{margin-top:36px}
.c-list{list-style:none;padding:0;margin:0 0 20px}
.c-item{border-bottom:1px dotted var(--hair);padding:12px 0}
.c-head{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline;font:400 12px var(--mono);color:var(--dim)}
.c-who{font:700 14px var(--serif);color:var(--ink)}
.c-stars{color:var(--red);letter-spacing:1px}
.c-text{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere;font:400 15px/1.85 var(--serif)}
.c-form{display:grid;gap:10px;background:var(--card);border:1px solid var(--rule);padding:18px;box-shadow:4px 4px 0 var(--paper-2)}
.c-form[hidden]{display:none}   /* display:grid 會蓋掉 hidden 屬性，要明寫 */
.c-hint{margin:0;font:600 15px var(--serif)}
.stars{display:flex;gap:2px;align-items:center;flex-wrap:wrap}
.star{background:none;border:0;padding:4px 3px;font-size:25px;line-height:1;color:var(--miss);cursor:pointer;min-width:34px;min-height:34px}
.star.on{color:var(--red)}
.star:focus-visible,.star-clear:focus-visible{outline:2px solid var(--red)}
.star-clear{background:none;border:0;color:var(--dim);font:12px var(--mono);cursor:pointer;margin-left:8px;text-decoration:underline}
.c-name,.c-body{width:100%;padding:10px 12px;border:1px solid var(--hair);border-radius:0;
  background:var(--paper);color:var(--ink);font:16px/1.6 var(--sans)}
.c-body{resize:vertical;min-height:100px}
.c-name:focus,.c-body:focus{outline:none;border-color:var(--red)}
.c-actions{display:flex;justify-content:space-between;align-items:center;gap:10px}
.c-count{font:12px var(--mono);color:var(--dim)}
.c-submit{background:var(--ink);color:var(--paper);border:0;border-radius:0;padding:9px 22px;font:700 14px var(--sans);
  letter-spacing:.2em;cursor:pointer}
.c-submit:hover{background:var(--red)}
.c-submit:disabled{opacity:.5;cursor:default}
.c-msg{margin:0;font:12.5px var(--mono);color:var(--dim);min-height:1em}
.c-msg.err{color:var(--red)}
/* 首頁右欄的最近留言 */
.linklist{list-style:none;margin:0;padding:0}
.c-recent li{padding:8px 0;border-top:1px dotted var(--hair);display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline}
.c-recent li:first-child{border-top:0;padding-top:0}
.c-recent .c-who{font-size:13px}
.c-recent a{font:600 13.5px/1.5 var(--serif)}
.c-recent .c-excerpt{flex-basis:100%;font-size:12.5px;color:var(--dim)}

/* ── 頁尾 ── */
.colophon{max-width:1180px;margin:50px auto 0;padding:0 24px 30px}
.colophon p{display:flex;gap:8px 22px;flex-wrap:wrap;margin:10px 0 0;font:400 11.5px var(--mono);color:var(--dim)}
.colophon p span:first-child{font:400 17px/1 var(--display);color:var(--ink)}
.colophon em{color:var(--red)}
.colophon a{border-bottom:1px solid var(--hair)}

/* ── 響應式 ── */
@media (max-width:980px){
  .front{grid-template-columns:1fr}
  .rail{border-left:0;padding-left:0;border-top:3px double var(--rule);padding-top:18px;margin-top:6px;
    display:grid;grid-template-columns:1fr 1fr;gap:0 28px}
  .rail-box:last-child{border-bottom:1px solid var(--hair)}
}
@media (max-width:720px){
  main,.masthead,.bar,.colophon{padding-left:16px;padding-right:16px}
  .mh-meta{justify-content:center;font-size:10.5px}
  .mh-meta span:last-child{display:none}
  .mh-tag{font-size:12px;letter-spacing:.1em}
  .toolbar{flex-direction:column;align-items:stretch}
  .filters{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin:0 -16px;padding:0 10px}
  .filters::-webkit-scrollbar{display:none}
  .filter{white-space:nowrap}
  #q{flex:1 1 auto;width:100%}
  .seconds{grid-template-columns:1fr}
  .story,.story:first-child,.story:last-child{padding:18px 0;border-right:0;border-bottom:1px solid var(--hair)}
  .rail{grid-template-columns:1fr}
  .briefs ul{columns:1}
  .idx-grid{grid-template-columns:1fr;gap:18px}
  .rels{grid-template-columns:1fr}
  .lead-deck{font-size:16.5px}
  .prose{font-size:16px}
}
"""

JS = """
(async function(){
  const q=document.getElementById('q');
  if(!q) return;
  const res=document.getElementById('results');
  const main=document.getElementById('main-view');
  let idx=[]; let topic='';
  try{ idx=await (await fetch('search.json')).json(); }catch(e){}

  const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function render(list){
    if(!list.length){ res.innerHTML='<p class="note">沒有符合的筆記。</p>'; return; }
    res.innerHTML=list.slice(0,60).map(n=>`
      <article class="card">
        <a class="t" href="${esc(n.u)}">${esc(n.t)}</a>
        <div class="m"><span class="chip">${esc(n.k)}</span>${n.d?`<span class="chip date">${esc(n.d)}</span>`:''}
        ${(n.p||[]).map(p=>`<span class="chip topic">${esc(p)}</span>`).join('')}</div>
        <p class="x">${esc((n.s||'').slice(0,150))}</p>
      </article>`).join('');
  }
  function apply(){
    const s=q.value.trim().toLowerCase();
    if(!s && !topic){ res.classList.add('hidden'); main.classList.remove('hidden'); return; }
    let list=idx;
    if(topic) list=list.filter(n=>(n.p||[]).includes(topic));
    if(s) list=list.filter(n=>(n.t+' '+(n.p||[]).join(' ')+' '+(n.s||'')).toLowerCase().includes(s));
    render(list); res.classList.remove('hidden'); main.classList.add('hidden');
  }
  q.addEventListener('input',apply);
  document.querySelectorAll('.filter').forEach(b=>b.addEventListener('click',()=>{
    document.querySelectorAll('.filter').forEach(x=>x.classList.remove('active'));
    b.classList.add('active'); topic=b.dataset.topic||''; apply();
  }));
})();

/* ── 留言 ──────────────────────────────────────────────
   安全：使用者輸入（暱稱、內容、標題）一律用 textContent 插入，絕不用 innerHTML。
   降級：本機 python http.server 沒有 /api，逾時或非 JSON 回應時顯示一行提示，不轉圈。 */
(function(){
  const OFFLINE='留言功能僅在線上版可用';
  // 帶逾時的 JSON 請求；回應不是 JSON（例如本機 404 頁）就丟錯
  async function api(path,opts){
    const ctl=new AbortController(); const t=setTimeout(()=>ctl.abort(),6000);
    try{
      const r=await fetch(path,Object.assign({signal:ctl.signal,headers:{'content-type':'application/json'}},opts||{}));
      const ct=r.headers.get('content-type')||'';
      if(!ct.includes('application/json')) throw new Error('offline');
      const data=await r.json();
      if(!r.ok) throw new Error(data.error||('HTTP '+r.status));
      return data;
    }finally{ clearTimeout(t); }
  }
  function el(tag,cls,text){ const e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; return e; }
  const fmt=iso=>{ try{ return new Date(iso).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}); }catch(e){ return iso; } };
  const starStr=n=>'★'.repeat(n)+'☆'.repeat(5-n);
  const clip=(s,k)=>{ const a=[...s]; return a.length>k? a.slice(0,k).join('')+'…' : s; };

  // ── 筆記頁 ──
  const box=document.getElementById('comments');
  if(box){
    const slug=box.dataset.slug;
    const status=box.querySelector('.c-status'), list=box.querySelector('.c-list'), form=box.querySelector('.c-form');
    const stat=document.getElementById('c-stat');
    const nameI=form.querySelector('.c-name'), bodyI=form.querySelector('.c-body');
    const count=form.querySelector('.c-count'), msg=form.querySelector('.c-msg'), submit=form.querySelector('.c-submit');
    const stars=[...form.querySelectorAll('.star')];
    let rating=null, comments=[];

    function item(c){
      const li=el('li','c-item'), head=el('div','c-head');
      head.append(el('span','c-who',c.name||'訪客'), el('time',null,fmt(c.created_at)));
      if(c.rating){ const s=el('span','c-stars',starStr(c.rating)); s.setAttribute('aria-label',c.rating+' 顆星'); head.append(s); }
      li.append(head, el('p','c-text',c.body));
      return li;
    }
    function renderStat(){
      const rated=comments.filter(c=>c.rating);
      let t=comments.length? comments.length+' 則留言' : '';
      if(rated.length){ const avg=rated.reduce((a,c)=>a+c.rating,0)/rated.length; t+=' · 平均 ★'+avg.toFixed(1); }
      stat.textContent=t;
    }
    function render(){
      list.replaceChildren(...comments.map(item));
      status.textContent=comments.length? '' : '還沒有留言，來當第一個。';
      status.hidden=comments.length>0;
      renderStat();
    }
    function setRating(v){
      rating=v;
      stars.forEach(b=>{ const on=v!=null && Number(b.dataset.v)<=v; b.classList.toggle('on',on); b.setAttribute('aria-pressed',String(Number(b.dataset.v)===v)); });
    }
    stars.forEach(b=>b.addEventListener('click',()=>setRating(Number(b.dataset.v))));
    form.querySelector('.star-clear').addEventListener('click',()=>setRating(null));
    bodyI.addEventListener('input',()=>{ count.textContent=[...bodyI.value].length+' / 1000'; });

    form.addEventListener('submit',async ev=>{
      ev.preventDefault();
      const body=bodyI.value.trim();
      if(!body){ msg.textContent='內容不能是空的'; msg.className='c-msg err'; return; }
      submit.disabled=true; msg.className='c-msg'; msg.textContent='送出中…';
      try{
        const d=await api('/api/comments',{method:'POST',body:JSON.stringify({slug,name:nameI.value,body,rating})});
        comments.push(d.comment); render();
        bodyI.value=''; count.textContent='0 / 1000'; setRating(null);
        msg.textContent='已送出，謝謝！';
      }catch(e){
        msg.className='c-msg err';
        msg.textContent= e.message==='offline'||e.name==='AbortError' ? OFFLINE : '送出失敗：'+e.message;
      }finally{ submit.disabled=false; }
    });

    api('/api/comments?slug='+encodeURIComponent(slug))
      .then(d=>{ comments=d.comments||[]; render(); form.hidden=false; })
      .catch(()=>{ status.textContent=OFFLINE; });   // 表單維持隱藏，不顯示壞掉的畫面
  }

  // ── 首頁：最近留言 ──
  const recent=document.getElementById('recent-comments');
  if(recent){
    const status=recent.querySelector('.c-status'), ul=recent.querySelector('.c-recent');
    api('/api/comments/recent').then(d=>{
      const cs=d.comments||[];
      if(!cs.length){ status.textContent='還沒有留言。'; return; }
      status.hidden=true;
      ul.replaceChildren(...cs.map(c=>{
        const li=el('li'), a=el('a',null,c.title||c.slug);
        a.href='n/'+encodeURIComponent(c.slug)+'.html';
        li.append(el('span','c-who',c.name||'訪客'), a, el('span','c-excerpt',clip(c.body,40)));
        return li;
      }));
    }).catch(()=>{ status.textContent=OFFLINE; });
  }
})();
"""


def one_liner(note):
    """抓事件卡的「一句話」段落；沒填（或還是「（待填）」）就退回 excerpt。"""
    m = re.search(r"^##\s*一句話\s*\n(.*?)(?=^##\s|\Z)", note["body"], re.S | re.M)
    txt = m.group(1).strip() if m else ""
    txt = WIKI_RE.sub(lambda w: w.group(2) or w.group(1), txt)   # [[連結|別名]] → 純文字
    txt = re.sub(r"[*_`]", "", txt)                              # 去掉 markdown 強調符號
    txt = re.sub(r"\s+", " ", txt).strip()
    if not txt or txt.startswith("（待填"):
        return excerpt(note, 200)
    return txt


def rfc822(date_str):
    """把 frontmatter 的 YYYY-MM-DD 轉成 RFC 822（台北時間 00:00）；解析失敗回傳 None。"""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=TZ)
    except ValueError:
        return None
    return format_datetime(d)


def build_feed(notes):
    """RSS 2.0：只收 10-events，依日期新到舊取前 FEED_SIZE 則。"""
    events = sorted([n for n in notes.values() if n["folder"] == "10-events"],
                    key=lambda x: x["date"], reverse=True)[:FEED_SIZE]
    base = f"{SITE_URL}/" if SITE_URL else ""
    items = []
    for n in events:
        link = base + url_for(n["slug"])
        pub = rfc822(n["date"])
        parts = [
            "  <item>",
            f"    <title>{xml_escape(n['title'])}</title>",
            f"    <link>{xml_escape(link)}</link>",
            # 有絕對網址時 guid 才能當永久連結
            f'    <guid isPermaLink="{"true" if SITE_URL else "false"}">{xml_escape(link)}</guid>',
        ]
        if pub:
            parts.append(f"    <pubDate>{pub}</pubDate>")
        parts.append(f"    <description>{xml_escape(one_liner(n))}</description>")
        parts += [f"    <category>{xml_escape(t)}</category>" for t in n["topics"]]
        parts.append("  </item>")
        items.append("\n".join(parts))

    head = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"  <title>{xml_escape(SITE_TITLE)} — 事件</title>",
        f"  <link>{xml_escape(base or 'index.html')}</link>",
        f"  <description>{xml_escape(SITE_DESC)}</description>",
        "  <language>zh-Hant</language>",
        f"  <lastBuildDate>{format_datetime(datetime.now(TZ))}</lastBuildDate>",
    ]
    if SITE_URL:
        head.append(f'  <atom:link href="{xml_escape(base)}feed.xml" rel="self" type="application/rss+xml"/>')
    xml = "\n".join(head + items + ["</channel>", "</rss>"]) + "\n"
    (OUT / "feed.xml").write_text(xml, encoding="utf-8")
    return len(events)


def main():
    # 只清空 site/ 的內容、保留資料夾本身：Windows 上若 run serve 正在 site/ 裡跑，
    # 資料夾被佔用刪不掉，整個 rmtree 會失敗
    OUT.mkdir(exist_ok=True)
    for child in OUT.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    (OUT / "assets").mkdir(parents=True)
    notes = resolve_links(collect())
    build_index(notes)
    build_notes(notes)
    build_search(notes)
    n_feed = build_feed(notes)
    (OUT / "assets" / "style.css").write_text(CSS, encoding="utf-8")
    (OUT / "assets" / "app.js").write_text(JS, encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"✓ 網站已產生：{OUT}（{len(notes)} 篇筆記，RSS {n_feed} 則）")


if __name__ == "__main__":
    main()
