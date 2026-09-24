import notes


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_ok(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "---\ntype: concept\ntopics: [RWA]\n---\n# 標題\n內文\n"))
    assert n.error == ""
    assert n.fm == {"type": "concept", "topics": ["RWA"]}
    assert n.body.startswith("# 標題")


def test_parse_crlf(tmp_path):
    p = tmp_path / "a.md"
    p.write_bytes("---\r\ntype: moc\r\n---\r\n# X\r\n".encode("utf-8"))
    n = notes.parse_note(p)
    assert n.error == "" and n.fm["type"] == "moc"


def test_parse_missing_frontmatter(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "# 沒有 frontmatter\n"))
    assert n.error == "缺少 frontmatter"


def test_parse_bad_yaml_reports_error(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "---\ntitle: a: b: [\n---\nx\n"))
    assert n.error.startswith("YAML 解析失敗")
    assert n.fm == {}


def test_parse_non_mapping(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "---\n- a\n- b\n---\nx\n"))
    assert n.error == "frontmatter 不是 key: value 形式"


def test_first_heading():
    assert notes.first_heading("前言\n## 第二層標題\n# 一層\n") == "第二層標題"
    assert notes.first_heading("沒有標題") == ""


def test_new_id_format_and_unique():
    existing = set()
    for _ in range(200):
        i = notes.new_id(existing)
        assert notes.ID_RE.match(i)
        assert i not in existing
        existing.add(i)


def test_iter_notes_and_legacy(tmp_vault):
    write(tmp_vault / "10-events" / "a.md", "---\ntype: event\nauto: true\n---\nx\n")
    write(tmp_vault / "20-concepts" / "b.md", "---\ntype: concept\n---\nx\n")
    got = {n.path.name: n for n in notes.iter_notes(tmp_vault)}
    assert set(got) == {"a.md", "b.md"}
    assert notes.is_legacy_auto(got["a.md"]) is True
    assert notes.is_legacy_auto(got["b.md"]) is False


def test_parse_non_utf8_reports_error(tmp_path):
    p = tmp_path / "a.md"
    p.write_bytes("---\ntype: moc\n---\n中文".encode("big5"))
    n = notes.parse_note(p)
    assert n.error == "無法讀取：UnicodeDecodeError"
    assert n.fm == {}
