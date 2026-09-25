import tracker


def _note(title, body="", folder="10-events", **fm):
    return {"title": title, "body": body, "folder": folder, **fm}


def test_countries_come_from_taxonomy(tax):
    assert [c for c, _ in tracker.COUNTRIES] == list(tax["jurisdiction_rules"])
    assert "US" in tracker.BODY_AMBIGUOUS


def test_countries_and_tracks_use_shared_matcher():
    n = _note("美联储：代币化证券新规")                    # 簡體標題，議題詞只有繁體版
    assert tracker.countries_of(n) == ["美國"]
    assert "代幣化證券／RWA" in tracker.tracks_of(n)
    assert tracker.countries_of(_note("Why banks did not adopt it", source_name="SEC Press Releases")) == ["美國"]
    assert tracker.countries_of(_note("Bank pilots deposits", "Priced in US dollars")) == []
