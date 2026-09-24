#!/usr/bin/env python3
"""筆記 schema 驗證。建站第一步執行，有 error 就讓 build 失敗。

用法： python scripts/validate.py
"""
import datetime as dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import taxonomy
from notes import ID_RE, Note, is_legacy_auto, iter_notes

ROOT = Path(__file__).resolve().parent.parent
DIR_TYPE = {"10-events": "event", "20-concepts": "concept", "30-entities": "entity",
            "40-regulations": "regulation", "50-maps": "moc", "60-outputs": "output"}
COMMON = ("id", "type", "title", "origin", "topics")
BY_TYPE = {"concept": ("maturity", "updated"), "entity": ("jurisdiction", "updated"),
           "regulation": ("jurisdiction", "updated"), "moc": ("updated",),
           "event": ("date",), "output": ("kind", "date")}
REVIEW = ("待核對", "已核對")
KINDS = ("週報", "講稿")
PARTIAL_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


@dataclass
class Issue:
    path: Path
    level: str   # "error" | "warning"
    msg: str


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def validate_note(note: Note, tax: dict) -> list:
    out = []

    def err(msg):
        out.append(Issue(note.path, "error", msg))

    if note.error:
        err(note.error)
        return out
    if is_legacy_auto(note):
        return out
    fm = note.fm
    expected = DIR_TYPE.get(note.path.parent.name)
    kind = fm.get("type")
    for f in COMMON + BY_TYPE.get(kind, ()):
        if fm.get(f) in (None, ""):
            err(f"缺少欄位 {f}")
    if expected and kind and kind != expected:
        err(f"type 應為 {expected}（資料夾 {note.path.parent.name}），實際是 {kind}")
    if fm.get("id") and not ID_RE.match(str(fm["id"])):
        err(f"id 格式不對：{fm['id']}")
    origin = fm.get("origin")
    if origin and origin not in tax["origins"]:
        err(f"origin 值不合法：{origin}")
    if origin == "ai-reviewed" and not fm.get("reviewed"):
        err("origin 是 ai-reviewed 但沒有 reviewed 日期")
    if "topics" in fm and fm["topics"] is not None and not isinstance(fm["topics"], list):
        err("topics 必須是陣列")
    for t in _as_list(fm.get("topics")):
        if t not in tax["topics"]:
            err(f"topics 值不在 taxonomy：{t}")
    if fm.get("maturity") and fm["maturity"] not in tax["maturity"]:
        err(f"maturity 值不合法：{fm['maturity']}")
    if fm.get("jurisdiction"):
        for part in str(fm["jurisdiction"]).split("/"):
            part = part.strip()
            if part and part not in tax["jurisdictions"]:
                err(f"jurisdiction 值不在 taxonomy：{part}")
    for t in _as_list(fm.get("tracks")):
        if t not in tax["tracks"]:
            err(f"tracks 值不在 taxonomy：{t}")
    if "stage" in fm and fm["stage"] is not None:
        s = fm["stage"]
        if not (isinstance(s, int) and not isinstance(s, bool) and 1 <= s <= 5):
            err(f"stage 必須是 1–5 的整數：{s}")
    if fm.get("review") and fm["review"] not in REVIEW:
        err(f"review 值不合法：{fm['review']}")
    ed = fm.get("effective_date")
    if ed not in (None, "") and not isinstance(ed, dt.date) and not PARTIAL_DATE.match(str(ed)):
        err(f"effective_date 必須是 YYYY、YYYY-MM 或 YYYY-MM-DD：{ed}")
    if kind == "output" and fm.get("kind") and fm["kind"] not in KINDS:
        err(f"kind 值不合法：{fm['kind']}")
    return out


def validate_all(root: Path, tax: dict) -> list:
    all_notes = list(iter_notes(root))
    out = []
    for n in all_notes:
        out += validate_note(n, tax)

    by_id = {}
    for n in all_notes:
        if n.fm.get("id") and not is_legacy_auto(n):
            by_id.setdefault(str(n.fm["id"]), []).append(n)
    for i, group in by_id.items():
        if len(group) > 1:
            names = "、".join(g.path.name for g in group)
            for g in group:
                out.append(Issue(g.path, "error", f"id 重複：{i}（{names}）"))

    known = set()
    for n in all_notes:
        known.add(n.path.stem.lower())
        if n.fm.get("title"):
            known.add(str(n.fm["title"]).lower())
    for n in all_notes:
        if n.error:
            continue
        text = n.body + "\n" + "\n".join(str(v) for v in n.fm.values())
        for m in WIKI_RE.finditer(text):
            target = m.group(1).strip()
            if target.startswith(("news:", "event:")):
                continue
            if target.lower() not in known:
                out.append(Issue(n.path, "warning", f"wikilink 找不到筆記：[[{target}]]"))
    return out


def report(issues: list, root: Path) -> int:
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    for label, group in (("錯誤", errors), ("警告", warnings)):
        for i in group:
            rel = i.path.relative_to(root).as_posix()
            print(f"[{label}] {rel}：{i.msg}")
    print(f"驗證完成：{len(errors)} 個錯誤、{len(warnings)} 個警告")
    return len(errors)


def main() -> int:
    tax = taxonomy.load_taxonomy()
    return 1 if report(validate_all(ROOT, tax), ROOT) else 0


if __name__ == "__main__":
    sys.exit(main())
