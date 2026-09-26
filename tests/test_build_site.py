import pytest

import build_site


def test_origin_badge_ai():
    assert build_site.origin_badge({"origin": "ai", "reviewed": ""}) == \
        '<span class="origin origin-ai" title="AI 撰寫，尚未審閱">AI 草稿</span>'


def test_origin_badge_reviewed():
    assert build_site.origin_badge({"origin": "ai-reviewed", "reviewed": "2026-09-30"}) == \
        '<span class="origin origin-reviewed" title="AI 撰寫，已審閱">已審閱 2026-09-30</span>'


def test_origin_badge_human_and_missing():
    assert build_site.origin_badge({"origin": "human", "reviewed": ""}) == ""
    assert build_site.origin_badge({"origin": "", "reviewed": ""}) == ""


def test_origin_badge_escapes():
    out = build_site.origin_badge({"origin": "ai-reviewed", "reviewed": "<b>"})
    assert "<b>" not in out and "&lt;b&gt;" in out


def test_main_fails_on_schema_error(monkeypatch):
    import validate
    monkeypatch.setattr(validate, "validate_all",
                        lambda root, tax: [validate.Issue(build_site.ROOT / "20-concepts" / "x.md", "error", "壞")])
    with pytest.raises(SystemExit) as e:
        build_site.main()
    assert e.value.code == 1
