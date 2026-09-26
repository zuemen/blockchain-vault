import numpy as np

from clustering import assign_clusters, apply_limit, title_tokens, jaccard


def fake_embed(table):
    """測試用：以標題查表回傳正規化向量。"""
    def embed(texts):
        v = np.asarray([table[t] for t in texts], dtype=float)
        return v / np.linalg.norm(v, axis=1, keepdims=True)
    return embed


def it(title, score):
    return {"title": title, "score": score}


def test_joins_existing_cluster_and_opens_new_ones():
    table = {"A1": [1, 0, 0], "A2": [0.95, 0.05, 0], "B": [0, 1, 0], "C": [0, 0, 1]}
    existing = [{"title": "A1", "cluster_id": 7}, {"title": "old", "cluster_id": None}]
    table["old"] = [1, 0, 0]
    refs = assign_clusters([it("A2", 5), it("B", 9), it("C", 3)], existing, fake_embed(table), 0.75, 0.35)
    assert refs == [7, "new:1", "new:2"]            # B 分數最高，先開組


def test_new_items_merge_with_each_other():
    table = {"x": [1, 0], "y": [0.9, 0.1], "z": [0, 1]}
    refs = assign_clusters([it("x", 3), it("y", 8), it("z", 1)], [], fake_embed(table), 0.75, 0.35)
    assert refs[0] == refs[1] == "new:1" and refs[2] == "new:2"


def test_jaccard_fallback_when_no_model():
    items = [it("Canada big six banks tokenized deposits", 5), it("Canada's big six banks explore tokenized deposits", 4)]
    refs = assign_clusters(items, [], None, 0.75, 0.35)
    assert refs == ["new:1", "new:1"]
    assert jaccard(title_tokens(items[0]["title"]), title_tokens(items[1]["title"])) >= 0.35


def test_empty_input():
    assert assign_clusters([], [{"title": "a", "cluster_id": 1}], None, 0.75, 0.35) == []


def test_apply_limit_keeps_existing_and_top_new_groups():
    items = [it("a", 9), it("b", 2), it("c", 5), it("d", 1)]
    refs = ["new:1", "new:2", "new:2", 42]
    kept = apply_limit(items, refs, daily_top=1)
    assert [r for _, r in kept] == ["new:1", 42]


def test_calibration_fixture_shape():
    from calibrate_clusters import load_groups
    groups = load_groups()
    assert [len(g) for g in groups[:4]] == [3, 3, 2, 2]
    assert len(groups) == 14 and all(len(g) == 1 for g in groups[4:])


def test_grid_counts_split_and_wrong_pairs():
    from calibrate_clusters import grid
    table = {"a1": [1, 0, 0], "a2": [0.8, 0.6, 0], "b": [0.6, 0.8, 0], "c": [0, 0, 1]}
    rows = dict((thr, (split, wrong)) for thr, split, wrong in grid([["a1", "a2"], ["b"], ["c"]], fake_embed(table), [0.7, 0.9, 0.99]))
    assert rows[0.99] == (1, 0)      # 門檻太高：a1、a2 沒合併
    assert rows[0.7] == (0, 2)       # a2、b 太像（0.96），b 被併進 a 組
