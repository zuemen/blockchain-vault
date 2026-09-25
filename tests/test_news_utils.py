import datetime as dt

from news_utils import normalize_url, clean_summary, detect_lang, utc_iso


def test_normalize_url():
    assert (normalize_url("HTTPS://Example.COM/a/b/?utm_source=x&id=3&fbclid=y&gclid=z#frag")
            == "https://example.com/a/b?id=3")
    assert normalize_url("https://example.com/") == "https://example.com"
    assert normalize_url("https://example.com/p?ref=tw&reference=1") == "https://example.com/p?reference=1"
    # 同一篇的兩種寫法要正規化成同一個
    assert normalize_url("https://a.com/x/?utm_medium=rss") == normalize_url("https://A.com/x")


def test_clean_summary():
    raw = "&lt;p&gt;Banks <b>tokenize</b> deposits.&lt;/p&gt; The post X appeared first on Y."
    assert clean_summary(raw) == "Banks tokenize deposits."
    assert clean_summary("Big news here - Reuters", "Big news here") == ""   # 只是重述標題
    long = ("第一句話很長。" * 120)
    out = clean_summary(long)
    assert len(out) <= 600 and out.endswith("。")


def test_detect_lang_and_utc_iso():
    assert detect_lang("香港穩定幣條例") == "zh"
    assert detect_lang("SEC approves") == "en"
    tpe = dt.timezone(dt.timedelta(hours=8))
    assert utc_iso(dt.datetime(2026, 9, 25, 7, 0, tzinfo=tpe)) == "2026-09-24T23:00:00Z"
