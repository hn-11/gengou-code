import sys
from pathlib import Path
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
from fontTools.ttLib import TTFont
import verifylib as V

def probe(path):
    tf = TTFont(path)
    base_anchor = {}   # mark glyph -> set of (x,y) in mark-to-base lookups
    mkmk_anchor = {}   # mark glyph -> set of (x,y) Mark1 anchors in mkmk
    for i, kind, subs, tags in V._pos_lookups(tf):
        for sub in subs:
            if kind == 4:
                for g, rec in zip(sub.MarkCoverage.glyphs, sub.MarkArray.MarkRecord):
                    a = rec.MarkAnchor
                    if a is not None:
                        base_anchor.setdefault(g, set()).add((a.XCoordinate, a.YCoordinate, rec.Class))
            elif kind == 6:
                for g, rec in zip(sub.Mark1Coverage.glyphs, sub.Mark1Array.MarkRecord):
                    a = rec.MarkAnchor
                    if a is not None:
                        mkmk_anchor.setdefault(g, set()).add((a.XCoordinate, a.YCoordinate, rec.Class))
    same = diff = 0
    worst = []
    for g, s in sorted(mkmk_anchor.items()):
        b = base_anchor.get(g)
        if not b:
            worst.append((g, "no base anchor", sorted(s)))
            continue
        for (x, y, c) in sorted(s):
            # nearest base anchor of the same mark
            d = min((abs(x-bx), abs(y-by)) for bx, by, bc in b)
            if d == (0, 0):
                same += 1
            else:
                diff += 1
                worst.append((g, (x, y), sorted(b), d))
    print(f"{Path(path).name}: marks with mkmk anchors {len(mkmk_anchor)}, exact match {same}, differ {diff}")
    for w in worst[:8]:
        print("   ", w)

for p in sys.argv[1:]:
    probe(p)
