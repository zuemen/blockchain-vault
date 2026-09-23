#!/usr/bin/env python3
"""vault 統計與未讀清單。 用法： python3 scripts/status.py [--unread]"""
import re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def fm_of(p):
    m = FM.match(p.read_text(encoding="utf-8"))
    d = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
    return d


def main():
    unread_only = "--unread" in sys.argv
    events = sorted((ROOT / "10-events").glob("*.md"))
    rows = []
    for f in events:
        d = fm_of(f)
        try:
            sc = int(d.get("score", 0))
        except ValueError:
            sc = 0
        rows.append((sc, d.get("status", "?"), d.get("source_tier", "?"),
                     d.get("title", f.stem)[:64], f.stem))

    if unread_only:
        rows = [r for r in rows if r[1] == "unread"]
        if not rows:
            print("沒有未讀事件 👍")
            return
        for sc, st, tier, title, stem in sorted(rows, reverse=True):
            mark = "★" if tier == "primary" else " "
            print(f"[{sc:>2}]{mark} {title}")
        return

    def count(d):
        return len(list((ROOT / d).glob("*.md")))

    print(f"事件 {count('10-events')}　概念 {count('20-concepts')}　機構 {count('30-entities')}"
          f"　法規 {count('40-regulations')}　地圖 {count('50-maps')}"
          f"　產出 {count('60-outputs')}　每日 {count('99-daily')}")

    st = Counter(r[1] for r in rows)
    print(f"事件狀態：未讀 {st.get('unread',0)}　已讀 {st.get('read',0)}　已引用 {st.get('cited',0)}")

    mat = Counter()
    for f in (ROOT / "20-concepts").glob("*.md"):
        mat[fm_of(f).get("maturity", "?")] += 1
    print(f"概念成熟度：seed {mat.get('seed',0)}　growing {mat.get('growing',0)}　stable {mat.get('stable',0)}"
          + ("　← seed 太多代表在囤積不在消化" if mat.get("seed", 0) > mat.get("growing", 0) else ""))

    tiers = Counter(r[2] for r in rows)
    print(f"事件來源：一手 {tiers.get('primary',0)}　媒體 {tiers.get('trade',0)}")

    orphan = [r for r in rows if r[1] == "unread" and r[0] and r[0] < 5]
    if orphan:
        print(f"可清理：{len(orphan)} 張低分未讀事件卡（make unread 看清單）")


if __name__ == "__main__":
    main()
