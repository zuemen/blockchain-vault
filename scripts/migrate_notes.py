#!/usr/bin/env python3
"""一次性遷移：補 id / title / origin，刪沒用的欄位，整理 effective_date。可重跑。

用法：
  python scripts/migrate_notes.py --dry-run
  python scripts/migrate_notes.py --human 2026-09-22-sofi-穩定幣結算-mastercard.md ...
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from notes import FM_RE, first_heading, is_legacy_auto, iter_notes, new_id

ROOT = Path(__file__).resolve().parent.parent
REMOVE_ALWAYS = {"keyword_hits", "used_in"}
REMOVE_EVENT = {"status"}
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")
DATE_PREFIX = re.compile(r"^(\d{4}(?:-\d{2}(?:-\d{2})?)?)(?!\d)(.*)$")
FULL_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _strip_note(s: str) -> str:
    s = s.strip()
    if s.startswith("（") and s.endswith("）"):
        s = s[1:-1]
    return s.strip()


def _fix_effective_date(value: str) -> list:
    v = value.strip()
    if v == "" or FULL_DATE.match(v):
        return [f"effective_date:{' ' + v if v else ''}"]
    m = DATE_PREFIX.match(v)
    if m and m.group(2).strip():
        return [f"effective_date: {m.group(1)}",
                f"effective_note: {json.dumps(_strip_note(m.group(2)), ensure_ascii=False)}"]
    return ["effective_date:", f"effective_note: {json.dumps(v, ensure_ascii=False)}"]


def migrate_text(raw: str, stem: str, existing_ids: set, origin: str = "ai") -> str:
    m = FM_RE.match(raw)
    if not m:
        return raw
    fm = yaml.safe_load(m.group(1)) or {}
    if fm.get("type") == "event" and fm.get("auto") is True:
        return raw
    body = raw[m.end():]   # 只拿來找標題
    remove = REMOVE_ALWAYS | (REMOVE_EVENT if fm.get("type") == "event" else set())

    out, skipping = [], False
    for line in m.group(1).split("\n"):
        km = KEY_RE.match(line)
        if km:
            skipping = km.group(1) in remove
            if skipping:
                continue
            if km.group(1) == "effective_date" and "effective_note" not in fm:
                out += _fix_effective_date(km.group(2))
                continue
        elif skipping and (line.startswith((" ", "\t", "-")) or line.strip() == ""):
            continue
        else:
            skipping = False
        out.append(line)

    add = []
    if not fm.get("id"):
        i = new_id(existing_ids)
        existing_ids.add(i)
        add.append(f"id: {i}")
    if not fm.get("title"):
        add.append(f"title: {json.dumps(first_heading(body) or stem, ensure_ascii=False)}")
    if not fm.get("origin"):
        add.append(f"origin: {origin}")
    if add:
        at = next(k for k, l in enumerate(out) if l.startswith("type:")) + 1
        out[at:at] = add
    # 開頭分隔線與「結尾分隔線＋正文」原樣保留，避免吃掉 frontmatter 後的空行
    return raw[:m.start(1)] + "\n".join(out) + raw[m.end(1):]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--human", nargs="*", default=[], help="這些檔名的 origin 設成 human")
    args = ap.parse_args(argv)

    all_notes = list(iter_notes(ROOT))
    ids = {str(n.fm["id"]) for n in all_notes if n.fm.get("id")}
    changed = 0
    for n in all_notes:
        if n.error or is_legacy_auto(n):
            continue
        raw = n.path.read_text(encoding="utf-8")
        origin = "human" if n.path.name in args.human else "ai"
        new = migrate_text(raw, n.path.stem, ids, origin)
        if new != raw:
            changed += 1
            print(("[試跑] " if args.dry_run else "") + n.path.relative_to(ROOT).as_posix())
            if not args.dry_run:
                n.path.write_text(new, encoding="utf-8")
    print(f"{'會' if args.dry_run else '已'}修改 {changed} 篇")
    return 0


if __name__ == "__main__":
    sys.exit(main())
