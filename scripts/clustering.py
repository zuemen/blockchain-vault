"""事件分組：新報導跟近期報導比語意相似度，夠像就併進同一組，否則開新組。

模型與 numpy 延後到真的要用時才載入：測試與 Cloudflare build 不需要它們。
"""
import re
import sys
import unicodedata

# ── 標題 Jaccard（模型載入失敗時的備援；舊版 fetch_news.py 的去重方法）──
TITLE_NOISE = ["news", "breaking", "exclusive", "update", "report", "報導", "快訊",
               "獨家", "最新", "消息", "新聞"]
STOPWORDS = {"a", "an", "the", "to", "of", "for", "in", "on", "and", "or", "with", "as",
             "by", "at", "from", "is", "are", "be", "its", "it", "s", "into", "over",
             "after", "via", "new", "says", "said", "will", "could", "may", "than"}
STEM_LEN = 5


def title_tokens(title: str) -> frozenset:
    """英文取前 5 字母當詞幹、中文取 2-gram。"""
    t = unicodedata.normalize("NFKC", title).lower().replace("’", "'")
    for w in TITLE_NOISE:
        t = t.replace(w, " ")
    t = re.sub(r"'s\b", " ", t)
    words = {w[:STEM_LEN] for w in re.findall(r"[a-z0-9]+", t) if w not in STOPWORDS}
    grams = set()
    for run in re.findall(r"[一-鿿]+", t):
        grams |= {run[i:i + 2] for i in range(len(run) - 1)} or {run}
    return frozenset(words | grams)


def jaccard(a, b) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def cluster_text(item: dict) -> str:
    return f"{item['title']} {item.get('title_zh') or ''}".strip()


def load_embedder(model_name: str):
    """回傳 embed(texts) -> 已正規化的向量陣列；載入失敗回傳 None（呼叫端退回 Jaccard）。"""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
    except Exception as e:  # 套件沒裝、下載失敗、快取壞掉都一樣處理
        print(f"  ! 分組模型載入失敗，退回標題 Jaccard：{e}", file=sys.stderr)
        return None
    prefix = "query: " if "e5" in model_name else ""   # e5 系列要求輸入加前綴

    def embed(texts):
        return model.encode([prefix + t for t in texts], normalize_embeddings=True)
    return embed


def _similarities(new_texts, pool_texts, embed):
    """回傳 (新×既有, 新×新) 兩個相似度矩陣。"""
    if embed is None:
        nt = [title_tokens(t) for t in new_texts]
        pt = [title_tokens(t) for t in pool_texts]
        return [[jaccard(a, b) for b in pt] for a in nt], [[jaccard(a, b) for b in nt] for a in nt]
    import numpy as np
    n = np.asarray(embed(new_texts))
    p = np.asarray(embed(pool_texts)) if pool_texts else np.zeros((0, n.shape[1]))
    return n @ p.T, n @ n.T


def assign_clusters(new_items, existing, embed, threshold, jaccard_threshold):
    """回傳與 new_items 對齊的 cluster_ref：既有 cluster_id（int）或本次暫時代號 'new:<n>'。

    new_items 依分數高到低處理：高分的先開組，低分的才併進來。
    existing 是 /api/news/recent 的結果；cluster_id 為空的略過。
    embed 為 None 時用標題 Jaccard 與 jaccard_threshold。
    """
    if not new_items:
        return []
    pool = [e for e in existing if e.get("cluster_id")]
    s_pool, s_new = _similarities([cluster_text(i) for i in new_items],
                                  [cluster_text(e) for e in pool], embed)
    thr = threshold if embed is not None else jaccard_threshold
    refs, done, n = [None] * len(new_items), [], 0
    for i in sorted(range(len(new_items)), key=lambda k: -new_items[k]["score"]):
        best, best_ref = -1.0, None
        for p, e in enumerate(pool):
            if s_pool[i][p] > best:
                best, best_ref = float(s_pool[i][p]), e["cluster_id"]
        for j in done:
            if s_new[i][j] > best:
                best, best_ref = float(s_new[i][j]), refs[j]
        if best >= thr:
            refs[i] = best_ref
        else:
            n += 1
            refs[i] = f"new:{n}"
        done.append(i)
    return refs


def apply_limit(items, refs, daily_top):
    """併入既有分組的全留；新分組依組內最高分排序，只留前 daily_top 組。回傳 [(item, ref)]。"""
    best = {}
    for it, r in zip(items, refs):
        if isinstance(r, str):
            best[r] = max(best.get(r, it["score"]), it["score"])
    keep = set(sorted(best, key=lambda r: -best[r])[:daily_top])
    return [(it, r) for it, r in zip(items, refs) if not isinstance(r, str) or r in keep]
