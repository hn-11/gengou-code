"""Measure D: a glyph's SHAPE against the donor it was cut from, by
descriptors that survive the build's scaling/shifting -- the ink
centroid inside its own box, the ink spread, and the correlation
(which flips sign under a mirror).
Usage: p_shape.py FONT ...   (Latin letters vs Source Code Pro, kana +
kanji vs Source Han Sans, Nerd icons vs the Symbols font)"""
import sys, os, statistics
from pathlib import Path
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
from fontTools.ttLib import TTFont
from fontTools.pens.statisticsPen import StatisticsPen
import build

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CLASS = {"Light":300,"Regular":400,"Medium":500,"SemiBold":600,"Bold":700}

def desc(gs, name):
    pen = StatisticsPen(gs)
    try:
        gs[name].draw(pen)
    except Exception:
        return None
    if not pen.area:
        return None
    from fontTools.pens.boundsPen import BoundsPen
    bp = BoundsPen(gs); gs[name].draw(bp)
    if not bp.bounds: return None
    x0, y0, x1, y1 = bp.bounds
    w, h = x1 - x0, y1 - y0
    if w < 10 or h < 10: return None
    return ((pen.meanX - x0)/w, (pen.meanY - y0)/h,
            pen.stddevX/w, pen.stddevY/h, pen.correlation)

def compare(tag, ours, theirs, chars, our_cmap, their_cmap, worst):
    for ch in chars:
        cp = ord(ch)
        if cp not in our_cmap or cp not in their_cmap: continue
        a = desc(ours, our_cmap[cp]); b = desc(theirs, their_cmap[cp])
        if a is None or b is None: continue
        d = max(abs(x - y) for x, y in zip(a, b))
        worst.append((d, tag, ch, tuple(round(v,3) for v in a), tuple(round(v,3) for v in b)))

def run(path):
    tf = TTFont(path)
    sub = tf["name"].getDebugName(17) or tf["name"].getDebugName(2)
    ital = "Italic" in sub
    w = sub.replace("Italic","").replace("Roman","").strip() or "Regular"
    gs = tf.getGlyphSet(location={"wght": CLASS[w]}) if "fvar" in tf else tf.getGlyphSet()
    cmap = tf.getBestCmap()
    worst = []
    donor = TTFont(os.environ["SCP_VF_I" if ital else "SCP_VF_U"])
    dgs = donor.getGlyphSet(location={"wght": CLASS[w]})
    compare("scp", gs, dgs, LETTERS, cmap, donor.getBestCmap(), worst)
    if 0x3042 in cmap:              # a JP face: kana and kanji from SHS
        shs = Path(os.environ["SHS_DIR"]) / dict(build.FACES)[w]
        sf = TTFont(str(shs)); sgs = sf.getGlyphSet(); scm = sf.getBestCmap()
        chars = [chr(c) for c in list(range(0x3041, 0x30FF))
                 + list(range(0x4E00, 0x9FA0, 97))]
        compare("shs", gs, sgs, chars, cmap, scm, worst)
    if 0xE0B0 in cmap:              # a Nerd Font face: icons from the symbols font
        nf = TTFont(os.environ["NF_SYMBOLS"]); ngs = nf.getGlyphSet(); ncm = nf.getBestCmap()
        chars = [chr(c) for c in sorted(ncm) if c in cmap][::7]
        compare("nf", gs, ngs, chars, cmap, ncm, worst)
    worst.sort(reverse=True)
    print(f"{Path(path).name:32s} n={len(worst):5d} worst " +
          "  ".join(f"{t}:{ch!r} {d:.3f}" for d, t, ch, a, b in worst[:3]))
    for d, t, ch, a, b in worst[:2]:
        if d > 0.05:
            print(f"      {t} {ch!r}: ours {a} donor {b}")

for p in sys.argv[1:]:
    run(p)
