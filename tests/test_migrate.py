from migrate_notes import migrate_text
from notes import ID_RE, FM_RE
import yaml


def fm_of(text):
    return yaml.safe_load(FM_RE.match(text).group(1))


CONCEPT = """---
type: concept
topics: [RWA, 支付]
maturity: growing
updated: 2026-09-23
---

# Cash leg（現金腿）

內文
"""

HUMAN_EVENT = """---
type: event
date: 2026-09-22
title: SoFi 穩定幣結算
source_url: https://example.com/a
topics: [RWA]
entities: ["[[SoFi]]"]
score: 8
status: cited
used_in: ["日報 2026-09-23"]
keyword_hits:
  - stablecoin
  - settle
---
## 一句話
x
"""


def test_concept_gets_id_title_origin():
    ids = set()
    out = migrate_text(CONCEPT, "cash-leg", ids)
    fm = fm_of(out)
    assert ID_RE.match(fm["id"]) and fm["id"] in ids
    assert fm["title"] == "Cash leg（現金腿）"
    assert fm["origin"] == "ai"
    lines = out.splitlines()
    assert lines[1] == "type: concept"
    assert lines[2].startswith("id: ")
    assert lines[3] == 'title: "Cash leg（現金腿）"'
    assert lines[4] == "origin: ai"
    assert out.endswith("# Cash leg（現金腿）\n\n內文\n")


def test_event_removes_fields_keeps_title():
    out = migrate_text(HUMAN_EVENT, "2026-09-22-sofi", set(), origin="human")
    fm = fm_of(out)
    for k in ("status", "used_in", "keyword_hits"):
        assert k not in fm
    assert fm["title"] == "SoFi 穩定幣結算"
    assert fm["origin"] == "human"
    assert fm["entities"] == ["[[SoFi]]"]
    assert "  - settle" not in out


def test_title_falls_back_to_stem():
    out = migrate_text("---\ntype: moc\ntopics: [ZK]\nupdated: 2026-09-23\n---\n沒有標題\n", "MOC-ZK", set())
    assert fm_of(out)["title"] == "MOC-ZK"


def test_idempotent():
    once = migrate_text(CONCEPT, "cash-leg", set())
    assert migrate_text(once, "cash-leg", set()) == once


def test_legacy_auto_untouched():
    raw = "---\ntype: event\nauto: true\nstatus: unread\n---\nx\n"
    assert migrate_text(raw, "a", set()) == raw


def reg(value):
    return f"---\ntype: regulation\ntopics: [金融法規]\njurisdiction: 美國\neffective_date: {value}\nupdated: 2026-09-23\n---\n# 法\n"


def test_effective_date_with_note():
    fm = fm_of(migrate_text(reg("2027-01-18（最晚）"), "x", set()))
    assert str(fm["effective_date"]) == "2027-01-18"
    assert fm["effective_note"] == "最晚"


def test_effective_date_without_date():
    fm = fm_of(migrate_text(reg("最快 2027Q1"), "x", set()))
    assert fm["effective_date"] is None
    assert fm["effective_note"] == "最快 2027Q1"


def test_effective_date_valid_untouched():
    for v in ("2026-09-08", "2023-06"):
        out = migrate_text(reg(v), "x", set())
        assert f"effective_date: {v}\n" in out
        assert "effective_note" not in out
