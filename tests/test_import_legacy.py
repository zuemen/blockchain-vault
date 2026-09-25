from import_legacy import card_to_item, legacy_summary
from notes import parse_note

OLD_CARD = """---
type: event
date: 2026-09-22
title: "SoFi begins stablecoin settlement on Mastercard network"
source_url: "https://www.theblock.co/post/1?utm_source=rss"
source_name: "The Block"
source_tier: trade
score: 9
auto: true
---

## 一句話
（待填）

## 事實（只放可查證的）
- SoFi said the program will exceed $25 billion.

## 我的判讀
-
"""

WIP_CARD = """---
type: event
date: 2026-09-24
title: "Chainlink CCIP powers fund"
source_url: "https://news.google.com/rss/articles/abc"
source_name: "Reuters（GN Chainlink）"
source_tier: aggregator
score: 6
auto: true
---

## 內容
Chainlink said X.
"""


def _card(tmp_path, text):
    p = tmp_path / "card.md"
    p.write_text(text, encoding="utf-8")
    return parse_note(p)


def test_old_card(tmp_path):
    it = card_to_item(_card(tmp_path, OLD_CARD))
    assert it["url_canonical"] == "https://www.theblock.co/post/1"
    assert (it["outlet"], it["source_feed"], it["tier"], it["score"]) == ("The Block", "The Block", "trade", 9)
    assert it["published_at"] == "2026-09-21T16:00:00Z"       # 台北 9/22 00:00
    assert it["rss_summary"] == "SoFi said the program will exceed $25 billion."
    assert it["url_resolved"] == 1 and it["lang"] == "en"


def test_wip_card_with_google_news_source(tmp_path):
    it = card_to_item(_card(tmp_path, WIP_CARD))
    assert (it["outlet"], it["source_feed"], it["tier"]) == ("Reuters", "GN Chainlink", "aggregator")
    assert it["url_resolved"] == 0
    assert it["rss_summary"] == "Chainlink said X."


def test_card_missing_url_or_bad_date(tmp_path):
    assert card_to_item(_card(tmp_path, OLD_CARD.replace("source_url:", "x:"))) is None
    assert card_to_item(_card(tmp_path, OLD_CARD.replace("date: 2026-09-22", "date: 昨天"))) is None


def test_placeholder_summary_is_empty():
    assert legacy_summary("## 事實\n- （待填）\n\n## 我的判讀\n-") == ""
