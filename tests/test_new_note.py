import shutil
from pathlib import Path

import pytest

import new_note
import validate
from notes import parse_note

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def vault_with_templates(tmp_vault):
    shutil.copytree(ROOT / "templates", tmp_vault / "templates")
    return tmp_vault


@pytest.mark.parametrize("kind", ["concept", "entity", "regulation", "event"])
def test_created_note_is_valid_except_user_fields(vault_with_templates, tax, kind):
    p = new_note.create_note(vault_with_templates, kind, "測試: 標題", "2026-09-25")
    n = parse_note(p)
    assert n.error == ""
    assert n.fm["title"] == "測試: 標題"
    assert n.fm["origin"] == "human"
    msgs = [i.msg for i in validate.validate_note(n, tax)]
    # 模板留空給人填的欄位才允許報錯
    allowed = {"缺少欄位 jurisdiction", "缺少欄位 topics"}
    assert set(msgs) <= allowed, msgs


def test_existing_file_refused(vault_with_templates):
    new_note.create_note(vault_with_templates, "concept", "重複", "2026-09-25")
    with pytest.raises(FileExistsError):
        new_note.create_note(vault_with_templates, "concept", "重複", "2026-09-25")


def test_ids_unique(vault_with_templates):
    a = parse_note(new_note.create_note(vault_with_templates, "concept", "甲", "2026-09-25")).fm["id"]
    b = parse_note(new_note.create_note(vault_with_templates, "concept", "乙", "2026-09-25")).fm["id"]
    assert a != b


def test_raw_template_gives_clear_error(tmp_vault, tax):
    raw = (ROOT / "templates" / "concept.md").read_text(encoding="utf-8").replace("{{date}}", "2026-09-25")
    p = tmp_vault / "20-concepts" / "raw.md"
    p.write_text(raw, encoding="utf-8")
    msgs = [i.msg for i in validate.validate_note(parse_note(p), tax)]
    assert "id 格式不對：{{id}}" in msgs
    assert not any(m.startswith("YAML 解析失敗") for m in msgs)
