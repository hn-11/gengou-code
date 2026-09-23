import sys, os, statistics
from pathlib import Path
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
import pathops
from fontTools.ttLib import TTFont

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CLASS = {"Light":300,"Regular":400,"Medium":500,"SemiBold":600,"Bold":700}

def ratios(tf, loc=None):
    gs = tf.getGlyphSet(location=loc) if loc else tf.getGlyphSet()
    cmap = tf.getBestCmap()
    out = {}
    for ch in LETTERS:
        if ord(ch) not in cmap: continue
        p = pathops.Path()
        gs[cmap[ord(ch)]].draw(p.getPen())
        p = pathops.simplify(p)
        b = p.bounds
        if not b: continue
        out[ch] = abs(p.area)/((b[2]-b[0])*(b[3]-b[1]))
    return out

donor_u = TTFont(os.environ["SCP_VF_U"])
donor_i = TTFont(os.environ["SCP_VF_I"])
for path in sys.argv[1:]:
    tf = TTFont(path)
    sub = tf["name"].getDebugName(17) or tf["name"].getDebugName(2)
    ital = "Italic" in sub
    w = sub.replace("Italic","").strip() or "Regular"
    d = ratios(donor_i if ital else donor_u, {"wght": CLASS[w]})
    f = ratios(tf)
    rel = {c: f[c]/d[c] for c in f if c in d and d[c]}
    vals = sorted(rel.items(), key=lambda kv: kv[1])
    print(f"{Path(path).name:28s} wght {CLASS[w]} ital={ital}  n={len(rel)} "
          f"min {vals[0][0]}={vals[0][1]:.3f} max {vals[-1][0]}={vals[-1][1]:.3f} median {statistics.median(rel.values()):.3f}")
