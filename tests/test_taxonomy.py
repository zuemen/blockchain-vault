import pytest

import taxonomy


def test_real_taxonomy_loads(tax):
    assert "RWA" in tax["topics"]
    assert "支付" in tax["topics"]
    assert tax["stages"][3] == "已通過"
    assert tax["origins"] == ["ai", "ai-reviewed", "human"]
    assert {w["id"] for w in tax["watchlist"]} == {
        "chainlink", "kinexys", "jpmorgan", "fidelity", "bny", "fireblocks", "zk", "polygon"}


def test_missing_key_raises(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("topics: [RWA]\n", encoding="utf-8")
    with pytest.raises(taxonomy.TaxonomyError, match="缺少欄位"):
        taxonomy.load_taxonomy(p)


def test_duplicate_watch_id_raises(tmp_path, tax):
    import yaml
    bad = dict(tax, watchlist=[{"id": "a", "name": "A", "aliases": ["A"]},
                               {"id": "a", "name": "B", "aliases": ["B"]}])
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(taxonomy.TaxonomyError, match="watchlist id 重複"):
        taxonomy.load_taxonomy(p)
