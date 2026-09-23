"""Mutation harness for the Gengou verifiers (round 9).

A mutant is a built face, copied, damaged in one specific way, and the
DERIVED metadata (hmtx lsb, head bbox, hhea/vhea extents, xAvgCharWidth,
CFF charstring width) refitted exactly as a build that computed them
from the damaged outlines would -- so that only gates that look at the
DEFECT can fail, not the consistency gates around it.

Usage:  python mutants.py <ID>        (see mutants.py for the list)
"""
import io
import os
import re
import subprocess
import sys
from pathlib import Path

import pathops
import uharfbuzz as hb
from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

REPO = Path("/home/user/shoyu-code-pro-jp")
HERE = Path(__file__).resolve().parent
ENV = ("/tmp/claude-0/-home-user-shoyu-code-pro-jp/"
       "608d7d10-1a9e-5fcb-89e6-ebb09688cd94/scratchpad/r52env.sh")
sys.path.insert(0, str(REPO / "scripts"))


def load(path):
    tf = TTFont(str(path))
    tf.recalcBBoxes = False
    tf.recalcTimestamp = False
    return tf


def cff_top(tf):
    tag = "CFF " if "CFF " in tf else "CFF2"
    cff = tf[tag].cff
    return cff[cff.fontNames[0]] if tag == "CFF " else cff.topDictIndex[0]


def bounds(gs, name):
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return pen.bounds


def redraw(tf, name, transform, width=None):
    """Replace glyph `name`'s charstring (CFF, static) with the same
    outline drawn through `transform` (an affine 6-tuple), keeping the
    glyph's own hints out (a redrawn glyph is unhinted, as the build's
    own redrawn glyphs are with GENGOU_SKIP_AUTOHINT)."""
    td = cff_top(tf)
    gs = tf.getGlyphSet()
    old = td.CharStrings[name]
    old.decompile()
    adv = tf["hmtx"].metrics[name][0] if width is None else width
    private = old.private
    nominal = getattr(private, "nominalWidthX", 0)
    default = getattr(private, "defaultWidthX", 0)
    pen = T2CharStringPen(None if adv == default else adv - nominal, gs)
    gs[name].draw(TransformPen(pen, transform))
    new = pen.getCharString(private=private, globalSubrs=old.globalSubrs)
    td.CharStrings[name] = new
    if width is not None:
        lsb = tf["hmtx"].metrics[name][1]
        tf["hmtx"].metrics[name] = (width, lsb)


def set_advance(tf, name, width):
    """Advance of one glyph, in hmtx AND the charstring width."""
    redraw(tf, name, (1, 0, 0, 1, 0, 0), width=width)


def refit(tf):
    """Recompute everything a build derives from the outlines: lsb,
    head bbox, hhea extents, OS/2 xAvgCharWidth, and (JP) vmtx tsb from
    VORG plus vhea extents."""
    gs = tf.getGlyphSet()
    hmtx = tf["hmtx"].metrics
    boxes = {}
    for g in tf.getGlyphOrder():
        b = bounds(gs, g)
        if b:
            boxes[g] = b
            adv, _ = hmtx[g]
            hmtx[g] = (adv, otRound(b[0]))
    head = tf["head"]
    head.xMin = otRound(min(b[0] for b in boxes.values()))
    head.yMin = otRound(min(b[1] for b in boxes.values()))
    head.xMax = otRound(max(b[2] for b in boxes.values()))
    head.yMax = otRound(max(b[3] for b in boxes.values()))
    hhea = tf["hhea"]
    hhea.advanceWidthMax = max(a for a, _ in hmtx.values())
    hhea.minLeftSideBearing = otRound(min(hmtx[g][1] for g in boxes))
    hhea.minRightSideBearing = otRound(min(hmtx[g][0] - hmtx[g][1] - (b[2] - b[0])
                                           for g, b in boxes.items()))
    hhea.xMaxExtent = otRound(max(hmtx[g][1] + (b[2] - b[0]) for g, b in boxes.items()))
    widths = [w for w, _ in hmtx.values() if w]
    tf["OS/2"].xAvgCharWidth = otRound(sum(widths) / len(widths))
    if "vmtx" in tf and "VORG" in tf:
        vorg = tf["VORG"]
        vmtx = tf["vmtx"].metrics
        for g, b in boxes.items():
            if g in vmtx:
                origin = vorg.VOriginRecords.get(g, vorg.defaultVertOriginY)
                vmtx[g] = (vmtx[g][0], otRound(origin - b[3]))
        vhea = tf["vhea"]
        vhea.advanceHeightMax = max(h for h, _ in vmtx.values())
        vhea.minTopSideBearing = min(vmtx[g][1] for g in boxes)
        vhea.minBottomSideBearing = otRound(min(vmtx[g][0] - vmtx[g][1] - (b[3] - b[1])
                                                for g, b in boxes.items()))
        vhea.yMaxExtent = otRound(max(vmtx[g][1] + (b[3] - b[1]) for g, b in boxes.items()))
    return boxes


def verifier_for(path):
    name = Path(path).name
    marker = Path(path).with_suffix(".src")
    if marker.exists():
        name = Path(marker.read_text().strip()).name
    if "[wght]" in name:
        return "verify_latin_vf.py"
    if name.startswith("Gengou-") or name.startswith("GengouNFM"):
        return "verify_latin.py"
    return "verify.py"


def run_verifier(path, log):
    """Run the applicable verifier; return the FAIL lines that are not
    the expected 'carries hints' ones."""
    script = REPO / "scripts" / verifier_for(path)
    cmd = f'source {ENV} && cd {REPO} && python "{script}" "{path}"'
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    out = p.stdout + p.stderr
    Path(log).write_text(out)
    fails = [ln for ln in out.splitlines()
             if ln.startswith("FAIL") and ln.strip() != "FAILED" and "carries hints" not in ln
             and "carry hints" not in ln]
    return fails, out


# ---- ink proof ---------------------------------------------------------

def shaper(path, variations=None):
    blob = hb.Blob.from_file_path(str(path))
    font = hb.Font(hb.Face(blob))
    if variations:
        font.set_variations(variations)

    def shape(text, feats=None, direction=None, script=None, language=None):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        if direction:
            buf.direction = direction
        if script:
            buf.script = script
        if language:
            buf.language = language
        hb.shape(font, buf, feats or {})
        return list(buf.glyph_infos), list(buf.glyph_positions)
    return shape


def placed_paths(path, text, feats=None, variations=None, direction=None):
    """[(glyph name, pathops.Path at its shaped position, (x0,y0,x1,y1)
    or None)] for `text` shaped in the face at `path`; the pen advances
    along x (or down y for a ttb run)."""
    tf = TTFont(str(path))
    gs = tf.getGlyphSet(location=variations) if variations else tf.getGlyphSet()
    order = tf.getGlyphOrder()
    infos, positions = shaper(path, variations)(text, feats, direction=direction)
    out, pen_x, pen_y = [], 0, 0
    for info, pos in zip(infos, positions):
        name = order[info.codepoint]
        p = pathops.Path()
        gs[name].draw(p.getPen())
        moved = pathops.Path()
        p.draw(TransformPen(moved.getPen(),
                            (1, 0, 0, 1, pen_x + pos.x_offset, pen_y + pos.y_offset)))
        b = moved.bounds if list(moved.segments) else None
        out.append((name, moved, None if b is None else tuple(round(v) for v in b),
                    (pen_x, pen_y, pos.x_advance, pos.y_advance)))
        pen_x += pos.x_advance
        pen_y += pos.y_advance
    return out


def px(units, size=14, upm=1000):
    return round(units * size / upm, 2)


def overlap_area(p1, p2):
    return abs(pathops.op(p1, p2, pathops.PathOp.INTERSECTION).area)


def report_run(label, path, text, feats=None, variations=None, direction=None):
    rows = placed_paths(path, text, feats, variations, direction)
    print(f"  [{label}] {text!r}" + (f" {feats}" if feats else ""))
    for name, _p, b, (pen_x, pen_y, xa, ya) in rows:
        print(f"     {name:28s} pen=({pen_x},{pen_y}) adv=({xa},{ya}) ink={b}"
              + ("" if b is None else f"  (x {px(b[0])}..{px(b[2])}px, y {px(b[1])}..{px(b[3])}px @14px)"))
    return rows
