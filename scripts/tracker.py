"""各國進度追蹤：把筆記歸到「國家 × 議題」的格子裡，並判斷每格的推動階段。

原則：
- 階段只來自你寫的法規筆記（40-regulations）：status 文字自動換算，或用 frontmatter 的 stage: 1–5 直接指定。
- 事件卡只當「動態」掛在格子的時間軸上，不會自動改階段——進度判斷要人來做。

國家的判斷規則在 taxonomy.yaml 的 jurisdiction_rules；議題與階段的關鍵詞寫在這個檔案。
"""
import re

import taxonomy
from tagging import matches

# ── 國家：規則在 taxonomy.yaml 的 jurisdiction_rules（新聞標記也用同一份），依那裡的順序顯示 ──
_TAX = taxonomy.load_taxonomy()
COUNTRIES = [(name, dict(keywords=r["keywords"], sources=r.get("sources") or []))
             for name, r in _TAX["jurisdiction_rules"].items()]

# 只在標題裡算數的泛稱（內文出現不代表事件發生在該國）
BODY_AMBIGUOUS = set(_TAX["title_only"])

# ── 議題：一則筆記可同時屬於多條 ──
TRACKS = [
    ("穩定幣", ["穩定幣", "稳定币", "stablecoin", "USDC", "USDT", "GENIUS", "穩定幣條例"]),
    ("結算／存款代幣", ["結算", "结算", "settle*", "存款代幣", "代幣化存款", "存款代币", "deposit token",
                    "tokenized deposit*", "tokenised deposit*", "CBDC", "wCBDC", "DvP", "央行貨幣",
                    "central bank money", "mBridge", "Pontes"]),
    ("代幣化證券／RWA", ["RWA", "代幣化證券", "代幣化股票", "代幣化基金", "代幣化債券", "tokenized stock*",
                     "tokenized securit*", "tokenized share*", "tokenized fund*", "tokenized treasur*",
                     "tokenized bond*", "tokenised securit*", "transfer agent", "轉讓代理", "創新豁免",
                     "innovation exemption", "real-world asset*"]),
    ("數位身分", ["數位身分", "数字身份", "可驗證憑證", "可驗證數位憑證", "verifiable credential*",
              "digital identit*", "digital ID", "DID", "SSI", "mDL", "eIDAS", "EUDI", "identity wallet", "CIP"]),
    ("虛擬資產業者", ["虛擬資產服務", "虛擬資產", "虚拟资产", "VASP", "CASP", "MiCA", "交易所牌照", "牌照",
                  "licens*", "licence", "交易平台", "custod*", "託管"]),
]

# ── 階段 ──
STAGES = {1: "研議", 2: "草案", 3: "已通過", 4: "施行中", 5: "市場運作"}
STAGE_HINT = {
    1: "諮詢、研究、評估",
    2: "提案、草案、預告",
    3: "已立法／核定，待子法或施行",
    4: "已生效，或主管機關已發布可依循的規範",
    5: "已有業者實際上線營運",
}
# status 文字 → 階段；由高到低比對，先命中者為準
STATUS_RULES = [
    (5, ["上線", "營運中", "商轉"]),
    (4, ["生效", "施行", "實施", "上路", "釋義", "指引", "發布", "開放", "試辦"]),
    (3, ["三讀", "通過", "公布", "簽署", "核定"]),
    (2, ["提案", "草案", "預告", "徵詢", "諮詢期"]),
    (1, ["研議", "研究", "評估", "諮詢"]),
]



def _text_of(note, body_chars=400):
    """比對用的文字：標題＋內文開頭（跳過 frontmatter 與段落標題）。"""
    body = re.sub(r"^##.*$", " ", note.get("body", ""), flags=re.M)
    return f"{note['title']} {body[:body_chars]}"


def countries_of(note):
    """一篇筆記屬於哪些國家。優先序：frontmatter jurisdiction → 來源機構 → 標題關鍵詞 → 內文關鍵詞。"""
    jur = str(note.get("jurisdiction") or "").strip()
    names = [c for c, _ in COUNTRIES]
    if jur:
        hit = [c for c in names if c in jur]
        if hit:
            return hit
    src = str(note.get("source_name") or "")
    by_src = [c for c, cfg in COUNTRIES if any(s and src.startswith(s) for s in cfg["sources"])]
    if by_src:
        return by_src
    title = note["title"]
    by_title = [c for c, cfg in COUNTRIES if any(matches(k, title) for k in cfg["keywords"])]
    if by_title:
        return by_title
    # 內文只認機構與中文國名；US、Europe 這類泛稱在內文裡太常順帶出現（例：「美元」「US dollar」）
    text = _text_of(note, 300)
    return [c for c, cfg in COUNTRIES
            if any(matches(k, text) for k in cfg["keywords"] if k not in BODY_AMBIGUOUS)]


def tracks_of(note):
    """一篇筆記屬於哪些議題。

    - frontmatter 寫了 tracks: [穩定幣, …] 就照寫的（手動覆寫）。
    - 法規筆記只看標題＋人寫的 topics：內文常順帶提到結算、牌照，看內文會分得太廣。
    - 事件卡看標題＋內文開頭。
    """
    names = [t for t, _ in TRACKS]
    manual = note.get("tracks")
    if manual:
        manual = [manual] if isinstance(manual, str) else list(manual)
        return [t for t in names if t in manual]
    text = note["title"] if note["folder"] == "40-regulations" else _text_of(note)
    out = [t for t, kws in TRACKS if any(matches(k, text) for k in kws)]
    if note["folder"] == "40-regulations":
        topics = set(note.get("topics") or [])
        if "穩定幣" in topics and "穩定幣" not in out:
            out.append("穩定幣")
        if "SSI" in topics and "數位身分" not in out:
            out.append("數位身分")
        if "RWA" in topics and "代幣化證券／RWA" not in out:
            out.append("代幣化證券／RWA")
        if not out and "金融法規" in topics:
            out.append("虛擬資產業者")
    return [t for t, _ in TRACKS if t in out]          # 維持固定順序


def stage_of(note):
    """法規筆記的推動階段：frontmatter stage 優先，否則由 status 文字換算。回傳 0 表示判斷不出來。"""
    try:
        s = int(note.get("stage") or 0)
        if 1 <= s <= 5:
            return s
    except (TypeError, ValueError):
        pass
    status = str(note.get("status") or "")
    for stage, words in STATUS_RULES:
        if any(w in status for w in words):
            return stage
    return 0


def build_matrix(notes):
    """回傳 {(國家, 議題): {"stage", "stage_note", "regs", "events"}}，只含有資料的格子。"""
    cells = {}
    for n in notes.values():
        if n["folder"] not in ("10-events", "40-regulations"):
            continue
        if n["folder"] == "10-events":
            try:
                if int(n.get("score") or 0) < 0:       # 負分（宣傳、偏題）不算動態
                    continue
            except (TypeError, ValueError):
                pass
        for c in countries_of(n):
            for t in tracks_of(n):
                cell = cells.setdefault((c, t), dict(stage=0, stage_note=None, regs=[], events=[]))
                if n["folder"] == "40-regulations":
                    cell["regs"].append(n)
                    st = stage_of(n)
                    if st > cell["stage"]:
                        cell["stage"], cell["stage_note"] = st, n
                else:
                    cell["events"].append(n)
    for cell in cells.values():
        cell["events"].sort(key=lambda x: x["date"], reverse=True)
        cell["regs"].sort(key=lambda x: stage_of(x), reverse=True)
    return cells
