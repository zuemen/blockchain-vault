import pytest

import taxonomy
from scoring import score


@pytest.fixture
def sc(tax):
    return tax["scoring"]


def test_title_hits_count_double(sc):
    s, hits = score("SEC Clears Tokenized Stocks To Trade Onchain As CFTC Widens Software Relief", "", "trade", sc)
    assert s == 8
    assert set(hits) == {"tokeniz", "SEC"}


def test_english_verb_did_is_not_DID(sc):
    s, hits = score("Why banks did not adopt stablecoins", "", "trade", sc)
    assert "DID" not in hits
    assert s == 4


def test_simplified_chinese_hits_traditional_keyword(sc):
    s, hits = score("美联储拟对稳定币发行商实施新资本规则", "", "trade", sc)
    assert "穩定幣" in hits
    assert s == 4


def test_generic_word_needs_core_in_title(sc):
    s, hits = score("Fidelity reports quarterly earnings", "", "trade", sc)
    assert hits == [] and s == -8
    s, hits = score("Fidelity launches tokenized money market fund", "", "trade", sc)
    assert "Fidelity" in hits and s == 8


def test_assume_core_skips_core_miss_penalty(sc):
    assert score("Bank adds new custody service", "", "aggregator", sc, assume_core=True)[0] == 0
    assert score("Bank adds new custody service", "", "aggregator", sc)[0] == -6


def test_noise_words_penalised(sc):
    title = "BiFu 將亮相 Token2049 新加坡，舉辦「超越熱度：RWA 真正落地，還缺什麼？」主題晚宴與行業酒會"
    assert score(title, "", "trade", sc)[0] == -12


def test_jurisdiction_rule_must_be_known(tmp_path, tax):
    import yaml
    bad = dict(tax, jurisdiction_rules={"火星": {"keywords": ["Mars"], "sources": []}})
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(taxonomy.TaxonomyError, match="火星"):
        taxonomy.load_taxonomy(p)
