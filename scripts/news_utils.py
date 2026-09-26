"""新聞文字與網址的小工具：網址正規化、RSS 摘要清理、語言判斷。只用標準庫。"""
import datetime as dt
import html
import re
import urllib.parse

TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|ref)$", re.I)
CJK = re.compile(r"[一-鿿]")

# 摘要尾巴的 RSS 樣板句
BOILERPLATE = [r"The post .{0,200}? appeared first on .{0,80}?\.?$", r"\[?…\]?\s*$",
               r"(Continue|Read) (reading|more).{0,40}$", r"本文.{0,20}(首發|原文)於.{0,40}$"]
SUMMARY_MAX = 600


def normalize_url(url: str) -> str:
    """去重用的網址：小寫 scheme 與 host、去追蹤參數、去 fragment 與結尾斜線。"""
    p = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"),
                                    urllib.parse.urlencode(query), ""))


def clean_summary(raw: str, title: str = "") -> str:
    """RSS 摘要轉純文字：解實體、去標籤、去樣板句，在句尾截斷。摘要只是標題重述時回傳空字串。"""
    # 先解碼再去標籤：反過來的話，編碼過的 &lt;script&gt; 會在解碼後變成真的標籤
    t = re.sub(r"<[^>]+>", " ", html.unescape(raw or ""))
    t = re.sub(r"\s+", " ", t).strip()
    for pat in BOILERPLATE:
        t = re.sub(pat, "", t, flags=re.I).strip()
    if title:
        tl = re.sub(r"\W+", "", title.lower())
        if not t or re.sub(r"\W+", "", t.lower()).startswith(tl[: max(20, len(tl) - 5)]):
            return ""
    if len(t) > SUMMARY_MAX:
        cut = t[:SUMMARY_MAX]
        end = max(cut.rfind(x) for x in ("。", "！", "？", ". ", "! ", "? "))
        t = cut[: end + 1] if end > SUMMARY_MAX // 2 else cut.rstrip() + "…"
    return t


def detect_lang(title: str) -> str:
    return "zh" if CJK.search(title) else "en"


def utc_iso(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
