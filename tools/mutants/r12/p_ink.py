import sys, statistics
from pathlib import Path
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
import pathops
from fontTools.ttLib import TTFont

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def ratios(path):
    tf = TTFont(path)
    gs = tf.getGlyphSet()
    cmap = tf.getBestCmap()
    out = {}
    for ch in LETTERS:
        if ord(ch) not in cmap: continue
        p = pathops.Path()
        gs[cmap[ord(ch)]].draw(p.getPen())
        p = pathops.simplify(p)
        b = p.bounds
        if not b: continue
        area = abs(p.area)
        box = (b[2]-b[0])*(b[3]-b[1])
        out[ch] = area/box
    return out

for path in sys.argv[1:]:
    r = ratios(path)
    med = statistics.median(r.values())
    lo = min(r.items(), key=lambda kv: kv[1]); hi = max(r.items(), key=lambda kv: kv[1])
    print(f"{Path(path).name:28s} median {med:.3f}  min {lo[0]}={lo[1]:.3f} max {hi[0]}={hi[1]:.3f}  "
          f"e={r.get('e',0):.3f} o={r.get('o',0):.3f} n={r.get('n',0):.3f}")
