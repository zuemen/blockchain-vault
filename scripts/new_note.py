#!/usr/bin/env python3
"""從模板開新筆記。 用法： python3 scripts/new_note.py {event|concept|entity|regulation} "標題" """
import re, sys, unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = {"event": "10-events", "concept": "20-concepts",
        "entity": "30-entities", "regulation": "40-regulations"}
TZ = timezone(timedelta(hours=8))


def slug(t):
    t = unicodedata.normalize("NFKC", t).strip()
    return re.sub(r"[^\w一-鿿]+", "-", t).strip("-")[:60]


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in DEST:
        sys.exit('用法： python3 scripts/new_note.py {event|concept|entity|regulation} "標題"')
    kind, title = sys.argv[1], sys.argv[2]
    today = datetime.now(TZ).date().isoformat()
    tpl = (ROOT / "templates" / f"{kind}.md").read_text(encoding="utf-8").replace("{{date}}", today)
    name = f"{today}-{slug(title)}.md" if kind == "event" else f"{slug(title)}.md"
    p = ROOT / DEST[kind] / name
    if p.exists():
        sys.exit(f"已存在：{p}")
    if kind == "event":
        tpl = tpl.replace("title:", f"title: {title}")
    else:
        tpl = tpl.replace("# 概念名稱", f"# {title}").replace("# 名稱", f"# {title}") \
                 .replace("# 法規名稱", f"# {title}")
    p.write_text(tpl, encoding="utf-8")
    print(p)


if __name__ == "__main__":
    main()
