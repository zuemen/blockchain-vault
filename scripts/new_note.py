#!/usr/bin/env python3
"""從模板開新筆記。 用法： python3 scripts/new_note.py {event|concept|entity|regulation} "標題" """
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from notes import iter_notes, new_id

ROOT = Path(__file__).resolve().parent.parent
DEST = {"event": "10-events", "concept": "20-concepts",
        "entity": "30-entities", "regulation": "40-regulations"}
TZ = timezone(timedelta(hours=8))


def slug(t):
    t = unicodedata.normalize("NFKC", t).strip()
    return re.sub(r"[^\w一-鿿]+", "-", t).strip("-")[:60]


def create_note(root: Path, kind: str, title: str, today: str) -> Path:
    ids = {str(n.fm["id"]) for n in iter_notes(root) if n.fm.get("id")}
    tpl = (root / "templates" / f"{kind}.md").read_text(encoding="utf-8")
    tpl = (tpl.replace("{{date}}", today)
              .replace("{{id}}", new_id(ids))
              .replace("{{title}}", json.dumps(title, ensure_ascii=False)))
    tpl = tpl.replace("# 概念名稱", f"# {title}").replace("# 名稱", f"# {title}") \
             .replace("# 法規名稱", f"# {title}")
    name = f"{today}-{slug(title)}.md" if kind == "event" else f"{slug(title)}.md"
    p = root / DEST[kind] / name
    if p.exists():
        raise FileExistsError(p)
    p.write_text(tpl, encoding="utf-8")
    return p


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in DEST:
        sys.exit('用法： python3 scripts/new_note.py {event|concept|entity|regulation} "標題"')
    today = datetime.now(TZ).date().isoformat()
    try:
        print(create_note(ROOT, sys.argv[1], sys.argv[2], today))
    except FileExistsError as e:
        sys.exit(f"已存在：{e}")


if __name__ == "__main__":
    main()
