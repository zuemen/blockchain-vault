"""新聞評分。規則全在 taxonomy.yaml 的 scoring，這裡只有算法。"""
from tagging import matches


def score(title: str, summary: str, tier: str, sc: dict, assume_core: bool = False):
    """回傳 (分數, 命中的權重詞)。

    1. 權重詞：標題命中算兩倍。generic 泛用詞只在標題也命中 core 詞時才算。
    2. 組合加分：a、b 兩組都命中才加。
    3. 封頂 cap，再扣雜訊詞。
    4. 命中 core（或來源本身就是主題查詢 assume_core）才給 tier 加分，否則扣 core_miss_penalty。
    """
    text = f"{title} {summary}"
    title_core = any(matches(c, title) for c in sc["core"])
    generic = set(sc.get("generic") or [])
    hits, s = [], 0
    for kw, w in sc["weights"].items():
        in_t, in_s = matches(kw, title), matches(kw, summary)
        if not (in_t or in_s):
            continue
        if kw in generic and not title_core:
            continue
        s += w * 2 if in_t else w
        hits.append(kw.rstrip("*"))
    for c in sc["combos"]:
        if any(matches(x, text) for x in c["a"]) and any(matches(y, text) for y in c["b"]):
            s += c["bonus"]
    s = min(s, sc["cap"])
    s += sc["noise_penalty"] * sum(1 for n in sc["noise"] if matches(n, text))
    core_hit = assume_core or any(matches(c, text) for c in sc["core"])
    s += sc["tier_bonus"].get(tier, 0) if core_hit else sc["core_miss_penalty"]
    return s, hits
