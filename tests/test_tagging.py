import tagging
from tagging import matches, tags_for, note_terms


def test_s2t_table_has_unique_pairs():
    simp = tagging._PAIRS[0::2]
    assert len(tagging._PAIRS) % 2 == 0
    assert len(set(simp)) == len(simp)
    assert all(a != b for a, b in zip(simp, tagging._PAIRS[1::2]))
    assert tagging.to_trad("稳定币监管") == "穩定幣監管"


def test_matches_rules():
    assert matches("SEC", "SEC approves ETF")
    assert not matches("SEC", "Securities firm")          # 單字邊界
    assert not matches("DID", "the bank did it")          # 全大寫縮寫區分大小寫
    assert matches("tokeniz*", "Tokenized deposits")      # 字根、不分大小寫
    assert not matches("stablecoin", "stablecoins2x")
    assert matches("U.S.", "U.S. Treasury")
    assert matches("穩定幣", "香港稳定币条例")              # 簡轉繁


def _item(title, summary="", feed="CoinDesk"):
    return {"title": title, "rss_summary": summary, "source_feed": feed}


def test_tags_topics_watch_jurisdiction(tax):
    tags = tags_for(_item("SoFi begins stablecoin settlement on Mastercard network"), tax, [])
    assert {"kind": "topic", "key": "穩定幣"} in tags
    assert {"kind": "topic", "key": "RWA"} in tags
    assert {"kind": "jurisdiction", "key": "美國"} in tags
    tags = tags_for(_item("JPMorgan Kinexys settles repo on chain"), tax, [])
    assert {"kind": "watch", "key": "kinexys"} in tags and {"kind": "watch", "key": "jpmorgan"} in tags


def test_jurisdiction_source_first_and_title_only_words(tax):
    tags = tags_for(_item("Speech on payments", feed="HKMA Press Releases"), tax, [])
    assert [t["key"] for t in tags if t["kind"] == "jurisdiction"] == ["香港"]
    # 「US」只在標題算數；內文出現不算
    tags = tags_for(_item("Bank pilots tokenized deposits", "Priced in US dollars"), tax, [])
    assert not [t for t in tags if t["kind"] == "jurisdiction"]


def test_note_terms_and_note_tags(tmp_vault, tax):
    (tmp_vault / "20-concepts" / "cash-leg.md").write_text(
        "---\nid: abcd2345\ntype: concept\ntitle: 現金腿\naliases: [cash leg, DvP]\n---\n", encoding="utf-8")
    (tmp_vault / "10-events" / "old.md").write_text(
        "---\ntype: event\nauto: true\ntitle: DvP 舊卡\n---\n", encoding="utf-8")
    (tmp_vault / "20-concepts" / "no-id.md").write_text("---\ntype: concept\ntitle: 沒有 id\n---\n", encoding="utf-8")
    terms = note_terms(tmp_vault)
    assert terms == [("abcd2345", ["現金腿", "cash leg", "DvP"])]
    tags = tags_for(_item("Banks test DvP settlement"), tax, terms)
    assert {"kind": "note", "key": "abcd2345"} in tags
    assert not [t for t in tags_for(_item("Dvpx launches"), tax, terms) if t["kind"] == "note"]


def test_tags_are_unique(tax):
    tags = tags_for(_item("Stablecoin stablecoin 穩定幣"), tax, [])
    assert len(tags) == len({(t["kind"], t["key"]) for t in tags})
