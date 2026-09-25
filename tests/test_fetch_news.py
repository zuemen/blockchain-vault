import datetime as dt
import sys
import types

import pytest

import fetch_news
from fetch_news import parse_entry, decode_gnews, dedupe_urls, prepare_payload

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
CUTOFF = NOW - dt.timedelta(hours=36)
GN_SRC = {"name": "GN Chainlink", "query": "Chainlink", "assume_core": True}
RSS_SRC = {"name": "CoinDesk", "url": "https://coindesk.com/rss"}


def entry(**kw):
    base = {"title": "Chainlink CCIP powers tokenized fund - Reuters", "link": "https://news.google.com/rss/articles/abc",
            "summary": "", "source": {"title": "Reuters"}, "published_parsed": (2026, 9, 24, 12, 0, 0)}
    return {**base, **kw}


def test_parse_google_news_entry(tax):
    it = parse_entry(entry(), GN_SRC, "aggregator", tax["scoring"], CUTOFF, NOW)
    assert it["title"] == "Chainlink CCIP powers tokenized fund"
    assert (it["outlet"], it["source_feed"]) == ("Reuters", "GN Chainlink")
    assert it["published_at"] == "2026-09-24T12:00:00Z"
    assert it["lang"] == "en" and it["score"] > 0


def test_parse_entry_edge_cases(tax):
    sc = tax["scoring"]
    assert parse_entry(entry(link="javascript:x"), RSS_SRC, "trade", sc, CUTOFF, NOW) is None
    assert parse_entry(entry(title="  "), RSS_SRC, "trade", sc, CUTOFF, NOW) is None
    assert parse_entry(entry(published_parsed=(2026, 9, 1, 0, 0, 0)), RSS_SRC, "trade", sc, CUTOFF, NOW) is None
    no_date = parse_entry(entry(published_parsed=None), RSS_SRC, "trade", sc, CUTOFF, NOW)
    assert no_date["published_at"] == "2026-09-25T00:00:00Z"
    # 一般 RSS 不拆「 - 媒體名」，outlet 就是來源名
    assert no_date["outlet"] == "CoinDesk" and no_date["title"].endswith("- Reuters")


def _fake_decoder(monkeypatch, fn):
    mod = types.ModuleType("googlenewsdecoder")
    mod.gnewsdecoder = fn
    monkeypatch.setitem(sys.modules, "googlenewsdecoder", mod)


def test_decode_gnews_success_and_partial_failure(monkeypatch):
    items = [{"url": "https://news.google.com/rss/articles/1", "url_resolved": 1},
             {"url": "https://news.google.com/rss/articles/2", "url_resolved": 1},
             {"url": "https://coindesk.com/a", "url_resolved": 1}]
    _fake_decoder(monkeypatch, lambda urls: [{"success": True, "decoded_url": "https://reuters.com/x"},
                                             {"success": False, "message": "blocked"}])
    decode_gnews(items)
    assert [(i["url"], i["url_resolved"]) for i in items] == [
        ("https://reuters.com/x", 1), ("https://news.google.com/rss/articles/2", 0), ("https://coindesk.com/a", 1)]


def test_decode_gnews_library_crash_keeps_redirect(monkeypatch):
    def boom(urls):
        raise RuntimeError("Google changed batchexecute")
    _fake_decoder(monkeypatch, boom)
    items = [{"url": "https://news.google.com/rss/articles/1", "url_resolved": 1}]
    decode_gnews(items)
    assert items[0]["url_resolved"] == 0


def test_dedupe_urls_keeps_highest_score():
    out = dedupe_urls([{"url_canonical": "u", "score": 3, "n": 1}, {"url_canonical": "u", "score": 7, "n": 2}])
    assert [i["n"] for i in out] == [2]


def _news(title, url, score=5):
    return {"title": title, "url": url, "url_canonical": url, "url_resolved": 1, "outlet": "CoinDesk",
            "source_feed": "CoinDesk", "tier": "trade", "lang": "en", "published_at": "2026-09-24T00:00:00Z",
            "rss_summary": "", "score": score}


def test_prepare_payload_skips_known_urls_and_tags(tmp_vault, tax):
    existing = [{"url_canonical": "https://a.com/1", "title": "Canada big six banks tokenized deposits",
                 "title_zh": None, "cluster_id": 12}]
    items = [_news("Canada big six banks tokenized deposits", "https://a.com/1"),
             _news("Canada's big six banks explore tokenized deposits", "https://b.com/2"),
             _news("SEC approves stablecoin rule", "https://c.com/3", score=9)]
    payload = prepare_payload(items, existing, tax, None, "bot", root=tmp_vault)
    by_url = {p["url_canonical"]: p for p in payload}
    assert set(by_url) == {"https://b.com/2", "https://c.com/3"}
    assert by_url["https://b.com/2"]["cluster_ref"] == 12          # Jaccard 併入既有分組
    assert by_url["https://c.com/3"]["cluster_ref"] == "new:1"
    assert {"kind": "jurisdiction", "key": "美國"} in by_url["https://c.com/3"]["tags"]
    assert by_url["https://c.com/3"]["added_by"] == "bot"


def test_prepare_payload_limit(tmp_vault, tax, monkeypatch):
    monkeypatch.setitem(tax["limits"], "daily_top", 1)
    items = [_news("Alpha tokenized fund launches", "https://a.com/1", 9),
             _news("Completely different stablecoin law", "https://b.com/2", 4)]
    assert len(prepare_payload(items, [], tax, None, "bot", root=tmp_vault)) == 1
    assert len(prepare_payload(items, [], tax, None, "import", limit=False, root=tmp_vault)) == 2
