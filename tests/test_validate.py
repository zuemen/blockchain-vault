import validate
from notes import parse_note

GOOD_CONCEPT = """---
type: concept
id: abcdefgh
title: 現金腿
origin: ai
topics: [RWA]
maturity: growing
updated: 2026-09-23
---
# 現金腿
連到 [[原子結算]] 與 [[news:12]]
"""


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def msgs(issues):
    return [i.msg for i in issues]


def test_good_concept_has_no_issues(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "20-concepts" / "cash-leg.md", GOOD_CONCEPT))
    assert validate.validate_note(n, tax) == []


def test_bad_yaml_is_error(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "20-concepts" / "x.md", "---\ntitle: a: b: [\n---\n"))
    out = validate.validate_note(n, tax)
    assert out[0].level == "error" and out[0].msg.startswith("YAML 解析失敗")


def test_legacy_auto_card_skipped(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "10-events" / "a.md", "---\ntype: event\nauto: true\ntopics: [亂寫]\n---\n"))
    assert validate.validate_note(n, tax) == []


def test_missing_required_fields(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "20-concepts" / "x.md", "---\ntype: concept\n---\n"))
    m = msgs(validate.validate_note(n, tax))
    for f in ("id", "title", "origin", "topics", "maturity", "updated"):
        assert f"缺少欄位 {f}" in m


def test_type_must_match_folder(tmp_vault, tax):
    text = GOOD_CONCEPT.replace("type: concept", "type: entity")
    n = parse_note(write(tmp_vault / "20-concepts" / "x.md", text))
    assert "type 應為 concept（資料夾 20-concepts），實際是 entity" in msgs(validate.validate_note(n, tax))


def test_unknown_topic_and_origin(tmp_vault, tax):
    text = GOOD_CONCEPT.replace("topics: [RWA]", "topics: [RWA, 亂寫]").replace("origin: ai", "origin: robot")
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "20-concepts" / "x.md", text)), tax))
    assert "topics 值不在 taxonomy：亂寫" in m
    assert "origin 值不合法：robot" in m


def test_ai_reviewed_needs_reviewed_date(tmp_vault, tax):
    text = GOOD_CONCEPT.replace("origin: ai", "origin: ai-reviewed")
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "20-concepts" / "x.md", text)), tax))
    assert "origin 是 ai-reviewed 但沒有 reviewed 日期" in m


def test_regulation_rules(tmp_vault, tax):
    text = """---
type: regulation
id: bcdefghi
title: 某法
origin: ai
topics: [金融法規]
jurisdiction: 香港 / 火星
updated: 2026-09-23
stage: 9
review: 大概
tracks: [穩定幣, 亂寫]
effective_date: 最快 2027Q1
---
"""
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "40-regulations" / "x.md", text)), tax))
    assert "jurisdiction 值不在 taxonomy：火星" in m
    assert "stage 必須是 1–5 的整數：9" in m
    assert "review 值不合法：大概" in m
    assert "tracks 值不在 taxonomy：亂寫" in m
    assert "effective_date 必須是 YYYY、YYYY-MM 或 YYYY-MM-DD：最快 2027Q1" in m


def test_effective_date_forms_ok(tmp_vault, tax):
    for v in ("2026-09-08", "2023-06", "2027", ""):
        text = f"""---
type: regulation
id: bcdefghi
title: 某法
origin: ai
topics: [金融法規]
jurisdiction: 全球
updated: 2026-09-23
effective_date: {v}
---
"""
        n = parse_note(write(tmp_vault / "40-regulations" / "x.md", text))
        assert validate.validate_note(n, tax) == [], v


def test_output_kind(tmp_vault, tax):
    text = """---
type: output
id: cdefghij
title: 週報
origin: human
topics: [RWA]
kind: 日報
date: 2026-09-18
---
"""
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "60-outputs" / "x.md", text)), tax))
    assert "kind 值不合法：日報" in m


def test_validate_all_duplicate_id_and_dangling_link(tmp_vault, tax):
    write(tmp_vault / "20-concepts" / "cash-leg.md", GOOD_CONCEPT)
    write(tmp_vault / "20-concepts" / "copy.md", GOOD_CONCEPT.replace("title: 現金腿", "title: 副本"))
    out = validate.validate_all(tmp_vault, tax)
    dup = [i for i in out if i.msg.startswith("id 重複")]
    assert len(dup) == 2 and all(i.level == "error" for i in dup)
    miss = [i for i in out if i.level == "warning"]
    assert any(i.msg == "wikilink 找不到筆記：[[原子結算]]" for i in miss)
    assert not any("news:12" in i.msg for i in out)


def test_link_resolves_by_title(tmp_vault, tax):
    write(tmp_vault / "20-concepts" / "cash-leg.md", GOOD_CONCEPT)
    write(tmp_vault / "20-concepts" / "atomic.md",
          GOOD_CONCEPT.replace("id: abcdefgh", "id: zzzzzzzz").replace("title: 現金腿", "title: 原子結算"))
    out = validate.validate_all(tmp_vault, tax)
    assert not any(i.msg == "wikilink 找不到筆記：[[原子結算]]" for i in out)


def test_report_returns_error_count(tmp_vault, capsys):
    issues = [validate.Issue(tmp_vault / "20-concepts" / "a.md", "error", "壞"),
              validate.Issue(tmp_vault / "20-concepts" / "b.md", "warning", "注意")]
    assert validate.report(issues, tmp_vault) == 1
    out = capsys.readouterr().out
    assert "20-concepts/a.md" in out and "壞" in out and "注意" in out
