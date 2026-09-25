"""關鍵詞比對與新聞標記。評分、標記、各國進度都用這裡的 matches()，不要在別處另寫一套。

只依賴標準庫與 notes.py（PyYAML），因為 build_site.py 經由 tracker.py 會載入它，
而 Cloudflare build 只裝 pyyaml、markdown。
"""
import re
from pathlib import Path

import notes as notes_mod

ASCII_KW = re.compile(r"[A-Za-z0-9 .\-]+")
UPPER_DOTTED = re.compile(r"[A-Z](\.[A-Z])+\.?")

# 簡體 → 繁體的單字對照，只涵蓋本站主題常見字，讓「稳定币」也能命中「穩定幣」。
# ponytail: 逐字對照，詞彙差異（监管／監理）不處理；漏抓變多再改用 opencc
_PAIRS = ("币幣稳穩链鏈块塊监監规規资資产產银銀结結证證数數为為务務发發与與国國际際场場机機构構权權"
          "应應业業执執会會员員税稅贷貸汇匯兑兌实實现現网網络絡这這个個们們时時间間进進对對说說开開"
          "关關联聯备備储儲报報项項协協议議条條领領导導总總统統财財经經济濟贸貿纳納达達韩韓欧歐华華"
          "东東亚亞户戶账賬转轉让讓签簽认認质質杠槓杆桿预預测測创創试試点點颁頒许許虚虛拟擬钱錢托託"
          "价價额額长長线線众眾筹籌买買卖賣盘盤仓倉险險边邊隐隱验驗凭憑据據码碼电電讯訊云雲区區广廣"
          "义義兴興举舉传傳体體债債偿償则則动動单單变變号號启啟团團圣聖处處复復学學审審宪憲将將层層"
          "属屬岁歲师師带帶库庫张張强強录錄态態战戰扩擴护護担擔择擇换換损損断斷无無旧舊显顯标標样樣"
          "检檢极極气氣没沒涨漲满滿热熱状狀独獨环環画畫盖蓋矿礦确確离離种種积積竞競简簡类類紧緊约約"
          "级級练練组組终終维維综綜续續罗羅职職胜勝艺藝节節获獲营營补補视視计計订訂讨討训訓记記讲講"
          "论論设設访訪评評识識诉訴译譯询詢该該详詳语語请請读讀调調谈談负負责責败敗货貨购購费費贵貴"
          "赔賠赚賺赛賽趋趨车車轮輪软軟较較输輸过過运運还還远遠违違连連适適选選释釋针針铁鐵销銷锁鎖"
          "错錯键鍵门門问問队隊阶階陆陸随隨难難页頁顶頂顺順须須频頻题題风風飞飛驱驅龙龍黄黃齐齊")
S2T = str.maketrans(_PAIRS[0::2], _PAIRS[1::2])


def to_trad(s: str) -> str:
    return s.translate(S2T)


def matches(kw: str, text: str) -> bool:
    """關鍵詞是否出現在 text。

    - 中日韓字：子字串比對，雙方先轉繁體。
    - 英數：單字邊界。全大寫縮寫（SEC、DID、U.S.）區分大小寫，
      否則英文動詞 did 會命中 DID；其餘不分大小寫。
    - 尾端 * 表示字根，只放寬右邊界（tokeniz* 命中 tokenized）。
    """
    stem = kw.endswith("*")
    k = kw[:-1] if stem else kw
    if not ASCII_KW.fullmatch(k):
        return to_trad(k.lower()) in to_trad(text.lower())
    right = "" if stem else r"(?![A-Za-z0-9])"
    if k.isupper() or UPPER_DOTTED.fullmatch(k):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(k)}{right}", text) is not None
    return re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}{right}", text.lower()) is not None


def topic_tags(text: str, tax: dict) -> list:
    return [t for t, kws in tax["scoring"]["topic_map"].items() if any(matches(k, text) for k in kws)]


def watch_tags(text: str, tax: dict) -> list:
    return [w["id"] for w in tax["watchlist"] if any(matches(a, text) for a in w["aliases"])]


def jurisdiction_tags(title: str, summary: str, source_feed: str, tax: dict) -> list:
    """優先序：來源名稱 → 標題關鍵詞 → 內文關鍵詞（title_only 的泛稱不算）。與 tracker.countries_of 相同。"""
    rules = tax["jurisdiction_rules"]
    by_src = [c for c, r in rules.items() if any(s and source_feed.startswith(s) for s in r.get("sources") or [])]
    if by_src:
        return by_src
    by_title = [c for c, r in rules.items() if any(matches(k, title) for k in r["keywords"])]
    if by_title:
        return by_title
    title_only = set(tax["title_only"])
    return [c for c, r in rules.items()
            if any(matches(k, summary) for k in r["keywords"] if k not in title_only)]


def note_terms(root: Path) -> list:
    """[(筆記 id, [title 與 aliases])]。跳過壞檔、舊自動卡、沒有 id 的筆記；詞長至少 2。"""
    out = []
    for n in notes_mod.iter_notes(root):
        if n.error or notes_mod.is_legacy_auto(n) or not n.fm.get("id"):
            continue
        raw = [n.fm.get("title")] + list(n.fm.get("aliases") or [])
        terms = [str(t).strip() for t in raw if t is not None and len(str(t).strip()) >= 2]
        if terms:
            out.append((str(n.fm["id"]), terms))
    return out


def tags_for(item: dict, tax: dict, terms: list) -> list:
    """一則新聞的標記：[{kind, key}]，不重複。比對標題＋RSS 摘要。"""
    title, summary = item["title"], item.get("rss_summary") or ""
    text = f"{title} {summary}"
    pairs = ([("topic", k) for k in topic_tags(text, tax)]
             + [("watch", k) for k in watch_tags(text, tax)]
             + [("note", nid) for nid, ts in terms if any(matches(t, text) for t in ts)]
             + [("jurisdiction", k) for k in jurisdiction_tags(title, summary, item["source_feed"], tax)])
    return [{"kind": k, "key": v} for k, v in dict.fromkeys(pairs)]
