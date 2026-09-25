#!/usr/bin/env python3
"""事件分組門檻校準（spec §6.2）。讀 tests/fixtures/cluster_calibration.yaml，
用實際的分組邏輯（assign_clusters）掃過一串門檻，每個門檻印出：

- 漏併：必須合併的兩則被分到不同組的對數
- 誤併：不同事件被併進同一組的對數

誤併比漏併糟（一個事件會藏住另一個），所以先挑誤併最少、再挑漏併最少的門檻。

用法：python scripts/calibrate_clusters.py [--model <名稱>]
相依：sentence-transformers（見 requirements-news.txt）
"""
import argparse
import sys
from pathlib import Path

import yaml

import clustering
from taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "cluster_calibration.yaml"
THRESHOLDS = [round(0.40 + 0.02 * k, 2) for k in range(28)]     # 0.40 … 0.94


def load_groups(path=FIXTURE):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return list(data["same"].values()) + [[t] for t in data["different"]]


def grid(groups, embed, thresholds):
    """回傳 [(門檻, 漏併對數, 誤併對數)]。embed 只呼叫一次。"""
    texts = [t for g in groups for t in g]
    gid = [k for k, g in enumerate(groups) for _ in g]
    vectors = dict(zip(texts, embed(texts)))
    cached = lambda ts: [vectors[t] for t in ts]
    items = [{"title": t, "score": 0} for t in texts]
    out = []
    for thr in thresholds:
        refs = clustering.assign_clusters(items, [], cached, thr, 0)
        split = wrong = 0
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                same, together = gid[i] == gid[j], refs[i] == refs[j]
                split += same and not together
                wrong += together and not same
        out.append((thr, split, wrong))
    return out


def main():
    tax = load_taxonomy()
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=tax["clustering"]["model"])
    a = ap.parse_args()
    embed = clustering.load_embedder(a.model)
    if embed is None:
        sys.exit("模型載入失敗，無法校準")
    groups = load_groups()
    must = sum(len(g) * (len(g) - 1) // 2 for g in groups)
    rows = grid(groups, embed, THRESHOLDS)
    print(f"模型：{a.model}（必須合併的共 {must} 對）")
    for thr, split, wrong in rows:
        print(f"  {thr:.2f}  漏併 {split:>2}  誤併 {wrong:>2}")
    best = min(rows, key=lambda r: (r[2], r[1]))
    ties = [r[0] for r in rows if (r[2], r[1]) == (best[2], best[1])]
    print(f"最佳：誤併 {best[2]}、漏併 {best[1]}，門檻 {ties[0]:.2f}–{ties[-1]:.2f}，建議取中間 {ties[len(ties) // 2]:.2f}")


if __name__ == "__main__":
    main()
