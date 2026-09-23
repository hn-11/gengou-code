"""What a ligature gate could measure, on every face:
  P  the shaped ligature's x/y offset (L2)
  Q  its ink extent against its cells and against the characters it is
     cut from (L3)
  R  its shape against the Monaspace glyph mona_ligs.json names (L1)
"""
import sys, os, json
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.statisticsPen import StatisticsPen
from fontTools.pens.boundsPen import BoundsPen
import uharfbuzz as hb
import build

LIGS = json.load(open("/home/user/shoyu-code-pro-jp/data/mona_ligs.json"))
CLASS = {"Light":300,"Regular":400,"Medium":500,"SemiBold":600,"Bold":700}
MONA = TTFont(os.environ["MONA_VF"])

def desc(gs, name):
    pen = StatisticsPen(gs); gs[name].draw(pen)
    bp = BoundsPen(gs); gs[name].draw(bp)
    if not bp.bounds or not pen.area: return None
    x0,y0,x1,y1 = bp.bounds; w,h = max(x1-x0,1), max(y1-y0,1)
    return ((pen.meanX-x0)/w, (pen.meanY-y0)/h, pen.stddevX/w, pen.stddevY/h, pen.correlation)

def shaper(path):
    blob = hb.Blob.from_file_path(path); f = hb.Font(hb.Face(blob))
    def sh(text):
        buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
        hb.shape(f, buf, {"calt": True, "liga": True})
        return list(buf.glyph_infos), list(buf.glyph_positions)
    return sh

def run(path):
    tf = TTFont(path); gs = tf.getGlyphSet(); cmap = tf.getBestCmap(); order = tf.getGlyphOrder()
    sub = tf["name"].getDebugName(17) or tf["name"].getDebugName(2)
    ital = "Italic" in sub
    w = CLASS[sub.replace("Italic","").replace("Roman","").strip() or "Regular"]
    cell = min(a for a, _ in tf["hmtx"].metrics.values() if a)
    mgs = MONA.getGlyphSet(location={"wght": max(w, 200)})
    sh = shaper(path)
    off, wfrac, hfrac, dmax, n = [], [], [], [], 0
    for seq, spec in LIGS.items():
        if any(ord(c) not in cmap for c in seq): continue
        infos, pos = sh(f"a {seq} b")
        if len(infos) != 5: continue
        n += 1
        off.append((abs(pos[2].x_offset), abs(pos[2].y_offset)))
        name = order[infos[2].codepoint]
        box = build._bounds(gs, name)
        parts = [build._bounds(gs, cmap[ord(c)]) for c in seq]
        if box and all(parts):
            lo, hi = min(p[1] for p in parts), max(p[3] for p in parts)
            wfrac.append(((box[2]-box[0])/(spec["cells"]*cell), seq))
            hfrac.append(((box[3]-box[1])/(hi-lo), seq))
        if len(spec["glyphs"]) == 1:
            a, b = desc(gs, name), desc(mgs, spec["glyphs"][0])
            if a and b:
                dmax.append((max(abs(x-y) for x, y in zip(a, b)), seq))
    wfrac.sort(); hfrac.sort(); dmax.sort(reverse=True)
    print(f"{Path(path).name:32s}{'  ital' if ital else '      '} n={n:3d} "
          f"P offsets max {max(off) if off else '-'} | "
          f"Q width {wfrac[0][0]:.3f}({wfrac[0][1]!r}) height {hfrac[0][0]:.3f}({hfrac[0][1]!r}) | "
          f"R shape worst {dmax[0][0]:.3f}({dmax[0][1]!r}) 2nd {dmax[1][0]:.3f}")

for p in sys.argv[1:]:
    run(p)
