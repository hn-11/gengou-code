"""ASCII ink proof: shape with HarfBuzz, rasterize each glyph with
FreeType at 14px (unhinted), composite, print. `python render14.py
<font> <text> [feat=1,...] [ttb]`"""
import sys
from pathlib import Path

import freetype
import uharfbuzz as hb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M

SIZE = 14


def render(path, text, feats=None, direction=None, size=SIZE):
    face = freetype.Face(str(path))
    face.set_pixel_sizes(0, size)
    upm = face.units_per_EM
    infos, positions = M.shaper(path)(text, feats, direction=direction)
    cells = {}
    pen_x = pen_y = 0
    for info, pos in zip(infos, positions):
        face.load_glyph(info.codepoint,
                        freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER)
        bm = face.glyph.bitmap
        ox = round((pen_x + pos.x_offset) * size / upm) + face.glyph.bitmap_left
        oy = round((pen_y + pos.y_offset) * size / upm) + face.glyph.bitmap_top
        for r in range(bm.rows):
            for c in range(bm.width):
                v = bm.buffer[r * bm.pitch + c]
                if v:
                    cells[(oy - r, ox + c)] = max(cells.get((oy - r, ox + c), 0), v)
        pen_x += pos.x_advance
        pen_y += pos.y_advance
    return cells


def show(label, path, text, feats=None, direction=None, size=SIZE):
    cells = render(path, text, feats, direction, size)
    if not cells:
        print(f"  [{label}] (no ink)")
        return
    ys = [k[0] for k in cells]
    xs = [k[1] for k in cells]
    ramp = " .:-=+*#%@"
    print(f"  [{label}] {text!r} rows {min(ys)}..{max(ys)}  cols {min(xs)}..{max(xs)}")
    for y in range(max(ys), min(ys) - 1, -1):
        line = "".join(ramp[min(9, cells.get((y, x), 0) * 10 // 256)]
                       for x in range(min(xs), max(xs) + 1))
        print(f"   {y:4d} |{line}|")


if __name__ == "__main__":
    font, text = sys.argv[1], sys.argv[2]
    feats, direction = None, None
    for a in sys.argv[3:]:
        if a == "ttb":
            direction = "ttb"
        else:
            feats = {k: True for k in a.split(",")}
    show(Path(font).parent.name or font, font, text, feats, direction)
