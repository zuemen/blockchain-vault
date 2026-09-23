#!/usr/bin/env python3
"""把 vault 建成靜態網站（純 Python，無 npm）。

產出：site/index.html、site/n/<slug>.html、site/search.json、site/assets/*
公開：10-events / 20-concepts / 30-entities / 40-regulations / 50-maps
不公開：00-inbox、99-daily（每日筆記）、60-outputs（日報週報）、templates、scripts

用法： python3 scripts/build_site.py
"""
import json, re, shutil, sys, urllib.parse
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
                title=str(fm.get("title") or slug),
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
        body = DV_RE.sub("", note["body"])

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


def excerpt(note, k=150):
    txt = re.sub(r"<[^>]+>", " ", note["html"])
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:k]


TIER_LABEL = {"primary": "一手來源", "trade": "產業媒體", "aggregator": "彙整"}


def chip(text, cls=""):
    return f'<span class="chip {cls}">{text}</span>'


def meta_bar(n):
    bits = []
    if n["date"]:
        bits.append(chip(n["date"], "date"))
    if n["source_tier"]:
        bits.append(chip(TIER_LABEL.get(n["source_tier"], n["source_tier"]),
                         "tier-primary" if n["source_tier"] == "primary" else "tier"))
    if n["score"] != "":
        bits.append(chip(f"score {n['score']}", "score"))
    if n["maturity"]:
        bits.append(chip(f"maturity: {n['maturity']}", f"mat-{n['maturity']}"))
    if n["jurisdiction"]:
        bits.append(chip(n["jurisdiction"], "juris"))
    for t in n["topics"]:
        bits.append(chip(t, "topic"))
    return "".join(bits)


def shell(title, body, depth=0, desc=SITE_DESC):
    up = "../" * depth
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{desc}">
<title>{title}</title>
<link rel="stylesheet" href="{up}assets/style.css">
</head>
<body>
<header class="site">
  <a class="brand" href="{up}index.html">{SITE_TITLE}</a>
  <span class="tag">{SITE_DESC}</span>
</header>
<main>
{body}
</main>
<footer>
  <span>最後更新 {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')} (UTC+8)</span>
  <span>事件卡由腳本抓取骨架，判讀與概念筆記為人工撰寫</span>
</footer>
<script src="{up}assets/app.js"></script>
</body>
</html>
"""


def build_index(notes):
    events = sorted([n for n in notes.values() if n["folder"] == "10-events"],
                    key=lambda x: x["date"], reverse=True)
    concepts = sorted([n for n in notes.values() if n["folder"] == "20-concepts"],
                      key=lambda x: x["title"])
    entities = sorted([n for n in notes.values() if n["folder"] == "30-entities"],
                      key=lambda x: x["title"])
    regs = sorted([n for n in notes.values() if n["folder"] == "40-regulations"],
                  key=lambda x: x["title"])
    mocs = sorted([n for n in notes.values() if n["folder"] == "50-maps"],
                  key=lambda x: x["title"])

    all_topics = sorted({t for n in notes.values() for t in n["topics"]})
    chips = "".join(f'<button class="filter" data-topic="{t}">{t}</button>' for t in all_topics)

    def card(n):
        src = ""
        if n["source_url"]:
            src = f'<a class="src" href="{n["source_url"]}" target="_blank" rel="noopener">{n["source_name"] or "來源"} ↗</a>'
        return f"""<article class="card" data-topics="{'|'.join(n['topics'])}" data-kind="{n['folder']}">
  <a class="t" href="{url_for(n['slug'])}">{n['title']}</a>
  <div class="m">{meta_bar(n)}</div>
  <p class="x">{excerpt(n)}</p>
  {src}
</article>"""

    def list_block(title, items, note=""):
        if not items:
            return ""
        lis = "".join(
            f'<li data-topics="{"|".join(n["topics"])}"><a href="{url_for(n["slug"])}">{n["title"]}</a>'
            + (f'<span class="mini mat-{n["maturity"]}">{n["maturity"]}</span>' if n["maturity"] else "")
            + (f'<span class="mini">{n["jurisdiction"]}</span>' if n["jurisdiction"] else "")
            + "</li>" for n in items)
        return f'<section class="block"><h2>{title}</h2>{f"<p class=note>{note}</p>" if note else ""}<ul class="linklist">{lis}</ul></section>'

    body = f"""
<div class="toolbar">
  <input id="q" type="search" placeholder="搜尋標題、內容、主題…" autocomplete="off">
  <div class="filters"><button class="filter active" data-topic="">全部</button>{chips}</div>
</div>
<div id="results" class="hidden"></div>

<div id="main-view">
  <section class="block">
    <h2>最新事件 <span class="count">{len(events)}</span></h2>
    <div class="cards">{''.join(card(n) for n in events[:20])}</div>
  </section>

  {list_block("主題地圖", mocs, "每張地圖帶著我的核心主張與開放問題")}
  {list_block("概念", concepts, "知識累積在這裡。maturity 標示成熟度：seed 還講不深、growing 有案例、stable 能上台講")}
  {list_block("法規追蹤", regs)}
  {list_block("機構", entities)}
</div>
"""
    (OUT / "index.html").write_text(shell(SITE_TITLE, body, 0), encoding="utf-8")


def build_notes(notes):
    nd = OUT / "n"
    nd.mkdir(parents=True, exist_ok=True)
    for n in notes.values():
        src = ""
        if n["source_url"]:
            src = (f'<p class="srcline">來源：<a href="{n["source_url"]}" target="_blank" '
                   f'rel="noopener">{n["source_name"] or n["source_url"]} ↗</a></p>')
        bl = ""
        if n["backlinks"]:
            items = "".join(f'<li><a href="../{url_for(b)}">{notes[b]["title"]}</a></li>'
                            for b in sorted(n["backlinks"]))
            bl = f'<section class="backlinks"><h2>連到這裡的筆記</h2><ul>{items}</ul></section>'
        fwd = ""
        if n["links"]:
            items = "".join(f'<li><a href="../{url_for(l)}">{notes[l]["title"]}</a></li>'
                            for l in n["links"])
            fwd = f'<section class="backlinks"><h2>這篇連出去</h2><ul>{items}</ul></section>'

        body = f"""
<article class="note">
  <p class="crumb"><a href="../index.html">← 全部</a> · {n['folder_label']}</p>
  <h1>{n['title']}</h1>
  <div class="m">{meta_bar(n)}</div>
  {src}
  <div class="prose">{n['html']}</div>
</article>
{fwd}
{bl}
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
:root{
  --bg:#fbfaf8; --fg:#1b1a18; --dim:#6b6660; --line:#e6e2dc; --card:#fff;
  --accent:#8a5a2b; --accent-soft:#f3ece3; --miss:#b9b3ab;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#16161a; --fg:#e9e7e3; --dim:#9a958e; --line:#2b2b31; --card:#1d1d22;
         --accent:#d9a86c; --accent-soft:#2a241d; --miss:#5c574f; }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;
  padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
header.site{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;
  padding:20px 20px 12px;border-bottom:1px solid var(--line)}
.brand{font-weight:650;font-size:17px;color:var(--fg)}
.tag{color:var(--dim);font-size:12.5px}
main{max-width:920px;margin:0 auto;padding:20px}
footer{max-width:920px;margin:40px auto 24px;padding:16px 20px;border-top:1px solid var(--line);
  color:var(--dim);font-size:12px;display:flex;gap:16px;flex-wrap:wrap}
.toolbar{margin-bottom:20px}
#q{width:100%;padding:11px 14px;border:1px solid var(--line);border-radius:10px;
  background:var(--card);color:var(--fg);font-size:15px}
#q:focus{outline:2px solid var(--accent-soft);border-color:var(--accent)}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.filter{border:1px solid var(--line);background:var(--card);color:var(--dim);
  border-radius:999px;padding:4px 11px;font-size:12.5px;cursor:pointer}
.filter.active{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}
.block{margin:0 0 34px}
.block h2{font-size:15px;letter-spacing:.02em;margin:0 0 6px;display:flex;gap:8px;align-items:center}
.count{color:var(--dim);font-weight:400;font-size:12px}
.note.small,p.note{color:var(--dim);font-size:12.5px;margin:0 0 12px}
.cards{display:grid;gap:12px}
@media(min-width:720px){.cards{grid-template-columns:1fr 1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.card .t{display:block;font-weight:600;margin-bottom:6px;color:var(--fg);line-height:1.45}
.card .x{color:var(--dim);font-size:13px;margin:8px 0 6px}
.src{font-size:12px}
.m{display:flex;gap:5px;flex-wrap:wrap;margin:2px 0 4px}
.chip{font-size:11.5px;border:1px solid var(--line);border-radius:6px;padding:1px 7px;color:var(--dim)}
.chip.topic{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.chip.tier-primary{background:#1f7a4d;color:#fff;border-color:transparent}
.chip.score{font-variant-numeric:tabular-nums}
.mat-seed{color:#a8741f}.mat-growing{color:#1f7a4d}.mat-stable{color:var(--dim)}
.linklist{list-style:none;padding:0;margin:0;border-top:1px solid var(--line)}
.linklist li{border-bottom:1px solid var(--line);padding:9px 2px;display:flex;gap:10px;align-items:baseline}
.mini{font-size:11.5px;color:var(--dim)}
.hidden{display:none}
#results .card{margin-bottom:10px}
.crumb{color:var(--dim);font-size:12.5px;margin:0 0 6px}
.note h1{font-size:23px;line-height:1.35;margin:.2em 0 .4em}
.prose{margin-top:14px}
.prose h2{font-size:16px;margin:1.8em 0 .5em;padding-bottom:4px;border-bottom:1px solid var(--line)}
.prose h3{font-size:14.5px;margin:1.4em 0 .4em}
.prose table{border-collapse:collapse;width:100%;font-size:13.5px;display:block;overflow-x:auto}
.prose th,.prose td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
.prose th{background:var(--accent-soft)}
.prose code{background:var(--accent-soft);padding:1px 5px;border-radius:4px;font-size:12.5px}
.prose pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow-x:auto}
.prose blockquote{margin:1em 0;padding:2px 14px;border-left:3px solid var(--accent);color:var(--dim)}
.prose img{max-width:100%}
.wl{border-bottom:1px dashed var(--accent);text-decoration:none}
.wl-miss{color:var(--miss);border-bottom:1px dotted var(--miss)}
.srcline{font-size:13px;color:var(--dim)}
.backlinks{margin-top:30px;padding-top:14px;border-top:1px solid var(--line)}
.backlinks h2{font-size:13px;color:var(--dim);margin:0 0 6px}
.backlinks ul{margin:0;padding-left:18px;font-size:13.5px}
"""

JS = """
(async function(){
  const q=document.getElementById('q');
  if(!q) return;
  const res=document.getElementById('results');
  const main=document.getElementById('main-view');
  let idx=[]; let topic='';
  try{ idx=await (await fetch('search.json')).json(); }catch(e){}

  function render(list){
    if(!list.length){ res.innerHTML='<p class="note">沒有符合的筆記。</p>'; return; }
    res.innerHTML=list.slice(0,60).map(n=>`
      <article class="card">
        <a class="t" href="${n.u}">${n.t}</a>
        <div class="m"><span class="chip">${n.k}</span>${n.d?`<span class="chip date">${n.d}</span>`:''}
        ${(n.p||[]).map(p=>`<span class="chip topic">${p}</span>`).join('')}</div>
        <p class="x">${(n.s||'').slice(0,150)}</p>
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
"""


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    notes = resolve_links(collect())
    build_index(notes)
    build_notes(notes)
    build_search(notes)
    (OUT / "assets" / "style.css").write_text(CSS, encoding="utf-8")
    (OUT / "assets" / "app.js").write_text(JS, encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"✓ 網站已產生：{OUT}（{len(notes)} 篇筆記）")


if __name__ == "__main__":
    main()
