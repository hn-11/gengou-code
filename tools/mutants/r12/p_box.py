import sys, os, statistics
from pathlib import Path
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CLASS = {"Light":300,"Regular":400,"Medium":500,"SemiBold":600,"Bold":700}

def boxes(tf, loc=None):
    gs = tf.getGlyphSet(location=loc) if loc else tf.getGlyphSet()
    cmap = tf.getBestCmap()
    out = {}
    for ch in LETTERS:
        if ord(ch) not in cmap: continue
        pen = BoundsPen(gs); gs[cmap[ord(ch)]].draw(pen)
        if pen.bounds: out[ch] = pen.bounds
    return out

donor_u = TTFont(os.environ["SCP_VF_U"]); donor_i = TTFont(os.environ["SCP_VF_I"])
for path in sys.argv[1:]:
    tf = TTFont(path)
    sub = tf["name"].getDebugName(17) or tf["name"].getDebugName(2)
    ital = "Italic" in sub
    w = sub.replace("Italic","").strip() or "Regular"
    d = boxes(donor_i if ital else donor_u, {"wght": CLASS[w]})
    f = boxes(tf)
    hs, ws = {}, {}
    for c in f:
        if c not in d: continue
        dh = d[c][3]-d[c][1]; dw = d[c][2]-d[c][0]
        if dh > 20: hs[c] = (f[c][3]-f[c][1])/dh
        if dw > 20: ws[c] = (f[c][2]-f[c][0])/dw
    hv = sorted(hs.items(), key=lambda kv: kv[1]); wv = sorted(ws.items(), key=lambda kv: kv[1])
    print(f"{Path(path).name:28s} height scale {hv[0][1]:.4f}({hv[0][0]})..{hv[-1][1]:.4f}({hv[-1][0]}) med {statistics.median(hs.values()):.4f} | "
          f"width scale {wv[0][1]:.4f}({wv[0][0]})..{wv[-1][1]:.4f}({wv[-1][0]}) med {statistics.median(ws.values()):.4f}")
