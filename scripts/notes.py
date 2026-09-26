"""筆記解析：所有腳本共用，壞掉的 frontmatter 會回報錯誤而不是靜默變成 {}。"""
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

NOTE_DIRS = ("10-events", "20-concepts", "30-entities", "40-regulations", "50-maps", "60-outputs")
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
ID_RE = re.compile(r"^[a-z2-7]{8}$")


@dataclass
class Note:
    path: Path
    fm: dict
    body: str
    error: str = ""


def parse_note(path: Path) -> Note:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return Note(path, {}, "", f"無法讀取：{e.__class__.__name__}")
    m = FM_RE.match(raw)
    if not m:
        return Note(path, {}, raw, "缺少 frontmatter")
    body = raw[m.end():]
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        first_line = str(e).splitlines()[0]
        return Note(path, {}, body, f"YAML 解析失敗：{first_line}")
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        return Note(path, {}, body, "frontmatter 不是 key: value 形式")
    return Note(path, fm, body)


def iter_notes(root: Path, dirs=NOTE_DIRS) -> Iterator[Note]:
    for d in dirs:
        for f in sorted((Path(root) / d).glob("*.md")):
            yield parse_note(f)


def first_heading(body: str) -> str:
    m = HEADING_RE.search(body)
    return m.group(1).strip() if m else ""


def new_id(existing: set) -> str:
    while True:
        i = "".join(secrets.choice(ID_ALPHABET) for _ in range(8))
        if i not in existing:
            return i


def is_legacy_auto(note: Note) -> bool:
    """main 上 bot 產生的舊格式自動卡：階段 2 匯入 D1 前不驗證、不遷移。"""
    return note.fm.get("type") == "event" and note.fm.get("auto") is True
