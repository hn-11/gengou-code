"""Proposed round-12 gates, measured. Three candidate measures:
  A  mkmk Mark1 anchor == the same mark's mark-to-base MarkAnchor (exact)
  B  every Latin letter's ink box == Source Code Pro's at this weight (units)
  C  every Latin letter's ink area / box area == the donor's (ratio)
Usage: p_gate.py FONT [FONT ...]   (a VF is measured at its default)
"""
import sys, os, statistics
from pathlib import Path
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
import pathops
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
import verifylib as V

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CLASS = {"Light":300,"Regular":400,"Medium":500,"SemiBold":600,"Bold":700}
donor_u = TTFont(os.environ["SCP_VF_U"]); donor_i = TTFont(os.environ["SCP_VF_I"])

def measure(tf, loc=None):
    gs = tf.getGlyphSet(location=loc) if loc else tf.getGlyphSet()
    cmap = tf.getBestCmap()
    box, fill = {}, {}
    for ch in LETTERS:
        if ord(ch) not in cmap: continue
        p = pathops.Path(); gs[cmap[ord(ch)]].draw(p.getPen()); p = pathops.simplify(p)
        b = p.bounds
        if not b: continue
        box[ch] = b
        fill[ch] = abs(p.area)/((b[2]-b[0])*(b[3]-b[1]))
    return box, fill

def anchors(tf):
    base, mkmk = {}, {}
    for i, kind, subs, tags in V._pos_lookups(tf):
        for sub in subs:
            if kind == 4:
                for g, rec in zip(sub.MarkCoverage.glyphs, sub.MarkArray.MarkRecord):
                    if rec.MarkAnchor is not None:
                        base.setdefault(g, set()).add((rec.MarkAnchor.XCoordinate, rec.MarkAnchor.YCoordinate))
            elif kind == 6:
                for g, rec in zip(sub.Mark1Coverage.glyphs, sub.Mark1Array.MarkRecord):
                    if rec.MarkAnchor is not None:
                        mkmk.setdefault(g, set()).add((rec.MarkAnchor.XCoordinate, rec.MarkAnchor.YCoordinate))
    bad = [(g, a, sorted(base.get(g, ()))) for g, s in mkmk.items() for a in s
           if a not in base.get(g, set())]
    return len(mkmk), bad

def run(path, wght=None):
    tf = TTFont(path)
    sub = tf["name"].getDebugName(17) or tf["name"].getDebugName(2)
    ital = "Italic" in sub
    w = sub.replace("Italic","").replace("Roman","").strip() or "Regular"
    loc = None
    if "fvar" in tf:
        loc = {"wght": wght or CLASS[w]}
        w = {v: k for k, v in CLASS.items()}[loc["wght"]]
    d_box, d_fill = measure(donor_i if ital else donor_u, {"wght": CLASS[w]})
    f_box, f_fill = measure(tf, loc)
    dbox = sorted(((max(abs(f_box[c][k]-d_box[c][k]) for k in range(4)), c) for c in f_box if c in d_box), reverse=True)
    dfill = sorted(((abs(f_fill[c]/d_fill[c]-1), c) for c in f_fill if c in d_fill and d_fill[c]), reverse=True)
    n, bad = anchors(tf)
    name = Path(path).name + (f"@{loc['wght']}" if loc else "")
    print(f"{name:34s} B box worst {dbox[0][0]:8.1f}u ({dbox[0][1]}) 2nd {dbox[1][0]:6.1f}u | "
          f"C fill worst {dfill[0][0]*100:7.2f}% ({dfill[0][1]}) 2nd {dfill[1][0]*100:5.2f}% | "
          f"A mkmk {n} marks, {len(bad)} anchors differ" + (f" e.g. {bad[0]}" if bad else ""))

for p in sys.argv[1:]:
    if "=" in p and p.split("=")[0] == "wght":
        continue
    run(p, int(os.environ.get("WGHT", 0)) or None)
