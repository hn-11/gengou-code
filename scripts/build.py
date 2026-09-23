#!/usr/bin/env python3
"""Assemble Gengou Code JP from live upstreams.

Gengou Code JP is an English terminal font with Japanese: the Latin layer
is Gengou Code (dist/latin, scripts/build_latin.py — Source Code Pro's
named instances with Monaspace's punctuation and ligatures), taken as
it is, and Source Han Sans JP supplies everything Gengou Code does not
have. Source Code Pro sets the terms: the 600 cell, the stroke weight of
each named weight (the Japanese face is the Source Han Sans weight whose
strokes match), and the line metrics (984 / -273: the line pitch of an
English terminal font, not a Japanese one).

  - Half-width layer:  every codepoint Gengou Code covers gets its one-cell
                       glyph — Latin, Greek, Cyrillic, box drawing, the
                       ligature-paired arrows and operators included.
                       There is no two-cell alternate: fwid and hwid are
                       dropped (see build_face).
  - Full-width layer:  Source Han Sans JP, untouched: kanji, kana, the
                       full-width symbols Gengou Code has no glyph for (① ※
                       ...). Its proportional leftovers (half-width kana
                       at 500, Hangul jamo at 920, ﬀ ...) are centred on
                       the grid (fit_to_grid).
  - Weights:           Source Code Pro's Light / Regular / Medium /
                       SemiBold / Bold (usWeightClass 300-700); the
                       Japanese glyphs come from the Source Han Sans
                       static whose '=' bar matches that instance's
                       (FACES).

Italic faces take the Gengou Code Italic + upright Japanese.

Families (suffix -> full-width advance):
  ""     1000  3:5 — Gengou Code plus Japanese at Source Han Sans's own
               advance; the natural setting for editors
  "Term" 1200  1:2 — full-width widened to two cells (widen_fullwidth) so
               a non-grid application lays Japanese out on the terminal
               grid too. Identical to the base family everywhere else:
               a terminal renders both the same way.

Usage:
  python scripts/build.py [FILTER]
  FILTER is a run of words: weight names ("Bold"), styles ("Italic" /
  "Upright") and variants ("Term" / "base" for the suffix-less family;
  "" alone is that family). A face must be one of the words of every
  kind named: "Regular" takes Regular and Regular Italic of every
  family, "Light Italic" one face per family, "Light Upright Term" one
  face, "Light Regular base" four (the release builds a family's two
  weights per job). Whole words, never a substring match (face_matches).
  With no FILTER, dist/GengouCodeJP*.otf is cleared before building, so a
  full build never leaves faces from an older roster behind. A filtered run
  never deletes anything.

Env (SHS_DIR required, the rest default):
  SHS_DIR   = dir with SourceHanSansJP-<Weight>.otf
  LATIN_DIR = dist/latin (default) — scripts/build_latin.py's output; it
              needs SCP_VF_U / SCP_VF_I / SS_VF_I / MONA_VF and must run
              first

Env (optional):
  GENGOU_VERSION = our own release version, e.g. "6.0.0" — stamps
                  head.fontRevision (MAJOR.MINOR), nameID 5 and the CFF
                  version. Unset keeps today's behaviour: the revision
                  stays whatever Source Han Sans shipped.
  GENGOU_SKIP_AUTOHINT = 1 skips otfautohint (quick local iterations)
"""

import concurrent.futures
import contextlib
import copy
import dataclasses
import json
import logging
import math
import os
import shutil
import string
import sys
import tempfile
import traceback
import unicodedata
from pathlib import Path

import pathops
from fontTools.misc.roundTools import otRound
from fontTools.otlLib import builder as otl
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parent.parent
# the half-width cell: Source Code Pro's own advance (upm 1000), which
# Gengou Code keeps as it is — one number, since v5 rescales nothing
CELL = 600
FULLWIDTH = 1000    # full-width advance of the CJK layer (upm 1000)
MONA_CELL = 1240    # Monaspace advance (upm 2000)

# Adobe-Japan1-7 defines CIDs 0..23057; a PDF consumer that assumes the
# ROS is really Adobe-Japan1 decodes those CIDs as their standard
# characters. Our appended glyphs are NOT Adobe-Japan1 characters, so
# allocation starts above the defined range (still < 65535).
CID_ALLOC_START = 23058
CID_MAX = 65534

# Unicode Combining Diacritical Marks block. SCP has these (as spacing
# clones centered in their own 600-unit cell — SCP is monospace, so even a
# bare accent gets a full column); graft_halfwidth() grafts them at 0
# advance instead of CELL so they behave as real combining marks.
COMBINING_MARKS = range(0x0300, 0x0370)

# Provenance stamped into every face (name IDs 0/3/8/11, OS/2 achVendID).
# The vendor ID is ours by convention only — Microsoft's registry is opt-in
# and this one is not registered; it just has to stop being Adobe's 'ADBO'.
PROJECT_URL = "https://github.com/hn-11/shoyu-code-pro-jp"
PROJECT_COPYRIGHT = f"Copyright 2026 hn-11 ({PROJECT_URL})"
VENDOR_ID = "GNGO"

# OS/2 usWeightClass per output weight, the STAT table's wght axis values
# and the Source Code Pro VF wght the Latin is instanced at (Source Code
# Pro's own named instances: its user wght is usWeightClass).
WEIGHT_CLASS = {"Light": 300, "Regular": 400, "Medium": 500,
                "SemiBold": 600, "Bold": 700}


# The Latin donor faces scripts/build_latin.py writes under LATIN_DIR:
# (family name, PostScript family). The released Gengou Code, exactly.
LATIN_FAMILY = ("Gengou Code", "GengouCode")


def latin_face_path(latin_dir, weight, italic):
    _, ps_family = LATIN_FAMILY
    return Path(latin_dir) / f"{ps_family}-{weight}{'Italic' if italic else ''}.otf"


# {family suffix: widen the full-width advances to two cells}
VARIANTS = {
    "": False,      # 3:5 — Gengou Code plus Japanese at 1000
    "Term": True,   # 1:2 terminal grid (600:1200), widen_fullwidth
}

# (output weight name, Source Han Sans static file): the Source Han Sans
# weight whose '=' bar (U+FF1D, in the same 1000 em) matches the Source
# Code Pro instance the Latin comes from — measured, not by name:
#
#   Light    SCP 300  37u   Source Han Sans ExtraLight  36u
#   Regular  SCP 400  62u   Source Han Sans Normal      63u
#   Medium   SCP 500  73u   Source Han Sans Regular     69u
#   SemiBold SCP 600  83u   Source Han Sans Medium      83u
#   Bold     SCP 700 104u   Source Han Sans Bold       101u
#
# (Source Han Sans's own Light 49u, Heavy 120u and Source Code Pro's
# ExtraLight 28u / Black 120u have no partner in the other family and are
# not built.) Monaspace bottoms out at wght 200 (bar ~53u at our scale);
# Light's surplus is eroded away in the static faces (vfsource.VFSource.matched).

# the weights every face takes its width decisions from
# (reference_steps): our Regular's donor for the advance, the heaviest
# for the ink, which grows with the weight
REFERENCE_SHS = "SourceHanSansJP-Normal.otf"
INK_SHS = "SourceHanSansJP-Bold.otf"

FACES = [
    ("Light", "SourceHanSansJP-ExtraLight.otf"),
    ("Regular", "SourceHanSansJP-Normal.otf"),
    ("Medium", "SourceHanSansJP-Regular.otf"),
    ("SemiBold", "SourceHanSansJP-Medium.otf"),
    ("Bold", "SourceHanSansJP-Bold.otf"),
]


def load_ligatures(path=None):
    """data/mona_ligs.json -> {sequence: {cells, glyphs, group[, at]}}."""
    with open(path or ROOT / "data" / "mona_ligs.json") as fp:
        return json.load(fp)


LIGATURES = load_ligatures()   # module-level default; passed explicitly

# UI names shown by font-feature pickers, one per feature we author.
# English by convention (the OT name records these land in are 3/1/0x409);
# they mirror README's ss table. Every ligature group in mona_ligs.json
# must appear here — tests/test_build.py enforces that.
GROUP_NAMES = {
    "ss01": "Comparison & equality",
    "ss02": "Arrows",
    "ss03": "Markup",
    "ss04": "Pipes",
    "ss05": "Colons",
    "ss06": "Dots",
    "ss07": "Comments",
    "ss08": "Repetition, logic & misc",
    "cv99": "Alternate ligature designs",
}


def _glyphset(source):
    """`source` as a glyph set: a TTFont's, or a glyph set handed over as
    is (TTFont.getGlyphSet(location=...) for a VF probed at a location
    without instancing it — see vfsource.VFSource._probe_bar)."""
    return source.getGlyphSet() if hasattr(source, "getGlyphSet") else source


def contour_boxes(font, glyph_name):
    """(xMin, yMin, xMax, yMax) of each contour of `glyph_name`, open
    or closed, from the curves themselves and not their control points
    -- a '=' bar with rounded ends measures thicker than it is
    otherwise. `font` is a TTFont or a glyph set (_glyphset). One
    BoundsPen per contour, split at each moveTo; this replaced a
    105-line extremum solver that agreed with it on every glyph of
    every donor (round 10)."""
    pen = RecordingPen()
    _glyphset(font)[glyph_name].draw(pen)
    contours, cur = [], []
    for op, args in pen.value:
        if op == "moveTo" and cur:
            contours.append(cur)
            cur = []
        cur.append((op, args))
        # a TrueType contour with no on-curve point at all is drawn as
        # a bare qCurveTo ending in None, with no moveTo to split on
        # (611 of the Nerd Fonts symbols); closing on the end of the
        # path is what separates those
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []
    if cur:
        contours.append(cur)
    out = []
    for ops in contours:
        box = BoundsPen(None)
        for op, args in ops:
            getattr(box, op)(*args)
        if box.bounds is not None:
            out.append(box.bounds)
    return out


def bar_thickness(font, glyph_name):
    """Thickness of '=' — our stroke-weight probe.

    The minimum contour height over all contours: both bars of '=' have the
    same thickness, so min-height is robust against contour order (and
    against a font whose '=' carries extra bits). `font` is a TTFont or a
    glyph set."""
    heights = [b[3] - b[1] for b in contour_boxes(font, glyph_name)]
    return min(heights) if heights else 0


def draw_clean(draws, pen, simplify=True):
    """Draw (glyphset, glyph, transform) triples through skia-pathops
    simplify before hitting the charstring pen. Variable-font instancing
    leaves self-intersecting outlines (A/K/x/R... — masters keep overlaps
    for interpolation; Adobe removes them only in static releases), and
    some rasterizers render seams at the overlaps.

    simplify=False skips the pathops pass entirely (straight through
    TransformPen): building a VARIABLE font's masters needs point-for-point
    compatible outlines across weights, and pathops.simplify's boolean ops
    do not guarantee that — a self-intersection's topology can resolve
    differently at different weights, at which point the master glyphs are
    no longer interpolatable at all (confirmed: this is what
    scripts/build_latin_vf.py's masters need)."""
    if not simplify:
        for gs, gname, t in draws:
            gs[gname].draw(TransformPen(pen, t))
        return
    path = pathops.Path()
    for gs, gname, t in draws:
        gs[gname].draw(TransformPen(path.getPen(), t))
    with contextlib.suppress(pathops.PathOpsError):
        path = pathops.simplify(path, clockwise=path.clockwise)  # degenerate outline: keep as drawn
    path.draw(pen)


def pen_width(private, advance):
    """CFF charstring width operand: omitted when equal to defaultWidthX,
    otherwise encoded relative to nominalWidthX."""
    default = getattr(private, "defaultWidthX", 0)
    nominal = getattr(private, "nominalWidthX", 0)
    return None if advance == default else advance - nominal


@dataclasses.dataclass
class BuildState:
    """What the passes of one build tell each other about the glyphs it
    made, kept on the font as `font.state` (state_of).

    `built` is every glyph this build made, and nothing ever leaves it:
    their names come from Source Han Sans's own CID space, so a pass
    that looks a glyph up by name in a reference font (fit_to_grid)
    must know not to. `appended` is the subset add_latin_fd re-homes
    into the Latin FontDict, which an appender can opt out of
    (narrow_halfwidth does); once add_latin_fd has run, `latin_fd` is
    that FontDict's index and nothing may be appended after it.
    `redrawn` is every glyph whose charstring WE generated -- a
    T2CharStringPen's output carries no hints, so autohint_face
    re-hints these after the face is saved and Source Han Sans's own
    untouched glyphs keep theirs. `pinned_cell` is what
    narrow_halfwidth and the Latin graft put on one cell for
    fit_to_grid to leave alone. `vorigin` caches vmtx_origin; the CID
    allocator keeps its cursor in `used_cids` / `next_cid`."""
    built: set = dataclasses.field(default_factory=set)
    appended: set = dataclasses.field(default_factory=set)
    redrawn: set = dataclasses.field(default_factory=set)
    pinned_cell: set = dataclasses.field(default_factory=set)
    vorigin: dict = dataclasses.field(default_factory=dict)
    used_cids: set | None = None
    next_cid: int = CID_ALLOC_START
    latin_fd: int | None = None


def state_of(font):
    """The BuildState of `font`, made on first use."""
    state = getattr(font, "state", None)
    if state is None:
        state = font.state = BuildState()
    return state


def alloc_glyph_name(font):
    """Allocate an unused CID. Subset OTFs have sparse CIDs (SHS JP tops
    out at 65497 with only ~18k glyphs), so len(order) collides with real
    names and max+1 overflows 65534 — walk the gaps instead, starting
    above the Adobe-Japan1-7 defined range (see CID_ALLOC_START)."""
    state = state_of(font)
    if state.used_cids is None:
        state.used_cids = {int(g[3:]) for g in font.getGlyphOrder()
                           if g.startswith("cid") and g[3:].isdigit()}
    n = state.next_cid
    while n in state.used_cids:
        n += 1
    if n > CID_MAX:
        raise RuntimeError("CID space exhausted")
    state.used_cids.add(n)
    state.next_cid = n + 1
    return f"cid{n:05d}"


def charstring_box(cs):
    """(xMin, yMin, xMax, yMax) of a freshly built charstring, or None for
    a blank one — appended glyphs used to get lsb=0, which lies to
    anything that trusts hmtx over the outline."""
    try:
        return cs.calcBounds(None)
    except Exception as exc:
        print(f"  WARNING: calcBounds failed for appended glyph ({exc})")
        return None


def charstring_lsb(cs):
    """xMin of a freshly built charstring."""
    box = charstring_box(cs)
    return otRound(box[0]) if box else 0


def vmtx_origin(font, glyph):
    """The vertical origin of a glyph already in `font` — its own yMax
    plus its top side bearing, which is what CFF's VORG states directly.
    Cached, because it needs the glyph set."""
    cache = state_of(font).vorigin
    if glyph not in cache:
        box = _bounds(font.getGlyphSet(), glyph)
        cache[glyph] = font["vmtx"].metrics[glyph][1] + (box[3] if box else 0)
    return cache[glyph]


def vmtx_donor(font):
    """Glyph whose vertical metrics the appended glyphs inherit: 日, or
    the first of a few others a face is sure to have (they all carry
    Source Han Sans's one em and 880 origin). Resolve once per call
    site — getBestCmap() per glyph was the hot spot."""
    if "vmtx" not in font:
        return None
    cmap = font.getBestCmap()
    for cp in (0x65E5, 0xFF61, 0xFF9F, 0x0041):
        g = cmap.get(cp)
        if g is not None and g in font["vmtx"].metrics:
            return g
    return None


def note_redrawn(font, names):
    """Remember glyphs whose charstring WE generated. T2CharStringPen output
    carries no hints, so every glyph that passes through it — grafted,
    fitted, shifted, widened — is re-hinted by autohint_face() after the
    face is saved. Source Han Sans's own untouched glyphs keep theirs."""
    state_of(font).redrawn.update(names)


def append_glyph(font, td, name, cs, fd_index, width, lsb=None, vdonor=None):
    """Append one built glyph. Returns its outline box (None if blank),
    which it measures anyway for the side bearing — update_bbox_after's
    caller wants it and should not pay for it twice.

    A glyph appended at width 0 is a combining mark, and takes 0 for its
    vertical advance as well as its horizontal one. Copying the donor's
    1000 gave every grafted accent a full cell of vertical advance it
    must not have; Source Han Sans's own thirteen marks keep the 1000 it
    ships them with, which is its vertical design, not ours to rewrite."""
    order = font.getGlyphOrder()
    order.append(name)
    # the same list object for CFF fonts; a CFF2 has no charset, its
    # names are post's
    if getattr(td, "charset", order) is not order:
        td.charset.append(name)
    if fd_index is not None:     # CID-keyed; a plain CFF has no FDSelect
        td.FDSelect.gidArray.append(fd_index)
    if hasattr(td.CharStrings, "charStringsIndex"):
        i = len(td.CharStrings.charStringsIndex.items)
        td.CharStrings.charStringsIndex.append(cs)
        td.CharStrings.charStrings[name] = i
    else:                        # a plain, non-indexed CFF (the fixtures)
        td.CharStrings[name] = cs
    box = charstring_box(cs)
    font["hmtx"].metrics[name] = (
        width, (otRound(box[0]) if box else 0) if lsb is None else lsb)
    if "vmtx" in font and vdonor is not None:
        # the donor's vertical ORIGIN, not its top side bearing. tsb is
        # measured down from each glyph's OWN yMax, so copying it moves
        # the origin by the difference between the two: every glyph this
        # build appends inherited U+FF61's 637 against its own yMax of
        # 243, and stood 250-570 units low in a vertical run under any
        # shaper that reads vmtx rather than VORG — FreeType's vertical
        # layout does, and reads no VORG at all. The CFF VORG in the same
        # file said 880 for all of them, so the two tables disagreed
        font["vmtx"].metrics[name] = (
            0 if width == 0 else font["vmtx"].metrics[vdonor][0],
            otRound(vmtx_origin(font, vdonor) - (box[3] if box else 0)))
    note_redrawn(font, [name])
    state = state_of(font)
    if state.latin_fd is not None:
        raise RuntimeError(f"{name} appended after add_latin_fd: it would keep "
                           "the FontDict of whatever it was drawn against")
    # two sets, because they answer two questions (BuildState says which)
    state.built.add(name)
    state.appended.add(name)
    font.setGlyphOrder(order)
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    font["maxp"].numGlyphs = len(order)
    return box

def append_context(font):
    """What appending a glyph next to 'A' needs: (top dict, cmap, FD
    index, that FD's Private dict, vmtx donor). The FD (and its
    nominalWidthX, which pen_width() offsets against) is the one 'A'
    already lives in. Every appender uses it: in the JP faces
    add_latin_fd() later moves all appended glyphs into a copy of A's FD,
    and a width encoded against any other FD's nominalWidthX would then
    be wrong (the ligatures were, by 510u); the Latin faces have one FD.

    A plain CFF has no FDSelect at all: the index is None and the Private
    dict the top dict's own. Every face this repo builds is CID-keyed,
    Gengou Code included; the branch is for a caller handed something else
    (the unit tests' fixtures). A face with no vmtx has no donor
    either. A variable font's CFF2 has no names of its own and keeps its
    one top dict in an index; nerdpatch appends to the variable Gengou
    Code too."""
    cff = font["CFF2" if "CFF2" in font else "CFF "].cff
    td = cff.topDictIndex[0] if "CFF2" in font else cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    a = cmap[ord("A")]
    return (td, cmap, glyph_fd(font, td, a), glyph_private(font, td, a),
            vmtx_donor(font))


def graft_outline(font, ctx, draws, width, simplify=True):
    """Draw `draws` (see draw_clean) into a new glyph of `width` next to
    'A' and return its name: the one way every import puts a donor's
    outline into this font, so the FontDict, its nominalWidthX and the
    vertical origin come from one place (append_context) rather than
    from each site's own copy of the sequence."""
    td, _cmap, fd_index, private, vdon = ctx
    pen = T2CharStringPen(pen_width(private, width), None)
    draw_clean(draws, pen, simplify=simplify)
    name = alloc_glyph_name(font)
    append_glyph(font, td, name, pen.getCharString(private=private),
                 fd_index, width, None, vdon)
    return name


def glyph_fd(font, td, name):
    """The FontDict index `name` lives in, or None in a plain CFF (which
    has one Private dict and no FDSelect — the tests' fixtures; every
    face this repo builds is CID-keyed). A CFF2 with a single FontDict
    may leave FDSelect out as well, and then this is None too."""
    return td.FDSelect[font.getGlyphID(name)] if hasattr(td, "FDSelect") else None


def glyph_private(font, td, name):
    """The Private dict a charstring for `name` is written against: its
    own FD's, the only FD's in a CFF2 without FDSelect, or the top
    dict's in a plain CFF."""
    fd = glyph_fd(font, td, name)
    if fd is None:
        return td.FDArray[0].Private if hasattr(td, "FDArray") else td.Private
    return td.FDArray[fd].Private


def set_cmap(font, mapping, add_new=False):
    """Write {codepoint: glyph name} into every Unicode cmap subtable.
    Existing entries are replaced; a codepoint the subtable lacks is added
    only with `add_new`, and then only where the subtable can hold it (a
    BMP-only format 0/4/6 subtable cannot take a supplementary plane
    codepoint)."""
    for table in font["cmap"].tables:
        # a format 14 subtable is Unicode too, but its map is the
        # variation-sequence dict; the `.cmap` it carries is a dummy
        if not table.isUnicode() or table.format == 14:
            continue
        bmp_only = table.format in (0, 4, 6)
        for cp, name in mapping.items():
            if cp in table.cmap or (add_new and not (bmp_only and cp > 0xFFFF)):
                table.cmap[cp] = name


def graft_halfwidth(base, latin):
    """Give `base` (Source Han Sans JP) its half-width layer: every
    codepoint the Latin donor (Gengou Code, dist/latin) has gets the
    donor's one-cell glyph, at the donor's own size — Latin, Greek,
    Cyrillic, box drawing, the ligature-paired arrows and operators,
    everything an English terminal font sets in one cell. The glyph
    Source Han Sans had for the codepoint (full-width for → ─ ≠ in the
    JIS tradition, proportional for A é α) is left in the font and
    reported in `replaced`, which the vertical features are re-pointed
    from (repoint_features).

    Combining marks (U+0300-U+036F) are the one case that must NOT get
    CELL: SCP draws them as if standalone — a spacing clone centered in
    its own 600-unit cell, same as every other SCP glyph — but a proper
    combining accent has to have 0 advance so 'k' + U+0301 shapes as one
    cell, not two. Grafted at 0 advance, with the outline shifted left by
    one CELL so the ink lands centered over the PRECEDING glyph's cell.

    Returns (grafted glyph count, {codepoint: the Source Han Sans glyph
    replaced}, {donor glyph: our glyph} for the variant wiring, the set
    of grafted 0-advance mark glyphs)."""
    scp_cm, scp_gs = latin.getBestCmap(), latin.getGlyphSet()
    ctx = append_context(base)
    td, bcm, fd_index, private, vdon = ctx
    new_map = {}
    default_map = {}  # donor glyph name -> our glyph name (variant wiring)
    made = {}         # (donor glyph, is_mark) -> our glyph (dedup aliases)
    marks = set()
    replaced = {}
    for cp in sorted(scp_cm):
        src = scp_cm[cp]
        is_mark = cp in COMBINING_MARKS
        # several codepoints often share one donor glyph (SCP's cmap
        # aliases) — one grafted glyph per source keeps default_map 1:1
        # so zero/cv/salt wiring survives for all of them; a source glyph
        # shared by a mark and a spacing codepoint gets both renderings
        key = (src, is_mark)
        if key not in made:
            # the donor's own advance, not an assumed cell: every glyph
            # Gengou Code cmaps is one cell today, and a two-cell one it
            # ever adds must be grafted two cells wide, not overprinted
            width = 0 if is_mark else latin["hmtx"][src][0]
            name = graft_outline(base, ctx, [(scp_gs, src, (1, 0, 0, 1, -CELL if is_mark else 0, 0))],
                                 width)
            made[key] = name
            if is_mark:
                marks.add(name)
            # variant wiring keys off the donor glyph, one rendering per
            # glyph: the spacing one is wired — variants are chosen on
            # letters and symbols, the accent keeps its default
            if not is_mark or src not in default_map:
                default_map[src] = name
        new_map[cp] = made[key]
        if cp in bcm:
            replaced[cp] = bcm[cp]

    # Drop legacy non-Unicode subtables (Mac (1,0) format 6): they still
    # point at the old proportional Latin, and FontForge unifies subtables
    # on load — the conflict silently drops ~40 ASCII slots after
    # cidFlatten, which is how the Nerd Font variants lost 'M' et al.
    base["cmap"].tables = [t for t in base["cmap"].tables if t.isUnicode()]
    set_cmap(base, new_map, add_new=True)   # donor-only codepoints are new entries
    return len(made), replaced, default_map, marks


def _remap_scp_tag(tag):
    """SCP feature tags, shifted around our own: ss01-ss10 -> ss11-ss20
    because ss01-ss08 are the ligature groups; ss11 and up are already
    shifted (Gengou Code carries them that way); cv/zero/salt keep their
    names. Everything else (case, frac, sups...) is not a glyph variant
    we mount."""
    if tag in ("zero", "salt") or tag.startswith("cv"):
        return tag
    if tag.startswith("ss") and tag[2:].isdigit():
        n = int(tag[2:])
        return f"ss{n + 10:02d}" if n <= 10 else tag
    return None


def _unwrap(lookup):
    """(LookupType, [subtables]) with Extension (type 7) unwrapped."""
    if lookup.LookupType != 7:
        return lookup.LookupType, lookup.SubTable
    subs = [st.ExtSubTable for st in lookup.SubTable]
    kind = subs[0].LookupType if subs else None
    return kind, subs


def shift_anchors(font, shifts):
    """Move each glyph's GPOS anchors with its outline. fit_to_grid and
    widen_fullwidth re-centre a glyph in a new advance, and an anchor is
    a point ON the glyph: leave it and a combining mark lands where the
    ink used to be. Source Han Sans attaches the Bopomofo tone marks
    this way, and widening ㄓ to two cells moved its ink 100u right while
    the anchor stayed, putting ˫ over the letter.

    `shifts` is {glyph name: how far its outline moved}. GPOS type 9
    (Extension) is unwrapped by _unwrap_pos; types 3 (cursive), 4
    (mark-to-base), 5 (mark-to-ligature) and 6 (mark-to-mark) carry the
    anchors. Returns the number of anchors moved."""
    if "GPOS" not in font or not shifts:
        return 0
    moved = 0
    for lookup in font["GPOS"].table.LookupList.Lookup:
        kind, subtables = _unwrap_pos(lookup)
        for sub in subtables:
            moved += _shift_subtable_anchors(kind, sub, shifts)
    return moved


def _unwrap_pos(lookup):
    """(LookupType, [subtables]) for a GPOS lookup, with Extension
    unwrapped. GPOS numbers Extension 9, where GSUB numbers it 7 (and
    GPOS's own 7 is contextual positioning), so this is not _unwrap."""
    if lookup.LookupType != 9:
        return lookup.LookupType, lookup.SubTable
    subs = [st.ExtSubTable for st in lookup.SubTable]
    return (subs[0].LookupType if subs else None), subs


def _shift_subtable_anchors(kind, sub, shifts):
    def move(anchor, dx):
        if anchor is None or not dx:
            return 0
        anchor.XCoordinate += dx
        return 1

    def by_coverage(coverage, records, pick):
        n = 0
        if coverage is None or records is None:
            return 0
        for name, rec in zip(coverage.glyphs, records):
            dx = shifts.get(name)
            if dx:
                for anchor in pick(rec):
                    n += move(anchor, dx)
        return n

    if kind == 3:      # cursive attachment
        return by_coverage(getattr(sub, "Coverage", None),
                           getattr(sub, "EntryExitRecord", None),
                           lambda r: (r.EntryAnchor, r.ExitAnchor))
    if kind in (4, 5, 6):
        marks = "Mark1" if kind == 6 else "Mark"
        n = by_coverage(getattr(sub, f"{marks}Coverage", None),
                        getattr(getattr(sub, f"{marks}Array", None), "MarkRecord", None),
                        lambda r: (r.MarkAnchor,))
        if kind == 4:
            n += by_coverage(getattr(sub, "BaseCoverage", None),
                             getattr(getattr(sub, "BaseArray", None), "BaseRecord", None),
                             lambda r: r.BaseAnchor)
        elif kind == 5:
            n += by_coverage(
                getattr(sub, "LigatureCoverage", None),
                getattr(getattr(sub, "LigatureArray", None), "LigatureAttach", None),
                lambda r: [a for comp in r.ComponentRecord for a in comp.LigatureAnchor])
        else:
            n += by_coverage(getattr(sub, "Mark2Coverage", None),
                             getattr(getattr(sub, "Mark2Array", None), "Mark2Record", None),
                             lambda r: r.Mark2Anchor)
        return n
    return 0


def _subst_pairs(kind, subtables, tag):
    """(src, dst) pairs from a Single (1) or Alternate (3) subst lookup."""
    if kind == 1:
        for st in subtables:
            yield from st.mapping.items()
    elif kind == 3:
        for st in subtables:
            for src, alts in st.alternates.items():
                if alts:
                    yield src, alts[0]
    else:
        print(f"  warning: {tag}: unsupported GSUB LookupType {kind}, skipped")


def _scp_ui_name(scp, feature_params):
    """UI name text for an SCP feature's FeatureParams, or None.

    StylisticSet (ssNN) carries it in UINameID, CharacterVariants (cvNN) in
    FeatUILabelNameID; both resolve through SCP's own 'name' table."""
    if feature_params is None:
        return None
    nid = getattr(feature_params, "UINameID", None)
    if nid is None:
        nid = getattr(feature_params, "FeatUILabelNameID", None)
    if not nid:
        return None
    return scp["name"].getDebugName(nid)


def import_scp_variants(base, scp, default_map, marks):
    """Carry SCP's own character variants (dotted/slashed zero bodies,
    one/two-story a, g shapes, salt...) through the graft. Returns
    ({our tag: {our default glyph: our variant glyph}}, {our tag: UI name}).

    A variant of a combining mark (cv11, the Cyrillic breve for U+0306)
    is grafted the way graft_halfwidth() grafts the mark itself — 0
    advance, ink shifted one cell left — and added to `marks`, so it
    positions and rescales like its default; a variant drawn as a
    spacing glyph would make the accent take a cell when selected.

    UI names are only meaningful (and only defined by OpenType) for ssNN /
    cvNN — 'zero' and 'salt' come back with no entry in the names dict."""
    gsub = scp["GSUB"].table
    ctx = append_context(base)
    td, _, fd_index, private, vdon = ctx
    scp_gs = scp.getGlyphSet()

    imported = {}   # (scp variant glyph, is_mark) -> our glyph name
    tag_maps = {}
    tag_names = {}
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag in GROUP_NAMES:   # Gengou Code's own ss01-ss08 / cv99
            continue
        tag = _remap_scp_tag(fr.FeatureTag)
        if tag is None:
            continue
        if tag not in tag_names and (tag.startswith("ss")
                                     or tag.startswith("cv")):
            name = _scp_ui_name(scp, fr.Feature.FeatureParams)
            if name:
                tag_names[tag] = name
        for li in fr.Feature.LookupListIndex:
            kind, subtables = _unwrap(gsub.LookupList.Lookup[li])
            for src, dst in _subst_pairs(kind, subtables, fr.FeatureTag):
                if src not in default_map:
                    continue
                is_mark = default_map[src] in marks
                # another import may already have drawn this one —
                # cv11's breve is also a locl form — and grafting it
                # again left the copy the feature selects with none of
                # the donor's anchors, 229 units low under every
                # ascender
                already = default_map.get(dst)
                if already is not None and (already in marks) == is_mark:
                    imported.setdefault((dst, is_mark), already)
                if (dst, is_mark) not in imported:
                    # the DEFAULT's advance, not the variant's: a
                    # variant must not be a different width from the
                    # glyph it replaces mid-run
                    width, dx = ((0, -CELL) if is_mark
                                 else (scp["hmtx"][src][0], 0))
                    name = graft_outline(base, ctx, [(scp_gs, dst, (1, 0, 0, 1, dx, 0))], width)
                    imported[dst, is_mark] = name
                    if is_mark:
                        marks.add(name)
                    # the variant is a donor glyph of ours now, so a
                    # later import can name it: SCP's ccmp composes the
                    # ogonek onto cv04's serifed i, and without this the
                    # rule has no glyph to fire on. Spacing first, as in
                    # graft_halfwidth — the accent keeps its default
                    if not is_mark or dst not in default_map:
                        default_map[dst] = name
                tag_maps.setdefault(tag, {})[default_map[src]] = imported[dst, is_mark]
    return tag_maps, tag_names


def _ccmp_lookups(gsub):
    """(every lookup index SCP's 'ccmp' needs, the ones the feature
    itself names). A chain context substitutes nothing itself, it names
    the lookup that does, so the callees have to be copied too — and a
    shaper applies lookups in LookupList order, so that order is what
    has to survive the copy. But only the first list is copied: a callee
    listed in the feature as well would run with its context thrown
    away, which is the difference between 'i' before a combining mark
    and 'i' anywhere at all."""
    order = set()
    own = set()

    def add(i):
        if i in order:
            return
        order.add(i)
        kind, subtables = _unwrap(gsub.LookupList.Lookup[i])
        if kind == 6:
            for st in subtables:
                for rec in getattr(st, "SubstLookupRecord", None) or ():
                    add(rec.LookupListIndex)

    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag == "ccmp":
            for li in fr.Feature.LookupListIndex:
                own.add(li)
                add(li)
    return sorted(order), own


def _ccmp_remap(lookup, gmap, shift, gid):
    """Rewrite one deep-copied SCP lookup in our glyph names: every
    mapping, ligature and coverage through `gmap`, every nested lookup
    index through `shift`. A rule naming a glyph we did not graft is
    dropped, and a subtable that loses a whole coverage with it; returns
    False when nothing is left of the lookup.

    A coverage keeps SCP's glyph order until `gid` (our glyph ids) puts
    it back in ours — the order a coverage table is searched in, and the
    one thing about it that is not a set."""
    if lookup.LookupFlag & 0x0010:   # UseMarkFilteringSet: SCP's own GDEF
        raise ValueError("ccmp: a mark filtering set cannot be carried over")
    kind, subtables = _unwrap(lookup)
    keep = []
    for entry, st in zip(lookup.SubTable, subtables):
        if kind == 1:
            st.mapping = {gmap[s]: gmap[d] for s, d in st.mapping.items()
                          if s in gmap and d in gmap}
            alive = bool(st.mapping)
        elif kind == 2:
            st.mapping = {gmap[s]: [gmap[d] for d in seq]
                          for s, seq in st.mapping.items()
                          if s in gmap and all(d in gmap for d in seq)}
            alive = bool(st.mapping)
        elif kind == 3:
            alts = {gmap[s]: [gmap[d] for d in a if d in gmap]
                    for s, a in st.alternates.items() if s in gmap}
            st.alternates = {s: a for s, a in alts.items() if a}
            alive = bool(st.alternates)
        elif kind == 4:
            ligs = {}
            for src, rules in st.ligatures.items():
                if src not in gmap:
                    continue
                kept = []
                for lig in rules:
                    if (lig.LigGlyph in gmap
                            and all(c in gmap for c in lig.Component)):
                        lig.Component = [gmap[c] for c in lig.Component]
                        lig.LigGlyph = gmap[lig.LigGlyph]
                        kept.append(lig)
                if kept:
                    ligs[gmap[src]] = kept
            st.ligatures = ligs
            alive = bool(ligs)
        elif kind == 6:
            # coverage-based contexts only: a class- or glyph-based one
            # (Format 1, 2) has no coverage lists to remap and would
            # fall out below as dead, silently
            if getattr(st, "Format", 3) != 3:
                raise ValueError(f"ccmp: chain context Format {st.Format}; "
                                 f"only Format 3 is carried")
            # the glyph counts are the coverage lists' own lengths, so
            # only a coverage that empties changes the subtable's shape
            # — and an empty one would match everywhere
            alive = True
            for attr in ("BacktrackCoverage", "InputCoverage",
                         "LookAheadCoverage"):
                for cov in getattr(st, attr, None) or ():
                    cov.glyphs = sorted((gmap[g] for g in cov.glyphs
                                         if g in gmap), key=gid)
                    alive = alive and bool(cov.glyphs)
            recs = [rec for rec in getattr(st, "SubstLookupRecord", None) or ()
                    if rec.LookupListIndex in shift]
            for rec in recs:
                rec.LookupListIndex = shift[rec.LookupListIndex]
            st.SubstLookupRecord = recs
            st.SubstCount = len(recs)
            alive = alive and bool(recs)
        else:
            raise ValueError(f"ccmp: unsupported GSUB LookupType {kind}")
        if alive:
            keep.append(entry)
    lookup.SubTable = keep
    lookup.SubTableCount = len(keep)
    return bool(keep)


def graft_scp_outputs(base, scp, default_map, marks, order):
    """Give the face the glyphs the donor's lookups `order` draw that
    the graft had no reason to. Each is grafted the way graft_halfwidth
    grafts the glyph it comes from — a mark (its source is one) at 0
    advance with the ink a cell left, anything else at SCP's own
    advance — and named in `default_map`, so a later import can wire a
    rule that mentions it. A glyph already there is skipped, so the
    pass can run again once another import has unlocked more sources.
    Returns the number grafted."""
    gsub = scp["GSUB"].table
    ctx = append_context(base)
    td, _, fd_index, private, vdon = ctx
    scp_gs = scp.getGlyphSet()
    grafted = 0

    def graft(src, is_mark):
        nonlocal grafted
        if src in default_map:
            return
        width, dx = (0, -CELL) if is_mark else (scp["hmtx"][src][0], 0)
        name = graft_outline(base, ctx, [(scp_gs, src, (1, 0, 0, 1, dx, 0))], width)
        default_map[src] = name
        grafted += 1
        if is_mark:
            marks.add(name)

    # in the donor's own lookup order, so a composed mark is grafted
    # before the lookup that restyles it needs to know it is a mark. A
    # substitution's output is a mark when its input is one (a
    # decomposition's first output is the base, the rest are the
    # accents it carries)
    for i in order:
        kind, subtables = _unwrap(gsub.LookupList.Lookup[i])
        for st in subtables:
            if kind == 1:
                pairs = list(st.mapping.items())
            elif kind == 3:
                pairs = [(s, a[0]) for s, a in st.alternates.items() if a]
            elif kind == 2:
                for src, seq in st.mapping.items():
                    if src not in default_map:
                        continue
                    for k, dst in enumerate(seq):
                        graft(dst, k > 0 or default_map[src] in marks)
                continue
            elif kind == 4:
                for src, rules in st.ligatures.items():
                    if src not in default_map:
                        continue
                    for lig in rules:
                        graft(lig.LigGlyph, default_map[src] in marks)
                continue
            else:
                continue        # a chain context draws nothing itself
            for src, dst in pairs:
                if src in default_map:
                    graft(dst, default_map[src] in marks)
    return grafted


def _locl_lookups(gsub):
    """(every lookup index the donor's 'locl' uses, {(script tag,
    language tag or None): the indices THAT one gets}).

    Unlike ccmp, locl is not a feature to turn on everywhere, and not
    even one set of lookups everywhere it is on: Source Code Pro gives
    script grek the Greek accents, script cyrl one set by default and
    another under Serbian, and Northern Sami and Skolt Sami a third
    under their own language tags. Registering the union put the Greek tonos
    in a Cyrillic run, where it stopped ї + U+0301 composing."""
    order, where = set(), {}
    locl = {i for i, fr in enumerate(gsub.FeatureList.FeatureRecord)
            if fr.FeatureTag == "locl"}
    for record in gsub.ScriptList.ScriptRecord:
        for lang, langsys in ([(None, record.Script.DefaultLangSys)]
                              + [(r.LangSysTag, r.LangSys)
                                 for r in record.Script.LangSysRecord]):
            if langsys is None:
                continue
            mine = locl.intersection(langsys.FeatureIndex)
            if not mine:
                continue
            theirs = where.setdefault((record.ScriptTag, lang), set())
            for i in mine:
                theirs.update(gsub.FeatureList.FeatureRecord[i]
                              .Feature.LookupListIndex)
            order.update(theirs)
    return sorted(order), where


def import_scp_locl(base, scp, default_map, where_ours):
    """Carry the donor's 'locl' — the Greek shapes of the accents, and
    the Serbian and Sami letterforms — for the scripts and languages it
    names, not for the whole font. Returns the number of lookups
    copied.

    Without it a Greek run gets the Latin accent: Β + U+0301 drew the
    cap acute, 188 units wide and 138 units high, where the donor draws
    the tonos at 132 wide. Worse, SCP's own ccmp composes the breathing
    marks from the locl OUTPUTS, so ρ + U+0313 + U+0301 never composed
    and the psili was drawn inside the acute — 192 Greek sequences."""
    if "GSUB" not in scp:
        return 0
    gsub = scp["GSUB"].table
    order, where = _locl_lookups(gsub)
    ours = base["GSUB"].table
    if not order:
        return 0
    gmap = dict(default_map)
    # in front, like ccmp: a locl form is what the rest of the features
    # then work on, and SCP's own ccmp composes from these outputs
    shift = copy_lookups(gsub, ours, order,
                         lambda lookup, sh: _ccmp_remap(lookup, gmap, sh, base.getGlyphID),
                         front=True)
    if not shift:
        return 0
    # every pair the donor names, not only those the base already has
    # a LangSys for: _add_feature_where makes the missing ones
    _add_feature_where(ours, "locl",
                       {pair: sorted(shift[old] for old in theirs
                                     if old in shift)
                        for pair, theirs in where.items()
                        if pair[0] in {s for s, _ in where_ours}})
    sort_feature_list(ours)
    return len(shift)


def _new_langsys(record, lang):
    """A LangSys for `lang` under `record`'s script, starting from the
    script's default. The donor gives some languages their own forms
    and the base font has no record for them — Source Han Sans JP has
    no Serbian and no Northern Sami — so the Serbian б and the Sami eng
    were copied in and left unreachable."""
    made = otTables.LangSys()
    made.LookupOrder = None
    made.ReqFeatureIndex = 0xFFFF
    made.FeatureIndex = []
    default = record.Script.DefaultLangSys
    if default is not None:
        made.ReqFeatureIndex = default.ReqFeatureIndex
        made.FeatureIndex = list(default.FeatureIndex)
    made.FeatureCount = len(made.FeatureIndex)
    entry = otTables.LangSysRecord()
    entry.LangSysTag = lang
    entry.LangSys = made
    record.Script.LangSysRecord.append(entry)
    record.Script.LangSysRecord.sort(key=lambda r: r.LangSysTag)
    record.Script.LangSysCount = len(record.Script.LangSysRecord)
    return made


def _add_feature_where(table, tag, where):
    """Make each (script, language) pair in `where` reach the lookups
    IT is given — `_add_feature` puts one set on every LangSys, which
    is right for ccmp and wrong for a feature whose whole point is that
    it differs by language. A language the font has no LangSys for gets
    one, built from the script's default.

    Nothing already in the table is edited: one FeatureRecord per
    distinct lookup list is added and swapped into the LangSys that
    wants it. Source Han Sans shares one 'locl' record between a
    script's default and its languages, so merging into it put the
    Serbian б in every Cyrillic run.

    A language the base has a LangSys for and `where` does not name
    gets the script's default list, as a shaper would give a language
    the donor has no record of: a LangSys is complete, nothing
    cascades to it, and Source Han Sans keeps a Japanese LangSys under
    every script it has -- so a shaper told the text is Japanese, as an
    editor in a ja locale does, read grek/JAN and set the Latin acute
    on β where every other language got the tonos."""
    records = table.FeatureList.FeatureRecord
    existing = {i for i, fr in enumerate(records) if fr.FeatureTag == tag}
    made = {}
    for record in table.ScriptList.ScriptRecord:
        asked = {lang for script, lang in where if script == record.ScriptTag}
        have = {r.LangSysTag for r in record.Script.LangSysRecord} | {None}
        for lang in sorted(asked - have, key=str):
            _new_langsys(record, lang)
        for lang, langsys in ([(None, record.Script.DefaultLangSys)]
                              + [(r.LangSysTag, r.LangSys)
                                 for r in record.Script.LangSysRecord]):
            wanted = where.get((record.ScriptTag, lang),
                               where.get((record.ScriptTag, None)))
            if langsys is None or not wanted:
                continue
            mine = sorted(existing.intersection(langsys.FeatureIndex))
            keep = list(wanted)
            for i in mine:
                keep += [li for li in records[i].Feature.LookupListIndex
                         if li not in keep]
            key = tuple(sorted(keep))
            if key not in made:
                fr = otTables.FeatureRecord()
                fr.FeatureTag = tag
                fr.Feature = otTables.Feature()
                fr.Feature.FeatureParams = None
                fr.Feature.LookupListIndex = list(key)
                fr.Feature.LookupCount = len(key)
                records.append(fr)
                made[key] = len(records) - 1
            langsys.FeatureIndex = sorted(
                [i for i in langsys.FeatureIndex if i not in existing]
                + [made[key]])
            langsys.FeatureCount = len(langsys.FeatureIndex)
    table.FeatureList.FeatureCount = len(records)
    # the base's own records the swap left no LangSys pointing at
    prune_orphan_features(table)


def prune_orphan_features(table):
    """Drop every FeatureRecord no LangSys names (by index or as its
    required feature) and remap the rest. Returns the count dropped.

    _add_feature_where swaps a new record into a LangSys without
    editing the old one, which is then unreachable; and
    prune_orphan_lookups roots reachability at the LangSys, so a lookup
    only an orphan record names goes with it."""
    records = table.FeatureList.FeatureRecord
    used = set()
    for ls in _langsys_list(table):
        used.update(ls.FeatureIndex)
        req = getattr(ls, "ReqFeatureIndex", NO_REQUIRED_FEATURE)
        if req != NO_REQUIRED_FEATURE:
            used.add(req)
    keep = [i for i in range(len(records)) if i in used]
    if len(keep) == len(records):
        return 0
    remap = {old: new for new, old in enumerate(keep)}
    table.FeatureList.FeatureRecord = [records[i] for i in keep]
    table.FeatureList.FeatureCount = len(keep)
    for ls in _langsys_list(table):
        ls.FeatureIndex = sorted(remap[i] for i in ls.FeatureIndex if i in remap)
        ls.FeatureCount = len(ls.FeatureIndex)
        remap_required(ls, remap)
    return len(records) - len(keep)


def scripts_with_langsys(table):
    """{(script tag, language tag or None)} the font has a LangSys for."""
    out = set()
    for record in table.ScriptList.ScriptRecord:
        if record.Script.DefaultLangSys is not None:
            out.add((record.ScriptTag, None))
        for r in record.Script.LangSysRecord:
            out.add((record.ScriptTag, r.LangSysTag))
    return out


def graft_scp_ccmp(base, scp, default_map, marks):
    """Give the face the glyphs SCP's 'ccmp' draws that the graft had
    no reason to: the composed marks (circumflex and acute as one), the
    dotted-i forms, the accents' flattened shapes for stacking.

    Called twice, because the two imports need each other: the variant
    features have rules on what ccmp composes (cv02's single-storey g̃)
    and ccmp has rules on what the variants draw (the ogonek under
    cv04's serifed i). Returns the number grafted."""
    if "GSUB" not in scp:
        return 0
    order, _ = _ccmp_lookups(scp["GSUB"].table)
    if not order:
        return 0
    return graft_scp_outputs(base, scp, default_map, marks, order)


def copy_lookups(donor, ours, indices, remap, front, warn=None):
    """Copy the donor table's lookups `indices` into `ours`, at the front
    of its LookupList (`front`) or the end. Returns {donor index: ours}.

    `remap(lookup, shift)` rewrites one deep-copied lookup in place --
    its glyph names to ours, its nested lookup indices through `shift`
    -- and says whether anything of it is left. Which lookups survive
    is settled first: a rule can name a glyph this face does not have
    (the italic donor has no Greek), and a chain context whose only
    callee went with it is dead too, so the live set has to settle
    before the indices are handed out. `warn` names the feature in a
    line per lookup dropped, for an import that expects none.

    The one shape the three importers (locl, ccmp, the marks) had each
    spelled out for themselves."""
    live = list(indices)
    while True:
        seen = {old: k for k, old in enumerate(live)}
        kept = [old for old in live
                if remap(copy.deepcopy(donor.LookupList.Lookup[old]), seen)]
        if kept == live:
            break
        if warn:
            for old in live:
                if old not in kept:
                    print(f"  warning: {warn} lookup {old} has no rule this "
                          f"face can use, dropped")
        live = kept
    if not live:
        return {}
    first = 0 if front else len(ours.LookupList.Lookup)
    shift = {old: first + k for k, old in enumerate(live)}
    copied = []
    for old in live:
        lookup = copy.deepcopy(donor.LookupList.Lookup[old])
        remap(lookup, shift)
        copied.append(lookup)
    if front:
        _insert_lookups_first(ours, copied)
    else:
        ours.LookupList.Lookup.extend(copied)
        ours.LookupList.LookupCount = len(ours.LookupList.Lookup)
    return shift


def _insert_lookups_first(table, lookups):
    """Put `lookups` at the front of the LookupList, renumbering every
    reference to the ones already there. A shaper applies a stage's
    lookups in LookupList order whatever order the features name them,
    so a lookup appended at the end runs last — which for ccmp means
    after the variant features and after the ligatures, and cv04's
    serifed i then reached the combining mark with its dot still on."""
    by = len(lookups)
    if not by:
        return
    if getattr(table, "FeatureVariations", None) is not None:
        raise ValueError("FeatureVariations name lookups this does not renumber")
    for lookup in table.LookupList.Lookup:
        for rec in _lookup_records(lookup):
            rec.LookupListIndex += by
    for fr in table.FeatureList.FeatureRecord:
        fr.Feature.LookupListIndex = [i + by for i in fr.Feature.LookupListIndex]
    table.LookupList.Lookup[:0] = list(lookups)
    table.LookupList.LookupCount = len(table.LookupList.Lookup)


def import_scp_ccmp(base, scp, default_map, marks):
    """Carry the Latin donor's 'ccmp' — composition and decomposition —
    across the graft, the way import_scp_variants carries its variant
    features. Returns the number of glyphs grafted for it.

    ccmp is not a variant feature nobody asks for: it is on by default
    in every shaper, and without it the grafted Latin keeps Source Han
    Sans's ccmp alone, which knows nothing about Source Code Pro's
    glyphs. What that costs is visible in one line of a terminal: 'i'
    followed by U+0307 kept its own dot and drew a second one 84 units
    away — a smeared double dot where the donor substitutes the dotless
    ı and sets the accent over it. 'j' under any of ten accents, ĩ/g̃,
    the Vietnamese ê̆ ô̆, and Ї́ ї́ went the same way: 20 sequences the
    Latin-only faces composed and the JP faces did not.

    The feature's glyphs are SCP's own and mostly unencoded — the
    composed marks (circumflex + acute as one), the dotted-i forms, the
    accents' flattened shapes for stacking — so each one is grafted the
    way graft_halfwidth grafts the glyph it comes from: a mark (its
    source is one) at 0 advance with the ink a cell left, anything else
    at SCP's own advance. The lookups are then copied with every glyph
    name and every nested lookup index rewritten, appended to our
    LookupList in SCP's own order, and added to every 'ccmp' feature
    record — Source Han Sans has one per script, and the Latin, Greek
    and Cyrillic this touches are three of them."""
    gsub = scp["GSUB"].table
    order, own = _ccmp_lookups(gsub)
    ours = base["GSUB"].table
    records = [fr for fr in ours.FeatureList.FeatureRecord
               if fr.FeatureTag == "ccmp"]
    if not order or not records:
        return 0
    # the rules whose source is itself a variant (SCP composes the
    # ogonek onto cv04's serifed i) could not be grafted before
    # import_scp_variants made that glyph
    grafted = graft_scp_ccmp(base, scp, default_map, marks)
    gmap = dict(default_map)
    # at the FRONT of the list, where ccmp belongs: a shaper runs a
    # stage's lookups in LookupList order, so appended ones ran after
    # the variant features and the ligatures, and cv04's serifed i met
    # a combining mark with its dot still on — the very defect the
    # import exists to fix, on the variant path. Nothing is expected to
    # drop today, and a drop says so
    shift = copy_lookups(gsub, ours, order,
                         lambda lookup, sh: _ccmp_remap(lookup, gmap, sh, base.getGlyphID),
                         front=True, warn="ccmp")
    # the feature names what the donor's feature named, not the closure
    listed = sorted(shift[old] for old in shift if old in own)
    for fr in records:
        fr.Feature.LookupListIndex.extend(listed)
        fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
    return grafted


# (coverage, array, record list) per GPOS mark lookup type: the coverage
# and the array are parallel, so a glyph and its anchors move together
_MARK_ARRAYS = {
    4: (("MarkCoverage", "MarkArray", "MarkRecord"),
        ("BaseCoverage", "BaseArray", "BaseRecord")),
    5: (("MarkCoverage", "MarkArray", "MarkRecord"),
        ("LigatureCoverage", "LigatureArray", "LigatureAttach")),
    6: (("Mark1Coverage", "Mark1Array", "MarkRecord"),
        ("Mark2Coverage", "Mark2Array", "Mark2Record")),
}


def _remap_mark_subtable(sub, kind, gmap, gid):
    """Rewrite one mark-attachment subtable in our glyph names. A
    coverage here is not a set: its order is the order of the array
    beside it, so the glyph and its anchors are sorted together.
    Returns False when a coverage comes over empty."""
    for cov_attr, arr_attr, rec_attr in _MARK_ARRAYS[kind]:
        cov = getattr(sub, cov_attr, None)
        array = getattr(sub, arr_attr, None)
        records = getattr(array, rec_attr, None) if array else None
        if cov is None or records is None:
            return False
        kept = sorted(((gmap[g], rec) for g, rec in zip(cov.glyphs, records)
                       if g in gmap), key=lambda pair: gid(pair[0]))
        if not kept:
            return False
        cov.glyphs = [g for g, _ in kept]
        setattr(array, rec_attr, [rec for _, rec in kept])
        for count in (f"{rec_attr}Count", f"{cov_attr[:-8]}Count"):
            if hasattr(array, count):
                setattr(array, count, len(kept))
    return True


def _remap_single_pos(sub, gmap, gid, marks):
    """Rewrite a SinglePos subtable in our glyph names, keeping the
    placement it carries and dropping the advance.

    The donor pays for its spacing marks in GPOS: one subtable takes a
    cell off every mark's advance, and a second also pulls the two
    double-span marks — the tie bar U+0361 and the double macron U+035F
    — half a cell left, because they straddle the pair they join. Our
    marks are 0 wide already, so the advance is ours to drop; the
    placement is not, and dropping it with the rest left the tie
    centred on the first letter, 193 units left of the line's start and
    through the descenders U+035F is drawn to clear. Their outlines are
    already a CELL left of the donor's, so the placement it asks for is
    a CELL further right than the donor's. Returns False when nothing
    is left to say."""
    cov = getattr(sub, "Coverage", None)
    if cov is None:
        return False
    keep = [g for g in cov.glyphs if g in gmap]
    if not keep or not all(gmap[g] in marks for g in keep):
        return False        # a placement on a base is not ours to move
    sub.ValueFormat &= 0x3          # placements only, no advances
    if not sub.ValueFormat:
        return False

    def carry(value):
        for attr in ("XAdvance", "YAdvance"):
            if hasattr(value, attr):
                delattr(value, attr)
        # only a record whose format carries an x placement: one that
        # sets y alone leaves the mark where the graft drew it, a cell
        # left with no advance, which is where it belongs
        if sub.ValueFormat & 0x1:
            value.XPlacement = getattr(value, "XPlacement", 0) + CELL

    if sub.Format == 2:
        pairs = sorted(((gmap[g], v) for g, v in zip(cov.glyphs, sub.Value)
                        if g in gmap), key=lambda pair: gid(pair[0]))
        for _, value in pairs:
            carry(value)
        cov.glyphs = [g for g, _ in pairs]
        sub.Value = [v for _, v in pairs]
        sub.ValueCount = len(pairs)
    else:
        # one ValueRecord for the whole coverage: adjusted once
        carry(sub.Value)
        cov.glyphs = sorted((gmap[g] for g in keep), key=gid)
    return True


def _remap_chain_pos(sub, gmap, gid, shift):
    """Rewrite a ChainContextPos subtable: coverages and class
    definitions in our glyph names, the lookups it calls at their new
    indices. A context whose callees all went is dead, and so is one
    that loses a whole coverage — an empty one matches everywhere."""

    def renumber(records):
        recs = [rec for rec in records or () if rec.LookupListIndex in shift]
        for rec in recs:
            rec.LookupListIndex = shift[rec.LookupListIndex]
        return recs

    if sub.Format == 2:
        # class-based: the rule sets are indexed BY class, so nothing
        # here may be reordered — only the glyph keys change
        cov = getattr(sub, "Coverage", None)
        if cov is None:
            return False
        cov.glyphs = sorted((gmap[g] for g in cov.glyphs if g in gmap), key=gid)
        if not cov.glyphs:
            return False
        for attr in ("BacktrackClassDef", "InputClassDef", "LookAheadClassDef"):
            classes = getattr(sub, attr, None)
            if classes is not None:
                classes.classDefs = {gmap[g]: c
                                     for g, c in classes.classDefs.items()
                                     if g in gmap}
        alive = False
        for rules in getattr(sub, "ChainPosClassSet", None) or ():
            for rule in getattr(rules, "ChainPosClassRule", None) or ():
                rule.PosLookupRecord = renumber(rule.PosLookupRecord)
                rule.PosCount = len(rule.PosLookupRecord)
                alive = alive or bool(rule.PosLookupRecord)
        return alive
    if sub.Format != 3:
        print(f"  warning: mark import: ChainContextPos format {sub.Format}, "
              f"skipped")
        return False
    for attr in ("BacktrackCoverage", "InputCoverage", "LookAheadCoverage"):
        for cov in getattr(sub, attr, None) or ():
            cov.glyphs = sorted((gmap[g] for g in cov.glyphs if g in gmap),
                                key=gid)
            if not cov.glyphs:
                return False
    sub.PosLookupRecord = renumber(getattr(sub, "PosLookupRecord", None))
    sub.PosCount = len(sub.PosLookupRecord)
    return bool(sub.PosLookupRecord)


def import_scp_marks(base, scp, default_map, marks):
    """Carry the Latin donor's mark positioning across the graft, so an
    accent sits on the letter it belongs to. Returns the number of
    lookups copied.

    Source Code Pro draws its combining marks as spacing glyphs and
    places them entirely in GPOS: 'mark' attaches one to the base's own
    top anchor, which is higher on an ascender than on an x-height
    letter, 'mkmk' stacks a second on the first, and 'ccmp' lifts the
    tie bar over an ascender and drops the double macron under a
    descender. graft_halfwidth keeps the outline and gives it a 0
    advance one cell left, which lands it correctly over an x, o or a —
    and 229 units too low on b d f h k l, straight through the
    ascender: 58 of 84 ascender-and-accent pairs drew their ink into
    one another where the Latin-only faces drew none.

    Mark attachment is copied with every glyph name rewritten and the
    coverages re-sorted with their anchor arrays (a mark coverage is
    positional, not a set), then every anchor ON a mark is moved the
    same cell left as its outline was, so attachment lands exactly
    where the donor's does. A plain placement moves the other way (it
    is added to the outline, not measured on it), and the advances the
    donor takes off its spacing marks are left behind — ours are 0 wide
    already."""
    if "GPOS" not in scp or "GPOS" not in base:
        return 0
    donor = scp["GPOS"].table
    ours = base["GPOS"].table
    gmap = dict(default_map)
    gid = base.getGlyphID
    wanted = {}
    for fr in donor.FeatureList.FeatureRecord:
        if fr.FeatureTag in ("mark", "mkmk", "ccmp"):
            for li in fr.Feature.LookupListIndex:
                wanted.setdefault(li, set()).add(fr.FeatureTag)
    # a chain context positions nothing itself: it names the lookup that
    # does, which has to come over with it
    for li in list(wanted):
        kind, subtables = _unwrap_pos(donor.LookupList.Lookup[li])
        if kind != 8:
            continue
        for sub in subtables:
            for rec in _lookup_records(sub):
                wanted.setdefault(rec.LookupListIndex, set())

    def remap(lookup, shift):
        # a mark filtering set indexes the donor's MarkGlyphSetsDef,
        # which does not travel: copied, the flag would index a table
        # the base has none of (_ccmp_remap refuses it the same way)
        if lookup.LookupFlag & 0x0010:
            raise ValueError("mark: a donor lookup uses a mark filtering "
                             "set, which is not carried")
        kind, subtables = _unwrap_pos(lookup)
        keep = []
        for entry, sub in zip(lookup.SubTable, subtables):
            if kind in _MARK_ARRAYS:
                alive = _remap_mark_subtable(sub, kind, gmap, gid)
            elif kind == 1:
                alive = _remap_single_pos(sub, gmap, gid, marks)
            elif kind == 8:
                alive = _remap_chain_pos(sub, gmap, gid, shift)
            else:
                alive = False
            if alive:
                keep.append(entry)
        lookup.SubTable = keep
        lookup.SubTableCount = len(keep)
        if keep and kind in _MARK_ARRAYS:
            _, subs = _unwrap_pos(lookup)
            for sub in subs:
                _shift_subtable_anchors(kind, sub, {n: -CELL for n in marks})
        return bool(keep)

    shift = copy_lookups(donor, ours, sorted(wanted), remap, front=False)
    if not shift:
        return 0
    for tag in ("ccmp", "mark", "mkmk"):
        idx = sorted(shift[old] for old in shift if tag in wanted[old])
        if idx:
            _add_feature(ours, tag, idx)
    sort_feature_list(ours)
    # 'mkmk' asks GDEF which marks it may stack on (LookupFlag's mark
    # attachment type); Source Han Sans JP declares no such classes, so
    # the donor's travel with the lookups that read them -- and only
    # because it declares none: a class number the base already used
    # would make its marks stackable by the donor's lookups
    donor_classes = getattr(scp.get("GDEF"), "table", None)
    donor_classes = getattr(donor_classes, "MarkAttachClassDef", None)
    if donor_classes is not None and "GDEF" in base:
        gdef = base["GDEF"].table
        classes = dict(getattr(getattr(gdef, "MarkAttachClassDef", None),
                               "classDefs", None) or {})
        if classes:
            raise ValueError("mark: the base already declares mark "
                             "attachment classes; the donor's would "
                             "share their numbers")
        for name, cls in donor_classes.classDefs.items():
            if name in gmap:
                classes[gmap[name]] = cls
        if gdef.MarkAttachClassDef is None:
            gdef.MarkAttachClassDef = otTables.MarkAttachClassDef()
        gdef.MarkAttachClassDef.classDefs = classes
    return len(shift)


# (usWinAscent, usWinDescent) for every JP face — a clipping bound in
# the GDI paths and their line height. Pinned rather than measured: this
# family's ink reaches 1808 / -1048 and covering it would give a 2856u
# line, more than twice the 1257u every renderer honouring
# USE_TYPO_METRICS uses. See copy_line_metrics for where each number
# comes from, and verify.WIN_METRICS, which holds the built faces to it.
WIN_METRICS = (1160, 454)


def copy_line_metrics(base, latin):
    """The line pitch of an English terminal font: hhea and typo ascender
    / descender / line gap from the Latin donor (Source Code Pro's 984 /
    -273 / 0, hhea and typo alike, USE_TYPO_METRICS set), so a line of
    Gengou Code JP is as tall as a line of Source Code Pro, not of Source
    Han Sans (1160 / -288, 15% more). Source Han Sans's own kanji body
    (880 / -120) sits inside.

    usWinAscent / Descent are pinned to WIN_METRICS. They are a clipping
    bound as much as a line height, and Source Han Sans's own ink goes
    well past 984 — so bringing them down to the typo metrics would clip
    glyphs in the GDI paths that read them. The cost is that those same
    paths (legacy conhost, Notepad, Office's GDI text) lay out a 1614u
    line where DirectWrite, CoreText and HarfBuzz lay out 1257u;
    USE_TYPO_METRICS tells everything that reads it which to prefer.

    The ascent is Source Han Sans's own 1160. The descent is 454 rather
    than Source Han Sans's 288, because the Latin layer grafted over it
    draws deeper than Source Han Sans does: the box-drawing elements
    reach -400 and the shade blocks -454, and at 288 the GDI paths
    sliced the bottom off 111 codepoints, 101 of them box drawing — a
    terminal font's frames and rules breaking in exactly the renderers
    that read this field. 454 is what the Latin family already declares
    for the same ink (build_latin.LATIN_WIN_METRICS pins 1060 / 454), so
    this is the JP faces catching up to their own Latin layer rather
    than a new policy. Two codepoints stay outside it, the vertical kana
    repeat marks U+3031 and U+3032 at -549; covering them would cost
    another 6% of GDI line height for two characters no terminal sets.
    """
    for tbl, attrs in (
        ("hhea", ("ascent", "descent", "lineGap")),
        ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap")),
    ):
        for a in attrs:
            setattr(base[tbl], a, getattr(latin[tbl], a))
    base["OS/2"].usWinAscent, base["OS/2"].usWinDescent = WIN_METRICS
    base["OS/2"].fsSelection |= 1 << 7   # USE_TYPO_METRICS


# Representative sample chars per ulCodePageRange1 bit: a bit is set when
# every sample character for it is in the final cmap. Only these bits are
# touched by recalc_codepage_range() — everything else in the field (Mac
# charset, OEM/DOS, codepages we don't sample for...) stays whatever
# the base font declared.
CODEPAGE_SAMPLES = {
    0: "éàü",    # 1252 Latin 1
    1: "łőřș",   # 1250 Latin 2
    2: "Жд",     # 1251 Cyrillic
    3: "Ωβ",     # 1253 Greek
    4: "ğşıİ",   # 1254 Turkish
    17: "日あｱ",  # 932 JIS
}


def recalc_codepage_range(font):
    """Set the ulCodePageRange1 bits CODEPAGE_SAMPLES covers from the final
    cmap; leave every other bit as inherited from the base font."""
    cmap = font.getBestCmap()
    os2 = font["OS/2"]
    bits = os2.ulCodePageRange1
    for bit, sample in CODEPAGE_SAMPLES.items():
        mask = 1 << bit
        if all(ord(c) in cmap for c in sample):
            bits |= mask
        else:
            bits &= ~mask
    os2.ulCodePageRange1 = bits


# The symbols that pair with a ligature take Monaspace's one-cell glyph
# rather than SCP's (in Gengou Code, build_latin.py), so '←' beside '<-'
# (and ≠ / !=, ≤ / <=, … / ...) shares its stroke weight and arrowhead.
MONA_AMBIGUOUS = "←→↑↓⇐⇒⇔≠≤≥…"


def latin_ligatures(font, latin, latin_path, alts, ligatures):
    """Append the ligature glyphs by copying them out of the Latin donor:
    each sequence is shaped there (HarfBuzz, calt+liga) to find its glyph,
    and again with cv99 for the alternate design. Drawn at CELL per input
    character, as the donor has them. Returns {seq: glyph name};
    alternates land in `alts`."""
    import uharfbuzz as hb
    # 'A' like every other appender: add_latin_fd() later re-homes all
    # appended glyphs into a copy of A's FD, and a charstring's width is
    # encoded relative to its FD's nominalWidthX — encoding it against
    # another FD (the symbol one, as before) left every ligature's CFF
    # width 510u off its hmtx advance
    ctx = append_context(font)
    td, cmap, fd_index, private, vdon = ctx
    lgs = latin.getGlyphSet()
    order = latin.getGlyphOrder()
    hbfont = hb.Font(hb.Face(hb.Blob.from_file_path(str(latin_path))))

    def shaped(text, feats):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(hbfont, buf, feats)
        return [order[i.codepoint] for i in buf.glyph_infos]

    added = {}
    n_alt = 0
    for seq, spec in ligatures.items():
        glyphs = shaped(seq, {"calt": True, "liga": True})
        if len(glyphs) != 1:
            print(f"  skip {seq!r}: the Latin donor shapes it to {len(glyphs)} glyphs")
            continue
        if any(ord(c) not in cmap for c in seq):
            print(f"  skip {seq!r}: component not in target cmap")
            continue
        width = CELL * spec["cells"]
        name = graft_outline(font, ctx, [(lgs, glyphs[0], (1, 0, 0, 1, 0, 0))], width)
        added[seq] = name
        alt = shaped(seq, {"calt": True, "liga": True, "cv99": True})
        if len(alt) == 1 and alt[0] != glyphs[0]:
            alt_name = graft_outline(font, ctx, [(lgs, alt[0], (1, 0, 0, 1, 0, 0))], width)
            alts[name] = alt_name
            n_alt += 1
    print(f"  ligatures from the Latin donor: {len(added)}, cv99 alternates: {n_alt}")
    return added


def donor_credits(latin):
    """(label, copyright, designer) for Source Code Pro and Monaspace,
    parsed back out of the Latin donor's name IDs 0 / 9, which
    build_latin.py composed as "...; Source Code Pro: ...; Monaspace: ..."."""
    import re
    name = latin["name"]
    out = {}
    for nid, sep in ((0, " "), (9, "; ")):
        text = name.getDebugName(nid) or ""
        for label in ("Source Code Pro", "Monaspace"):
            m = re.search(rf"(?:^|{re.escape(sep)}){re.escape(label)}: (.*?)"
                          rf"(?={re.escape(sep)}(?:Source Code Pro|Monaspace): |$)",
                          text, re.S)
            out.setdefault(label, {})[nid] = m.group(1).strip() if m else None
    return [(label, v.get(0), v.get(9)) for label, v in out.items()]


def _rect_path(x0, y0, x1, y1):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return path


def _xform_path(path, matrix):
    out = pathops.Path()
    path.draw(TransformPen(out.getPen(), matrix))
    return out


def grid_step(adv, ink, cell):
    """The grid advance for a proportional glyph: the cell, or a whole
    number of full widths — whichever its own advance is nearest, since
    that is what the donor says the character's width class is. Source
    Han Sans's Greek letters run 285-804 at the Regular donor and
    329-853 at the Bold one, its Cyrillic 454-1005 and 483-1064: most
    of them sit a little over the cell, so rounding up would cost every
    one a whole terminal column, and would make the same letter one
    cell in one weight and two in the next (its advance grows with the
    weight). The widest would land on a full width here, which is why
    both Latin donors draw the whole block and no letter of it is
    Source Han Sans's.

    The ink may overhang the step by up to a third of a cell — an italic
    always overhangs — but no further: a three-em dash (⸻, 2452 wide)
    takes three full widths rather than spilling out of two."""
    if adv <= cell:
        step = cell
    else:
        low = FULLWIDTH * (adv // FULLWIDTH) or cell
        high = FULLWIDTH if low == cell else low + FULLWIDTH
        step = low if adv - low <= high - adv else high
    while ink > step + cell // 3:
        # the cell first, then whole full widths — and always forward,
        # even were the cell ever set at or above a full width
        step = FULLWIDTH if step < FULLWIDTH else step + FULLWIDTH
    return step


_REFERENCE_STEPS = {}


def reference_steps(path, cell, ink_path=None):
    """{glyph name: grid step} decided once, on one weight, for the whole
    family. A glyph's advance grows with the weight — Source Han Sans's
    Φ runs 757..850 across the five donors, straddling the midpoint
    between the cell and a full width — so deciding per face would make
    the same letter one column in Light Italic and two in Bold Italic.
    Keyed by name because every Source Han Sans weight shares its CID
    names, and because a glyph reachable only through a feature has no
    codepoint. A glyph on a whole number of cells gets an entry too — it
    can be on the grid in the reference and off it in a heavier weight,
    and both have to end up the same — but one on a full width does not:
    the nearest step from just off a full width is that full width. The
    reference is
    the donor of our Regular (FACES); `ink_path` is the heaviest donor,
    whose ink is the widest the step has to hold (Source Han Sans's ж
    overhangs a 600 cell by 138u at Normal and 223u at Bold). Read once
    per process."""
    key = (str(path), str(ink_path), cell)
    if key not in _REFERENCE_STEPS:
        for needed in (path, ink_path):
            if needed is not None and not Path(needed).exists():
                raise FileNotFoundError(
                    f"{needed}: a weight every face takes its width decisions from "
                    f"(REFERENCE_SHS / INK_SHS). Even a one-face build needs both in "
                    f"SHS_DIR, so that face's widths match the rest of the family")
        ref = TTFont(path)
        gs, hmtx = ref.getGlyphSet(), ref["hmtx"]
        heavy = TTFont(ink_path) if ink_path is not None else None
        heavy_gs = heavy.getGlyphSet() if heavy is not None else gs
        steps = {}
        for name in ref.getGlyphOrder():
            adv = hmtx[name][0]
            if adv <= 0:
                continue
            if adv % FULLWIDTH == 0:
                # the donor's own full width, and its design. No entry:
                # a heavier weight drawn a few units off it rounds back
                # to the same full width anyway, and 17,000 Japanese
                # glyphs in the map would ride to every pool worker
                continue
            source = heavy_gs if name in heavy_gs else gs
            pen = BoundsPen(source)
            source[name].draw(pen)
            ink = (pen.bounds[2] - pen.bounds[0]) if pen.bounds else 0
            # a whole number of cells is a step we would have picked, so
            # it stands unless the ink says otherwise (none does today)
            steps[name] = (adv if adv % cell == 0 and ink <= adv + cell // 3
                           else grid_step(adv, ink, cell))
        _REFERENCE_STEPS[key] = steps
        ref.close()
        if heavy is not None:
            heavy.close()
    return _REFERENCE_STEPS[key]


def fit_to_grid(font, cell, steps=None):
    """Centre Source Han Sans's proportional leftovers on the grid: every
    glyph whose advance is neither 0 nor a whole number of cells nor of
    full widths — the half-width kana and symbols at 500 (half of the
    1000 em, on neither grid; the Halfwidth block's wider glyphs are
    narrow_halfwidth's, before this), Hangul jamo at 920, ﬀ ﬃ ﬄ, the enclosed
    🄯, and in the italic faces the Greek and Cyrillic Source Code Pro
    Italic has none of — goes to the nearest grid step (grid_step); the
    outline is centred in the new advance. Runs before widen_fullwidth,
    which then takes the full-width ones along.

    Every glyph, not only the cmap'd ones: a feature puts glyphs on the
    page that no codepoint reaches, and 'locl' and 'ccmp' do it without
    being asked (Source Han Sans's locl form of ⋯ is 1052 units wide),
    and so did hwid's 500-advance alternates, before hwid was dropped
    (they are in the font still; aalt reaches most of them).

    A tiling character is stretched into its step instead of centred
    in it (tiling_glyphs; the two that get here are the two-em and
    three-em dashes ⸺ ⸻, which exist to butt together). Source Han
    Sans draws ⸺ 1580 units of ink wide in a 1672 advance, so the step
    rounds it to 2000 — and centred there, a run of them broke every
    420 units where the design leaves 92.

    `steps` (when given) is reference_steps()' {glyph name: step}, so
    every weight of the family agrees on a glyph's width; a name it does
    not have falls back to this face's own advance. Returns the number
    of glyphs moved."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    tiling = tiling_glyphs(font)
    drawn, shifted = {}, {}
    moved = 0
    # a glyph this build made carries a name alloc_glyph_name took from
    # Source Han Sans's own CID space, so it can collide with a reference
    # name that means something else entirely — and `built`, not
    # `appended`, is the whole of them: narrow_halfwidth's condensed
    # copies opt out of the Latin FontDict but are just as much ours.
    # Ours are on the grid by construction and take the fallback path
    built = state_of(font).built
    pinned = state_of(font).pinned_cell
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv <= 0:
            continue
        # the family's answer first: a glyph can land on a step in one
        # weight and off it in the next, and both must end up the same
        # ... and not one pinned to the cell: the reference map still
        # has the donor's own full width for it
        new = (None if name in built or name in pinned
               else (steps or {}).get(name))
        if new is None:
            if adv % cell == 0 or adv % FULLWIDTH == 0:
                continue
            bounds = BoundsPen(gs)
            gs[name].draw(bounds)
            new = grid_step(adv, (bounds.bounds[2] - bounds.bounds[0]) if bounds.bounds else 0,
                            cell)
        if new == adv:
            continue
        shift = (new - adv) // 2
        private = glyph_private(font, td, name)
        pen = T2CharStringPen(pen_width(private, new), gs)
        stretch = tiling.get(name) == "stretch"
        gs[name].draw(TransformPen(
            pen, (new / adv, 0, 0, 1, 0, 0) if stretch
            else (1, 0, 0, 1, shift, 0)))
        cs = drawn[name] = pen.getCharString(private=private)
        # a stretched outline's bearing is its own new xMin, and it did
        # not move by `shift`, so no anchor on it did either
        if stretch:
            hmtx.metrics[name] = (new, charstring_lsb(cs))
        else:
            hmtx.metrics[name] = (new, lsb + shift)
            shifted[name] = shift
        note_redrawn(font, [name])
        moved += 1
    # swap after drawing everything: the glyph set draws through the same
    # CharStrings, so replacing one mid-pass could feed a shifted glyph
    # to a later one that references it (widen_fullwidth defers too)
    for name, cs in drawn.items():
        td.CharStrings[name] = cs
    shift_anchors(font, shifted)
    return moved


_STACK_CLEARING = {"hstem", "vstem", "hstemhm", "vstemhm", "hintmask", "cntrmask",
                   "rmoveto", "hmoveto", "vmoveto", "endchar"}


def shift_charstring(cs, dx, width, private):
    """Move a (desubroutinized) Type 2 charstring `dx` to the right and
    give it advance `width`, keeping its hints: only the first vstem
    coordinate (explicit `vstem`/`vstemhm`, or the implicit one in front
    of a `hintmask`/`cntrmask`) and the first moveto move, everything
    after is relative. The width operand is rewritten against this FD's
    nominalWidthX (omitted at defaultWidthX, as the spec has it). Returns
    False, leaving the charstring alone, for a program it does not
    understand (a seac-style endchar) — the caller redraws that one."""
    cs.decompile()
    prog = list(cs.program)
    ops = [i for i, t in enumerate(prog) if isinstance(t, str)]
    if not ops:
        return False
    first_op = prog[ops[0]]
    if first_op not in _STACK_CLEARING or first_op == "endchar" and ops[0] > 1:
        return False
    # the width rides as an odd extra argument on the first stack-clearing
    # operator; strip it, then prepend ours
    nargs = ops[0]
    even_ops = {"hstem", "vstem", "hstemhm", "vstemhm", "hintmask", "cntrmask", "rmoveto"}
    has_width = (nargs % 2 == 1) if first_op in even_ops else (
        nargs == 2 if first_op in ("hmoveto", "vmoveto") else nargs == 1)
    if has_width:
        del prog[0]
    i = 0
    if width != private.defaultWidthX:
        prog.insert(0, width - private.nominalWidthX)
        i = 1                              # the walk below skips our width
    # walk the hints and the first moveto
    args = []
    vstem_done = False
    while i < len(prog):
        t = prog[i]
        if not isinstance(t, (str, bytes)):
            args.append(i)
            i += 1
            continue
        if isinstance(t, bytes):          # hintmask data
            i += 1
            continue
        if t in ("vstem", "vstemhm") or (t in ("hintmask", "cntrmask") and args and not vstem_done):
            if args:
                prog[args[0]] += dx
            vstem_done = True
        elif t == "rmoveto":
            prog[args[-2]] += dx
            break
        elif t == "hmoveto":
            prog[args[-1]] += dx
            break
        elif t == "vmoveto":
            prog[args[-1]:args[-1] + 2] = [dx, prog[args[-1]], "rmoveto"]
            break
        elif t not in ("hstem", "hstemhm", "hintmask", "cntrmask"):
            break                          # endchar or a path op: done
        args = []
        i += 1
    cs.program = prog
    cs.bytecode = None
    return True


def _slab(path, a, b):
    """The part of `path` between x = a and x = b."""
    big = 1e5
    return pathops.op(path, _rect_path(a, -big, b, big), pathops.PathOp.INTERSECTION)


def edge_is_rule(path, side):
    """Whether the ink at one edge of `path` is a horizontal rule: the
    2-unit slab at the edge is the same SHAPE as the slab 10 units in,
    slid onto it. True of a rule, a tee, a cross, a block; false of a
    diagonal (╱), a wave (〰), a shaded pattern (▒) or a triangle (◢),
    whose cross-section changes as it goes in. Compared by exclusive-or
    area rather than by extents: ╳'s two diagonals and ▓'s dot columns
    keep the same extents and piece count 10 units in, and only the
    overlay tells them from a rule."""
    x0, _, x1, _ = path.bounds
    if side == "left":
        edge, inner, back = _slab(path, x0, x0 + 2), _slab(path, x0 + 10, x0 + 12), -10
    else:
        edge, inner, back = _slab(path, x1 - 2, x1), _slab(path, x1 - 12, x1 - 10), 10
    if edge.bounds is None:
        return False
    moved = _xform_path(inner, (1, 0, 0, 1, back, 0))
    diff = pathops.op(edge, moved, pathops.PathOp.XOR)
    # a rule overlays itself exactly; the tolerance is for float edges
    # and for a leg that is already bending — the rounded corners ╭ ╮ ╯
    # ╰ measure 0.0059 at the straight end of the arc, identically in
    # every weight, and 0.005 read them as curves and left them out of
    # the tiling. It stays under everything the box drawing has to
    # reject: a diagonal ╱ ╲ ╳ is 0.34, and of the shapes decided by
    # codepoint elsewhere a triangle's flat side is 0.0100 and the
    # flattest wave 0.0083 (Heavy's 〰)
    return abs(diff.area) <= 0.007 * abs(edge.area)


def extend_edges(path, gap, left=True, right=True):
    """Lengthen an outline by `gap` units at the side(s) named, by
    extruding the 2-unit cross-section it has THERE. Not at its
    midpoint, which is where stretch_path cuts and where a box-drawing
    cross has its vertical stem: scaling that slab would smear the stem
    into a bar. At the edge a rule, a cross and a tee all present the
    same thing — the horizontal arm — so all three come out longer and
    no stroke changes weight. A corner or a side tee reaches one
    neighbour only, and is lengthened on that side only, so its stem
    stays where the centring put it: on the cell's centre line."""
    x0, y0, x1, y1 = path.bounds

    def edge(a, b, anchor, width):
        scale = width / (b - a)
        return _xform_path(_slab(path, a, b), (scale, 0, 0, 1, anchor * (1 - scale), 0))

    out = path
    if left:
        out = pathops.op(out, edge(x0, x0 + 2, x0 + 2, gap + 2), pathops.PathOp.UNION)
    if right:
        out = pathops.op(out, edge(x1 - 2, x1, x1 - 2, gap + 2), pathops.PathOp.UNION)
    out.simplify()
    return out


# The characters drawn to tile with a neighbour, by block, and how the
# Term family lengthens them from 1000 to 1200. Anything else that
# happens to touch its own advance (Ⅷ, ㌄, 孰 in Bold, a bracket) is an
# ordinary glyph and is centred like the rest: an edge test alone
# stretched those 20% wide.
#   stretch — the whole outline, by 1200/1000: block elements and
#   shades (▏ is an eighth of the cell and must stay one; ▓'s dots must
#   stay a pattern), the quadrant triangles, the wave and dashed lines,
#   the full-width low line and overline
#   rule — the box-drawing block, the dentistry symbols and √'s
#   vinculum: extruded at the edge(s) the ink reaches, so a corner's
#   stem stays on the cell centre and no stroke changes weight — unless
#   edge_is_rule says the reaching edge is a diagonal or an arc (╱ ╳ ╭),
#   which is stretched whole like the first group
# The dashed rules ┄ ┅ ┈ ┉ ╌ ╍ sit inside the box-drawing block but are
# stretched, and stretched whether or not their ink reaches the edge:
# Source Han Sans insets their end dashes by half a gap so that cells
# continue the pattern, which is exactly what the edge test cannot see
# — centred in 1200, the gap at every cell boundary was 312u against
# 111u inside the cell.
TILING_STRETCH = ((0x2504, 0x2505), (0x2508, 0x2509), (0x254C, 0x254D),
                  (0x2580, 0x259F), (0x25E2, 0x25E5), (0x2E3A, 0x2E3B),
                  (0x3030, 0x3030), (0xFE49, 0xFE4F), (0xFF3F, 0xFF3F),
                  (0xFFE3, 0xFFE3))
TILING_RULE = ((0x221A, 0x221A), (0x23BE, 0x23CC), (0x2500, 0x257F))


def tiling_glyphs(font):
    """{glyph: 'stretch' | 'rule'} for every glyph a tiling character
    reaches through the cmap. Not through vert: a rotated rule tiles
    vertically, and in Term its width is centred like any other
    glyph's."""
    cmap = font.getBestCmap()
    out = {}
    # the stretch blocks last, so the dashed rules inside the box-drawing
    # block take that treatment
    for blocks, how in ((TILING_RULE, "rule"), (TILING_STRETCH, "stretch")):
        for lo, hi in blocks:
            for cp in range(lo, hi + 1):
                name = cmap.get(cp)
                if name is not None:
                    out[name] = how
    return out


def shift_mark_placements(font, moved):
    """Move the GPOS placements that put a mark on the vertical column
    with the outline widen_fullwidth just moved. Returns the number of
    subtables adjusted.

    Source Han Sans centres its full-width marks for a vertical run in
    'vert', with a SinglePos that places them +500 across the column —
    a number measured against the outline, the way an anchor is. Move
    the outline and leave it, and in Term the enclosing circle sat 100
    units left of the column it encloses, the tone marks U+302A/302B
    hung outside its left edge and U+302C/302D stood inside its
    right."""
    if not moved or "GPOS" not in font:
        return 0
    done = 0
    for lookup in font["GPOS"].table.LookupList.Lookup:
        kind, subtables = _unwrap_pos(lookup)
        if kind != 1:
            continue
        for sub in subtables:
            names = getattr(getattr(sub, "Coverage", None), "glyphs", None) or []
            ours = [n for n in names if n in moved]
            if not ours:
                continue
            if not sub.ValueFormat & 0x1:
                continue
            step = moved[ours[0]]
            if sub.Format == 2:
                # one ValueRecord per covered glyph: move only ours
                for name, value in zip(names, sub.Value):
                    if name in moved:
                        value.XPlacement = getattr(value, "XPlacement", 0) - step
                done += 1
                continue
            if len(ours) != len(names):
                # one shared ValueRecord for glyphs that no longer move
                # together: it would have to be split in two
                rest = [n for n in names if n not in moved]
                raise ValueError(
                    "a GPOS placement covers both moved marks and other "
                    f"glyphs (moved: {ours[:4]}, not: {rest[:4]}); it "
                    "would need splitting")
            sub.Value.XPlacement = getattr(sub.Value, "XPlacement", 0) - step
            done += 1
    return done


def realign_halfwidth_marks(font, moved, widened):
    """Put the full-width combining marks back where they were over a
    base the widening did not move. Returns the number of glyphs the
    rule covers.

    widen_fullwidth moves them with the cell they ride on — but only
    the full-width cell grew. The half-width layer (the Latin, and the
    Halfwidth katakana) is one cell in both families, so over ｶ or ﾈ
    the mark came out 100 units left of where Source Han Sans puts it,
    into the kana's own strokes: 25 of the 116 Halfwidth-kana-and-
    voicing pairs went from touching nowhere to sharing up to 4,651
    square units of ink. A contextual rule gives those 100 units back
    when the base did not move; everything else keeps it.

    "Did not move" is `widened` — the glyphs widen_fullwidth actually
    touched — and not "one cell wide", which is what this asked at
    first. The Latin layer also owns 63 multi-cell ligature glyphs
    (`==`, `===`, `!==`, their cv99 designs: 1200, 1800 and 2400 units),
    and a ligature that lands on a whole number of full widths is in
    the widening's own `skip` set, so its advance is the same in both
    families — but it is not one cell, so all 488 ligature-and-mark
    pairs kept the move and the ring around ＝＝ came out 100 units off
    its own cells. Advance alone cannot tell them apart: 1200 is a
    widened full-width glyph in Term and an untouched ligature."""
    if not moved or "GPOS" not in font:
        return 0
    hmtx = font["hmtx"]
    gid = font.getGlyphID
    halves = sorted((name for name in font.getGlyphOrder()
                     if hmtx[name][0] > 0 and name not in widened), key=gid)
    if not halves:
        return 0

    def coverage(names):
        cov = otTables.Coverage()
        cov.glyphs = sorted(names, key=gid)
        return cov

    back = otTables.SinglePos()
    back.Format = 1
    back.Coverage = coverage(moved)
    back.Value = otTables.ValueRecord()
    # every mark moved by the same step, and this undoes it
    back.Value.XPlacement = -next(iter(moved.values()))
    back.ValueFormat = 0x1
    gpos = font["GPOS"].table
    first = len(gpos.LookupList.Lookup)
    gpos.LookupList.Lookup.append(_new_lookup_obj(1, back))

    # every OTHER mark is skipped while matching: the lookup filters on
    # the attachment class these eight get to themselves, so a Latin
    # accent between the base and the mark — 'B' + U+0300 + U+20DD, and
    # 1,908 sequences like it — no longer breaks the chain. What is
    # left to enumerate is a run of these eight themselves, one
    # subtable per depth: in ｶ ゛ ⃝ the glyph before the circle is the
    # dakuten, and three of them deep is as far as this goes
    gdef = base_gdef(font)
    ours_class = 0
    if gdef is not None:
        classes = dict(getattr(getattr(gdef, "MarkAttachClassDef", None),
                               "classDefs", None) or {})
        ours_class = max(classes.values(), default=0) + 1
        for name in moved:
            classes[name] = ours_class
        if gdef.MarkAttachClassDef is None:
            gdef.MarkAttachClassDef = otTables.MarkAttachClassDef()
        gdef.MarkAttachClassDef.classDefs = classes
    rules = []
    for depth in range(4):
        rule = otTables.ChainContextPos()
        rule.Format = 3
        rule.BacktrackCoverage = ([coverage(moved)] * depth
                                  + [coverage(halves)])
        rule.BacktrackGlyphCount = depth + 1
        rule.InputCoverage = [coverage(moved)]
        rule.InputGlyphCount = 1
        rule.LookAheadCoverage = []
        rule.LookAheadGlyphCount = 0
        rec = otTables.PosLookupRecord()
        rec.SequenceIndex, rec.LookupListIndex = 0, first
        rule.PosLookupRecord = [rec]
        rule.PosCount = 1
        rules.append(rule)
    chain = _new_lookup_obj(8, rules[0])
    chain.SubTable = rules
    chain.SubTableCount = len(rules)
    # skip every other mark. Without a GDEF there is no class to filter
    # on, and naming one anyway would make a shaper skip EVERY mark —
    # the input marks included, which is the whole rule
    chain.LookupFlag = ours_class << 8
    gpos.LookupList.Lookup.append(chain)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)
    # under 'dist', not 'mark': a shaper runs 'mark' in a vertical run
    # too, and there the marks are already put on the column by Source
    # Han Sans's own 'vert' placement (shift_mark_placements moves that
    # one with the outline). Correcting again there pushed the tone
    # marks 100 units clear of the column. 'dist' is horizontal-only
    # and is exactly what it is for
    _add_feature(gpos, "dist", [first + 1])
    sort_feature_list(gpos)
    return len(halves)


def rehome_replaced_marks(base, replaced):
    """Put the grafted accents into the mark lookups Source Han Sans
    keeps for its OWN copies of them. Returns the number of entries
    added.

    Source Han Sans attaches the Bopomofo tone marks to the Bopomofo
    letters with three MarkBasePos lookups, and their MarkCoverage names
    Source Han Sans's own U+0300, U+0301, U+0307 and U+030C. The graft
    re-points those four codepoints at the Latin donor's accents and
    leaves the coverage naming glyphs no codepoint reaches any more, so
    nothing attaches: 164 of the 188 Bopomofo-and-tone pairs drew the
    mark straight through the letter's strokes (ㄓ + U+0301 at 636..836
    against a letter at 66..934, where Source Han Sans hangs it off the
    right shoulder at 760..1120, 284 units further right and 226 up).
    U+02EA and U+02EB kept Source Han Sans's own glyphs and still
    attach, which is how the rest of the machinery is known to be
    sound.

    The two outlines are not the same shape, so the anchor comes over
    shifted by the difference between the two inks' centres: the donor's
    accent then lands where Source Han Sans puts its own."""
    if "GPOS" not in base or not replaced:
        return 0
    cmap = base.getBestCmap()
    gs = base.getGlyphSet()
    gid = base.getGlyphID
    swap = {}
    for cp, theirs in replaced.items():
        ours = cmap.get(cp)
        if ours and ours != theirs:
            swap.setdefault(theirs, ours)

    def centre(name):
        box = _bounds(gs, name)
        return None if box is None else ((box[0] + box[2]) / 2,
                                         (box[1] + box[3]) / 2)

    added = 0
    for lookup in base["GPOS"].table.LookupList.Lookup:
        kind, subtables = _unwrap_pos(lookup)
        if kind not in (4, 5, 6):
            continue
        for sub in subtables:
            cov = getattr(sub, "MarkCoverage", None) or \
                getattr(sub, "Mark1Coverage", None)
            array = getattr(sub, "MarkArray", None) or \
                getattr(sub, "Mark1Array", None)
            if cov is None or array is None:
                continue
            pairs = list(zip(cov.glyphs, array.MarkRecord))
            for name, rec in list(pairs):
                ours = swap.get(name)
                if not ours or ours in cov.glyphs:
                    continue
                theirs_c, ours_c = centre(name), centre(ours)
                if theirs_c is None or ours_c is None:
                    continue
                anchor = otTables.Anchor()
                anchor.Format = 1
                anchor.XCoordinate = round(rec.MarkAnchor.XCoordinate
                                           + ours_c[0] - theirs_c[0])
                anchor.YCoordinate = round(rec.MarkAnchor.YCoordinate
                                           + ours_c[1] - theirs_c[1])
                copy = otTables.MarkRecord()
                copy.Class, copy.MarkAnchor = rec.Class, anchor
                pairs.append((ours, copy))
                added += 1
            pairs.sort(key=lambda pair: gid(pair[0]))
            cov.glyphs = [name for name, _rec in pairs]
            array.MarkRecord = [rec for _name, rec in pairs]
            array.MarkCount = len(pairs)
    return added


def base_gdef(font):
    """The font's GDEF table, or None."""
    return getattr(font.get("GDEF"), "table", None)


def _new_lookup_obj(kind, subtable):
    """A Lookup holding one subtable, with no flags."""
    lookup = otTables.Lookup()
    lookup.LookupType = kind
    lookup.LookupFlag = 0
    lookup.SubTable = [subtable]
    lookup.SubTableCount = 1
    return lookup


def fullwidth_marks(font):
    """The 0-advance combining marks Source Han Sans draws INSIDE a
    full-width cell — the enclosing circle and square, the kana voicing
    marks, the ideographic tone marks. They ride on the cell before
    them, so widen_fullwidth has to move them with it.

    Source Han Sans draws them one FULL WIDTH left of the origin, the
    way graft_halfwidth draws ours one CELL left, so widening the cell
    to 1200 has to take them 100 units further left — not right. Told
    from the grafted Latin marks by `built`: those are ours, the Latin
    cell is 600 in both families, and they stay put.

    What says "drawn in the full-width cell" is where the ink's CENTRE
    falls, not a hair's breadth either side of the cell's own edges. The
    first version of this allowed 2 units, and Source Han Sans's strokes
    thicken with the weight: at Medium the ideographic tone marks reach
    -1007 and +7, at Bold the voicing marks +5 and +7, so four of the
    eight fell out of the set at Medium and six at Bold. Those marks
    kept the 1000-unit cell in Term (the enclosing ring 100 units off
    the character it encloses, at three of the five weights), and the
    half-set then tripped shift_mark_placements, which is where the CI
    build stopped. Source Han Sans's own Latin marks, which the graft
    may not have replaced, are drawn to the RIGHT of the origin — even
    U+0304, the widest, is centred on it — so the centre tells them
    apart at any weight."""
    hmtx = font["hmtx"]
    gs = font.getGlyphSet()
    built = state_of(font).built
    slack = FULLWIDTH // 20
    out = set()
    for cp, name in font.getBestCmap().items():
        if (name in built or hmtx[name][0] != 0
                or unicodedata.category(chr(cp)) not in ("Mn", "Me")):
            continue
        box = _bounds(gs, name)
        if (box is not None and box[0] >= -FULLWIDTH - slack
                and box[2] <= slack and (box[0] + box[2]) / 2 < 0):
            out.add(name)
    return out


def widen_fullwidth(font, cell, skip=()):
    """Term variant: widen every full-width glyph's advance to two cells
    (2 x cell; an n-full-width glyph such as ⸻ to 2n cells) and center
    the unchanged outline. The terminal grid becomes exact (CJK = two
    cells, symmetric padding instead of a right-side gap).

    The Latin layer is on the cell grid and passes through untouched —
    except that a multi-cell ligature can land on a whole number of full
    widths too (5 cells = 3000 = three full widths), so `skip` names the
    ligature glyphs.

    A tiling character (TILING_STRETCH / TILING_RULE, tiling_glyphs)
    whose ink reaches an edge of its own advance is drawn to meet a
    neighbour there — ＿ ￣ 〰 ◢, ⸺ ⸻ and the dashed overlines ﹉–﹏.
    Centring one of those would leave white at that
    join, so it is lengthened on that side instead: extruded where the
    edge is a rule (extend_edges), stretched whole where it is a block,
    a pattern, a diagonal or a wave.

    The other outlines are moved inside their charstrings (shift_charstring),
    so Source Han Sans's own hints survive on the 17,000 glyphs this
    touches — redrawing them cost autohint 100 seconds per face; a
    glyph shift_charstring declines is redrawn and re-hinted."""
    cff = font["CFF "].cff
    cff.desubroutinize()   # shift_charstring reads a flat program
    td = cff[cff.fontNames[0]]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    redrawn, moved_by, marks_moved = {}, {}, {}
    shifted = tiled = 0
    tiling = tiling_glyphs(font)
    skip = set(skip)
    full_marks = fullwidth_marks(font)
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if name in full_marks:
            # a combining mark carries no advance of its own and rides
            # on the cell before it, so it has to move with that cell:
            # Source Han Sans's own full-width marks (the enclosing
            # circle and square, the kana voicing marks, the ideographic
            # tone marks) are drawn inside a 1000-unit cell, and leaving
            # them there put the circle 100 units right of the kanji it
            # encloses — through its left edge. They hang to the LEFT of
            # the origin, over the cell that has just been widened, so
            # they move the other way from the glyph that carries them
            step = -((2 * cell - FULLWIDTH) // 2)
            private = glyph_private(font, td, name)
            if shift_charstring(td.CharStrings[name], step, 0, private):
                shifted += 1
            else:
                pen = T2CharStringPen(pen_width(private, 0), gs)
                gs[name].draw(TransformPen(pen, (1, 0, 0, 1, step, 0)))
                redrawn[name] = pen.getCharString(private=private)
            hmtx.metrics[name] = (0, lsb + step)
            moved_by[name] = step
            marks_moved[name] = step
            continue
        if adv <= 0 or adv % FULLWIDTH or name in skip:
            continue
        full = (adv // FULLWIDTH) * 2 * cell
        shift = (full - adv) // 2
        private = glyph_private(font, td, name)
        how = tiling.get(name)
        box = _bounds(gs, name) if how else None
        left = box is not None and box[0] <= 2
        right = box is not None and box[2] >= adv - 2
        if how == "stretch" or (how == "rule" and (left or right)):
            # drawn to TILE with a neighbour at the edge its ink reaches:
            # centring it in the wider advance leaves `shift` units of
            # white at that join, so a rule of ＿ or ─ came out dashed, █
            # striped, and every corner of a box stood 100u clear of the
            # rule it should meet
            path = pathops.Path()
            gs[name].draw(path.getPen())
            if how == "rule" and all(edge_is_rule(path, side) for side, on in
                                     (("left", left), ("right", right)) if on):
                path = extend_edges(_xform_path(path, (1, 0, 0, 1, shift, 0)),
                                    shift, left, right)
            else:
                path = _xform_path(path, (full / adv, 0, 0, 1, 0, 0))
            pen = T2CharStringPen(pen_width(private, full), gs)
            path.draw(pen)
            cs = redrawn[name] = pen.getCharString(private=private)
            tiled += 1
            # the ink grew as well as moved, so the bearing is the new
            # outline's own xMin and not the old one plus the shift
            hmtx.metrics[name] = (full, charstring_lsb(cs))
            moved_by[name] = shift
            continue
        if shift_charstring(td.CharStrings[name], shift, full, private):
            shifted += 1
        else:
            pen = T2CharStringPen(pen_width(private, full), gs)
            gs[name].draw(TransformPen(pen, (1, 0, 0, 1, shift, 0)))
            redrawn[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (full, lsb + shift)
        moved_by[name] = shift
    for name, cs in redrawn.items():
        td.CharStrings[name] = cs        # a plain CFF has no charStringsIndex
    shift_anchors(font, moved_by)
    shift_mark_placements(font, marks_moved)
    realign_halfwidth_marks(font, marks_moved, moved_by)
    note_redrawn(font, redrawn)
    print(f"  full-width widened to {2 * cell}: {shifted} shifted with their hints, "
          f"{len(redrawn)} redrawn ({tiled} of them lengthened to keep tiling)")


# name IDs we drop before writing our own (every platform/encoding, so no
# stale record survives beside ours). 0 (Copyright) and 9 (Designer) are
# rebuilt FROM the inherited Source Han Sans strings plus the other
# donors' — every OFL notice stays, ours is prepended. 13/14 (License)
# are inherited untouched. 7 (trademark: "Source is a trademark of
# Adobe") and 25 (variations PostScript name prefix, SCP's own
# "SourceCodeUpright") are dropped, not
# rewritten: neither describes a font not named Source, and Adobe's notice
# already travels in nameID 0's credits. build_latin_vf.py sets its own 25.
OWNED_NAME_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 16, 17, 25)


def set_names(font, suffix, weight, italic, italic_angle=-12.0, version=None,
              credits=(), family_base="Gengou Code JP", ps_base="GengouCodeJP",
              base_credit="Source Han Sans"):
    """Rewrite the family-identifying names, preserve the legal ones.

    `version` (GENGOU_VERSION, e.g. "3.1.0") stamps our own release version
    when set: head.fontRevision becomes MAJOR.MINOR, nameID 5 notes both
    our version and the inherited Source Han Sans revision, and the CFF
    version matches head. Left None (the default), the inherited SHS
    revision is kept as-is — today's behaviour, used for CI builds.

    `credits`: [(donor label, copyright text, designer text), ...] for the
    donors other than Source Han Sans (whose own strings are inherited in
    the base font's name table and credited under `base_credit`; pass
    None for a font with no Source Han Sans glyphs, e.g. the Latin-only
    face) — appended to name IDs 0 and 9 so the Source Code Pro and
    Monaspace notices ship inside the font, not only in LICENSE. Also drops Source Han Sans's DSIG (a signature over bytes
    that no longer exist) and replaces Adobe's vendor identity (nameID
    8/11, OS/2 achVendID) with the project's.
    """
    base_family = (family_base + " " + suffix).strip()
    ribbi = weight in ("Regular", "Bold")
    family = base_family if ribbi else f"{base_family} {weight}"
    sub = (weight if ribbi else "Regular") + (" Italic" if italic else "")
    sub = sub.replace("Regular Italic", "Italic")
    psfam = ps_base + suffix
    ps = f"{psfam}-{weight}{'Italic' if italic else ''}"
    full = f"{family} {sub}".replace(" Regular", "").strip()
    name = font["name"]
    shs_copyright = name.getDebugName(0) or "" if base_credit else ""
    shs_designer = name.getDebugName(9) or "" if base_credit else ""
    # drop stale records for the IDs we own (every platform/encoding), so
    # the base font's Source Han Sans strings can't survive alongside ours
    name.names = [n for n in name.names if n.nameID not in OWNED_NAME_IDS]
    # version: GENGOU_VERSION (set) stamps our own release version and notes
    # the inherited SHS revision alongside it; unset (CI builds) keeps that
    # inherited revision as-is, as before.
    shs_rev = font["head"].fontRevision
    if version:
        major, minor = version.split(".")[:2]
        cff_version = f"{major}.{minor}"
        font["head"].fontRevision = float(cff_version)
        version_str = f"Version {version};{base_family}"
        if base_credit:
            version_str += f";SHS {shs_rev:.3f}"
        unique_version = version
    else:
        cff_version = f"{shs_rev:.3f}"
        version_str = f"Version {shs_rev:.3f};{base_family}"
        unique_version = cff_version
    # base_family, not family_base: a Term face's own family carries the
    # suffix, and naming it "Gengou Code JP" here left nameID 0 and 5 pointing
    # at a family the face is not in -- which nerdpatch.rename then
    # marked, giving a Gengou Code JP Term NF face a version
    # string reading "Gengou Code JP NF"
    copyright_parts = [f"{base_family}: {PROJECT_COPYRIGHT}."]
    designer_parts = []
    if base_credit:
        copyright_parts.append(f"{base_credit}: {shs_copyright}")
        designer_parts.append(shs_designer)
    for label, notice, designer in credits:
        if notice:
            copyright_parts.append(f"{label}: {notice}")
        if designer:
            designer_parts.append(f"{label}: {designer}")
    # one sentence per donor: SCP's notice ends in a quote, not a period
    copyright_parts = [p if p.rstrip().endswith(".") else p.rstrip() + "."
                       for p in copyright_parts]
    for nid, val in ((0, " ".join(copyright_parts)),
                     (1, family), (2, sub),
                     (3, f"{unique_version};{VENDOR_ID};{ps}"),
                     (4, full), (5, version_str), (6, ps),
                     (8, "hn-11"), (9, "; ".join(p for p in designer_parts if p)),
                     (11, PROJECT_URL),
                     (16, base_family),
                     (17, (weight + (" Italic" if italic else ""))
                          .replace("Regular Italic", "Italic"))):
        name.setName(val, nid, 3, 1, 0x409)
    os2 = font["OS/2"]
    os2.achVendID = VENDOR_ID
    os2.usWeightClass = WEIGHT_CLASS[weight]
    # PANOSE weight rides with it, and is set here rather than in
    # set_monospace_metadata because this is where the weight is known:
    # each face takes the Source Han Sans weight whose bar matches its
    # Latin, not the one that shares its name, and Source Code Pro's VF
    # carries its default master's — so every face inherited a PANOSE
    # that disagreed with its own usWeightClass (Regular 4 against 400).
    # A GDI-era matcher substitutes on it
    os2.panose.bWeight = panose_weight(WEIGHT_CLASS[weight])
    if "DSIG" in font:
        del font["DSIG"]
    # a variable font (build_latin_vf.py) carries CFF2, not CFF; CFF2's
    # TopDict has no FamilyName/FullName/version (guarded below), only the
    # placeholder fontNames[0] this still overwrites
    cff = font["CFF2"].cff if "CFF2" in font else font["CFF "].cff
    cff.fontNames[0] = ps
    td = cff[ps]
    if hasattr(td, "FamilyName"):
        td.FamilyName = family
    if hasattr(td, "FullName"):
        td.FullName = full
    if hasattr(td, "version"):
        td.version = cff_version
    # Windows' family-linking model reads *these* bits, not the name-table
    # text above, to decide which face is "the bold" / "the italic" of a
    # family — fsSelection/macStyle must always agree with nameID 2 (RIBBI
    # subfamily) or apps that key off them (Office, GDI) pick the wrong face.
    bold = weight == "Bold"
    fsel = font["OS/2"].fsSelection & ~0x61  # clear ITALIC(0)/BOLD(5)/REGULAR(6)
    if italic:
        fsel |= 0x1
    if bold:
        fsel |= 0x20
    if not italic and not bold:
        fsel |= 0x40
    # WWS (bit 8): every face is fully described by weight/width/slope
    # names, which is what lets DirectWrite group the 12 faces under one
    # typographic family (nameID 16/17). The bit exists from OS/2 v4 on;
    # v4 adds nothing else to the v3 layout Source Han Sans ships.
    fsel |= 0x100
    if font["OS/2"].version < 4:
        font["OS/2"].version = 4
    font["OS/2"].fsSelection = fsel
    mac = font["head"].macStyle & ~0x3  # clear Bold(0)/Italic(1)
    if bold:
        mac |= 0x1
    if italic:
        mac |= 0x2
    font["head"].macStyle = mac
    if italic:
        font["post"].italicAngle = italic_angle
        # caret follows the same angle the outlines actually carry
        font["hhea"].caretSlopeRise = 1000
        font["hhea"].caretSlopeRun = round(
            1000 * math.tan(math.radians(-italic_angle)))
    else:
        font["post"].italicAngle = 0
        font["hhea"].caretSlopeRise = 1
        font["hhea"].caretSlopeRun = 0
    return ps


# Standalone ASCII punctuation redrawn from Monaspace so it matches the
# ligatures cut from the same instance — every one of the 32 symbols;
# letters and digits stay Source Code Pro. The first five ('=' '<' '>'
# '|' '~') differed from their ligatures in shape ('=' vs '==' bar gap,
# SCP 170u / Monaspace 219u; '<' vs '<=' size and angle; '|' vs '||'
# vertical extent; '~' vs '~>' amplitude). The rest differ mostly in
# vertical size: Monaspace's cap height and x-height sit above SCP's, so
# '!' '&' '?' ':' ';' rise 16-67u, brackets and '#' '@' '$' are 60-150u
# taller and up to 96u wider — all still inside the cell, and under two
# pixels at terminal sizes, whereas a '#' beside '#[' or a '-' beside '->'
# in a different skeleton was the visible seam. '-' is 124u narrower than
# '=' (so is Monaspace's own). SCP's cv14/cv15/cv16 variants still swap
# '-' '*' '$' back to SCP's typographic forms when a user turns them on.
MONA_STANDALONE = string.punctuation   # !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~


def _new_lookup(gsub, *subtables):
    lookup = otl.buildLookup(list(subtables))
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount += 1
    return gsub.LookupList.LookupCount - 1


class _LookupRef:
    """What ChainContextualBuilder wants for a lookup to call: anything
    with a `lookup_index`."""
    def __init__(self, index):
        self.lookup_index = index


def _guard_subtables(font, seq_map, lig_lookup):
    """Context guards around the combined ligature lookup, the part of
    Monaspace's calt that a plain LigatureSubst cannot express.

    Monaspace builds its ligatures as chaining rules so that an operator
    run longer than any ligature stays plain: '&&=' is not '&' + '&=',
    '~~>' is not '~' + '~>', and '<|>' is neither '<|' + '>' nor '<' +
    '|>'. Four kinds of "ignore" rule (match, consume, substitute
    nothing) reproduce that, each only where the longer run is NOT itself
    a ligature (those are left to longest match inside `lig_lookup`):

      a. seq preceded by its own first glyph      ('&' before '&=')
      b. seq followed by its own last glyph       ('->' before '>')
      c. seq preceded by the body of another ligature that ends with
         seq's first glyph                        ('<' before '|>')
      d. seq followed by the tail of another ligature that starts with
         seq's last glyph                         ('<|' before '>')

    then one rule PER LIGATURE whose input sequence is the whole ligature,
    applying `lig_lookup` at its first glyph — longest first. Returns the
    subtables in that order; shapers try them in order and the first match
    wins, so a guard that fires consumes the run before any trigger rule
    sees it.

    The trigger's input must cover every component. A single one-glyph
    rule that lets the nested LigatureSubst run on past the matched input
    shapes fine in HarfBuzz (and fontkit) but not in DirectWrite — Windows
    Terminal rendered '->' plain — because what a nested lookup may consume
    beyond the input sequence is undefined by OpenType. Monaspace's own
    calt is built the way this is: input length == ligature length."""
    seqs = {tuple(k) for k in seq_map}
    # a set is for the membership tests below; the rules are emitted in a
    # fixed order so two builds of the same face produce the same GSUB
    # bytes (they used to differ by a permutation of the 16 rule sets —
    # shaping-identical over 67,239 probes, but not diffable)
    ordered = sorted(seqs, key=lambda seq: (-len(seq), seq))
    builder = otl.ChainContextSubstBuilder(font, None)
    Rule = otl.ChainContextualRule
    seen = set()   # a and c (or b and d) can derive the same guard twice

    def ignore(prefix, glyphs, suffix):
        if (prefix, glyphs, suffix) in seen:
            return
        seen.add((prefix, glyphs, suffix))
        builder.rules.append(Rule([{g} for g in prefix], [{g} for g in glyphs],
                                  [{g} for g in suffix], [None] * len(glyphs)))
    # A guard whose backtrack is non-empty (a, c) starts to the RIGHT of
    # the longer ligature it might pre-empt, so that ligature's own
    # trigger matches first, at the earlier position, and consumes the
    # run before this guard is reached: such a guard is always safe, and
    # skipping it when the longer run is itself a ligature is what let
    # '>>>=' shape as '>' '>' '≥' — the '>>' guard consumed the first two
    # glyphs and left '>=' unguarded, and the '>>=' that was supposed to
    # take them never got the chance.
    #
    # A guard whose backtrack is empty (b, d) starts where that longer
    # ligature starts, and every guard is tried before every trigger, so
    # it WOULD pre-empt it: '===' shaped as three plain glyphs the moment
    # '==' was guarded against a following '='. Those two keep the skip.
    for seq in ordered:
        ignore((seq[0],), seq, ())                                # a
        if seq + (seq[-1],) not in seqs:
            ignore((), seq, (seq[-1],))                           # b
        for other in ordered:
            # every ligature whose tail is this one, not only those that
            # overlap it by a single glyph: '=!=' ends with '!=', and
            # without this '==!=' shaped as '=' '=' '≠'
            if len(other) > len(seq) and other[-len(seq):] == seq:
                ignore(other[:-len(seq)], seq, ())                # c
            if other[-1] == seq[0]:
                ignore(other[:-1], seq, ())                       # c
            if other[0] == seq[-1] and seq + other[1:] not in seqs:
                ignore((), seq, other[1:])                        # d
    for seq in ordered:
        builder.rules.append(Rule([], [{g} for g in seq], [],
                                  [[_LookupRef(lig_lookup)]]
                                  + [None] * (len(seq) - 1)))
    return builder.build().SubTable


def _langsys_list(gsub):
    for script in gsub.ScriptList.ScriptRecord:
        for ls in [script.Script.DefaultLangSys] + [
                r.LangSys for r in script.Script.LangSysRecord]:
            if ls is not None:
                yield ls


def _add_feature(gsub, tag, lookup_indices):
    """Make `lookup_indices` reachable under `tag` from every LangSys.

    A LangSys that already lists a `tag` record gets the lookups merged
    into that record (shapers take the first matching tag and ignore a
    second record, so appending one would be dead weight). Source Han
    Sans carries one 'liga' record per script/langsys — eleven of them —
    and merging into just the first left 'latn' without our ligatures.
    LangSys that lack the tag share one new record. Returns that new
    record's index, or None when every LangSys already had the tag."""
    records = gsub.FeatureList.FeatureRecord
    existing = {i for i, fr in enumerate(records) if fr.FeatureTag == tag}
    merged = set()
    lacking = []
    for ls in _langsys_list(gsub):
        mine = existing.intersection(ls.FeatureIndex)
        if mine:
            merged.update(mine)
        else:
            lacking.append(ls)
    for i in merged:
        feat = records[i].Feature
        for li in lookup_indices:
            if li not in feat.LookupListIndex:
                feat.LookupListIndex.append(li)
        feat.LookupCount = len(feat.LookupListIndex)
    if not lacking:
        return None
    fr = otTables.FeatureRecord()
    fr.FeatureTag = tag
    fr.Feature = otTables.Feature()
    fr.Feature.FeatureParams = None
    fr.Feature.LookupListIndex = list(lookup_indices)
    fr.Feature.LookupCount = len(lookup_indices)
    records.append(fr)
    gsub.FeatureList.FeatureCount = len(records)
    new = len(records) - 1
    for ls in lacking:
        ls.FeatureIndex.append(new)
        ls.FeatureCount = len(ls.FeatureIndex)
    return new


def _alloc_name_id(font):
    """An unused nameID in the user range (>= 256)."""
    used = {rec.nameID for rec in font["name"].names}
    n = 256
    while n in used:
        n += 1
    return n


def _add_ui_name(font, text):
    """Add `text` as a Windows/Unicode BMP/en-US (3/1/0x409) name record,
    the platform triple every shaper UI reads, and return its nameID."""
    nid = _alloc_name_id(font)
    font["name"].setName(text, nid, 3, 1, 0x409)
    return nid


def _set_feature_params(font, gsub, index, tag, name=None):
    """Attach a UI name to the feature we just authored at `index`.

    `name` (when given) wins — it's SCP's own UI name for the ssNN/cvNN
    tag, carried through by import_scp_variants — otherwise we fall back
    to GROUP_NAMES for our own ss01-ss08 / cv99. Features merged into a
    record that already existed (index is None) belong to the base font
    and keep whatever FeatureParams they had; the SCP-imported tags don't
    exist in the SHS base today, but the guard stays in case that changes.
    """
    if index is None:
        return
    name = name or GROUP_NAMES.get(tag)
    if not name:
        return
    nid = _add_ui_name(font, name)
    feat = gsub.FeatureList.FeatureRecord[index].Feature
    if tag.startswith("cv"):
        params = otTables.FeatureParamsCharacterVariants()
        params.Format = 0
        params.FeatUILabelNameID = nid
        params.FeatUITooltipTextNameID = 0
        params.SampleTextNameID = 0
        params.NumNamedParameters = 0
        params.FirstParamUILabelNameID = 0
        params.CharCount = 0
        params.Character = []
    else:
        params = otTables.FeatureParamsStylisticSet()
        params.Version = 0
        params.UINameID = nid
    feat.FeatureParams = params


def sort_feature_list(gsub):
    """OpenType requires FeatureList sorted by tag; re-sort and remap every
    LangSys FeatureIndex through the old->new table."""
    records = gsub.FeatureList.FeatureRecord
    order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    remap = {old: new for new, old in enumerate(order)}
    gsub.FeatureList.FeatureRecord = [records[i] for i in order]
    gsub.FeatureList.FeatureCount = len(records)
    for ls in _langsys_list(gsub):
        ls.FeatureIndex = sorted(remap[i] for i in ls.FeatureIndex
                                 if i in remap)
        ls.FeatureCount = len(ls.FeatureIndex)
        remap_required(ls, remap)
    return remap


NO_REQUIRED_FEATURE = 0xFFFF


def remap_required(langsys, remap):
    """A LangSys's ReqFeatureIndex points into the same FeatureList as
    its FeatureIndex list, so it has to move with it — and 0xFFFF, its
    "none", must not be remapped. Source Han Sans sets none today."""
    req = getattr(langsys, "ReqFeatureIndex", NO_REQUIRED_FEATURE)
    if req != NO_REQUIRED_FEATURE:
        langsys.ReqFeatureIndex = remap.get(req, NO_REQUIRED_FEATURE)


def drop_features(font, tags):
    """Remove every FeatureRecord whose tag is in `tags` from GSUB and GPOS
    alike: drop it from FeatureList and every LangSys's FeatureIndex,
    remapping the remaining indices — same pattern as sort_feature_list().
    Used for the features that move a glyph off the fixed cell:
    'pwid'/'palt' (proportional width has no meaning here), 'kern' and
    'halt' (Source Han Sans kerns あ+て 20u tighter than the cell, and
    'kern' is on by default in every horizontal shaper). The vertical
    features stay: the faces keep vmtx/vhea, and 'vert' is the one
    HarfBuzz turns on for a vertical run."""
    for tbl_tag in ("GSUB", "GPOS"):
        if tbl_tag not in font:
            continue
        table = font[tbl_tag].table
        records = table.FeatureList.FeatureRecord
        drop = {i for i, fr in enumerate(records) if fr.FeatureTag in tags}
        if not drop:
            continue
        keep = [i for i in range(len(records)) if i not in drop]
        remap = {old: new for new, old in enumerate(keep)}
        table.FeatureList.FeatureRecord = [records[i] for i in keep]
        table.FeatureList.FeatureCount = len(keep)
        for ls in _langsys_list(table):
            ls.FeatureIndex = sorted(remap[i] for i in ls.FeatureIndex
                                     if i in remap)
            ls.FeatureCount = len(ls.FeatureIndex)
            remap_required(ls, remap)


def _lookup_records(root):
    """Every Subst/PosLookupRecord anywhere inside a subtable.

    The contextual formats nest them at different depths (format 3 holds
    them on the subtable, formats 1 and 2 one or two rule objects down),
    but fontTools gives them the same shape wherever they sit — a
    SequenceIndex and a LookupListIndex — so the walk finds them without
    a catalogue of formats to fall out of date."""
    out, stack, seen = [], [root], set()
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, (list, tuple)):
            stack.extend(obj)
            continue
        fields = getattr(obj, "__dict__", None)
        if not fields:
            continue
        if "LookupListIndex" in fields and "SequenceIndex" in fields:
            out.append(obj)
            continue
        stack.extend(fields.values())
    return out


def prune_orphan_lookups(font):
    """Drop the lookups nothing reaches any more. Returns {table: count}.

    drop_features removes a FeatureRecord but not the lookups it was the
    only route to, and Source Han Sans's kern / halt / palt left 36 KB of
    unreachable GPOS in every JP face that way. Reachability starts at
    the FeatureList — every LangSys's features and its required one are
    indices into it, and drop_features has already pruned those — and
    follows the contextual lookups' own references, which is why one pass
    over the features is not enough.

    A font with a JSTF is left alone: JSTF indexes this same LookupList
    and nothing here would renumber it."""
    if "JSTF" in font:
        return {}
    freed = {}
    for tag, unwrap in (("GSUB", _unwrap), ("GPOS", _unwrap_pos)):
        if tag not in font:
            continue
        table = font[tag].table
        ll = getattr(table, "LookupList", None)
        if ll is None or not ll.Lookup:
            continue
        lookups = ll.Lookup
        # from the LangSys, not the FeatureList: a FeatureRecord nothing
        # names is no route either (prune_orphan_features drops those)
        records = table.FeatureList.FeatureRecord
        named = set()
        for ls in _langsys_list(table):
            named.update(ls.FeatureIndex)
            req = getattr(ls, "ReqFeatureIndex", NO_REQUIRED_FEATURE)
            if req != NO_REQUIRED_FEATURE:
                named.add(req)
        reach, stack = set(), [i for k in sorted(named) if k < len(records)
                               for i in records[k].Feature.LookupListIndex]
        while stack:
            i = stack.pop()
            if i in reach or not 0 <= i < len(lookups):
                continue
            reach.add(i)
            for sub in unwrap(lookups[i])[1]:
                stack.extend(r.LookupListIndex for r in _lookup_records(sub))
        if len(reach) == len(lookups):
            continue
        keep = sorted(reach)
        remap = {old: new for new, old in enumerate(keep)}
        for fr in table.FeatureList.FeatureRecord:
            # a record no LangSys names may point at what was just
            # dropped; it is itself dead (prune_orphan_features)
            fr.Feature.LookupListIndex = [remap[i]
                                          for i in fr.Feature.LookupListIndex
                                          if i in remap]
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
        for i in keep:
            for sub in unwrap(lookups[i])[1]:
                for rec in _lookup_records(sub):
                    rec.LookupListIndex = remap[rec.LookupListIndex]
        ll.Lookup = [lookups[i] for i in keep]
        ll.LookupCount = len(keep)
        freed[tag] = len(lookups) - len(keep)
    return freed


def feature_map(font, tag):
    """{glyph: substitute} over every Single / Alternate subst reachable
    under `tag` — Source Han Sans's own vertical forms, say. The first
    substitute wins where a glyph has more than one."""
    out = {}
    for src, dst in _feature_pairs(font, tag):
        out.setdefault(src, dst)
    return out


def _feature_pairs(font, tag):
    """(glyph, substitute) over every Single / Alternate subst under
    `tag`, in lookup order."""
    if "GSUB" not in font:
        return
    gsub = font["GSUB"].table
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag != tag:
            continue
        for li in fr.Feature.LookupListIndex:
            kind, subs = _unwrap(gsub.LookupList.Lookup[li])
            yield from _subst_pairs(kind, subs, tag)


def add_gsub(font, added, alts, ligatures, variant_maps=None,
             variant_names=None):
    """calt/liga carry every ligature (default on); each Monaspace-style
    group is additionally exposed as ssNN so users can toggle selectively
    (calt off + ssNN on). cv99 switches to the .alt operator designs."""
    cmap = font.getBestCmap()
    gsub = font["GSUB"].table

    groups = {}
    for seq, g in added.items():
        grp = ligatures[seq]["group"]
        groups.setdefault(grp, {})[tuple(cmap[ord(c)] for c in seq)] = g

    # calt/liga use ONE combined lookup: LigatureSubst is longest-match only
    # within a single subtable — sequential per-group lookups would let
    # ss01's '>=' eat the tail of '>>=' before ss02 ever sees it.
    combined = {}
    for m in groups.values():
        combined.update(m)
    combined_lookup = _new_lookup(
        gsub, otl.buildLigatureSubstSubtable(combined))

    # each ssNN group below gets its OWN subtable, so that longest-match
    # guarantee is per group only: with calt off, enabling ss01 + ss02
    # together can let ss01's '>=' eat the prefix of ss02's '>>=' before
    # the longer match is ever tried. Accepted — Monaspace's own
    # stylistic sets have the same property; calt is the cross-group-safe
    # way to get everything at once.
    group_lookups = {}
    for grp in sorted(groups):
        group_lookups[grp] = _new_lookup(
            gsub, otl.buildLigatureSubstSubtable(groups[grp]))

    guarded_lookup = _new_lookup(
        gsub, *_guard_subtables(font, combined, combined_lookup))
    for tag in ("calt", "liga"):
        _add_feature(gsub, tag, [guarded_lookup])
    for grp in sorted(group_lookups):
        _set_feature_params(
            font, gsub, _add_feature(gsub, grp, [group_lookups[grp]]), grp)
    if alts:
        alt_lookup = _new_lookup(gsub, otl.buildSingleSubstSubtable(alts))
        _set_feature_params(
            font, gsub, _add_feature(gsub, "cv99", [alt_lookup]), "cv99")
    for tag in sorted(variant_maps or {}):
        vlookup = _new_lookup(
            gsub, otl.buildSingleSubstSubtable(variant_maps[tag]))
        _set_feature_params(
            font, gsub, _add_feature(gsub, tag, [vlookup]), tag,
            (variant_names or {}).get(tag))
    sort_feature_list(gsub)


# the tightest side bearing the Latin donor gives a letter: Source Code
# Pro's 'w' and 'W' carry 8 units either side of the 600 cell. A letter
# condensed to fit the cell gets the same, rather than an ink-exact fit
# that would leave it abutting its neighbours
LETTER_BEARING = 8


def cell_fit(box, cell=CELL, bearing=LETTER_BEARING):
    """(x scale, x offset) that seats `box`'s ink in one cell: centred,
    and condensed only where the ink will not fit the cell less a
    bearing at each side — and then only as far as that.

    Condensing costs stroke weight, and a letter squeezed beside letters
    that were not reads as thin and small inside its own alphabet, so
    the letters that need it are the only ones that get it. A glyph with
    no ink is centred trivially.

    build_latin.add_missing_from_sans applies it, seating Source Sans's
    proportional Greek and Cyrillic in the italic Latin faces. (A
    narrow_letters pass once stood by to condense Source Han Sans's own
    on the JP side; both Latin donors cover the whole block, it found
    nothing to do on any face, and verify_jp.py holds every Greek and
    Cyrillic letter to one cell, so it went in round 10.)"""
    if not box:
        return 1.0, 0
    ink = box[2] - box[0]
    room = cell - 2 * bearing
    sx = 1.0 if ink <= room else room / ink
    return sx, (cell - ink * sx) / 2 - box[0] * sx


def notdef_to_cell(base, latin, cell):
    """Redraw .notdef from the Latin donor, one cell wide. Returns
    whether it was replaced.

    A terminal allots a column by East Asian Width, not by what the
    font draws, and a codepoint no font in the fallback chain covers is
    almost always Neutral -- one column. Source Han Sans's .notdef is
    full width, so a single uncovered codepoint drew a two-column box
    in a one-column slot and pushed the rest of the line along: in the
    Term faces, 1200 units into a 600-unit cell. That is the one thing
    a terminal font must not do, and it did not take an exotic
    character -- until this build the italic faces reached .notdef for
    ten Greek Extended codepoints their own upright drew.

    The other way round costs nothing: a box narrower than its column
    leaves white, and nothing moves. So the donor's own .notdef, which
    is drawn for this cell, is the one to use.

    Runs before the grid passes and pins the glyph, so neither the
    family's step map nor the Term widening puts it back.
    """
    name = ".notdef"
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    if name not in td.CharStrings or name not in latin.getGlyphOrder():
        return False
    # the vertical origin before the box changes: VORG states it
    # outright, and vmtx says it as a top side bearing off the glyph's
    # own yMax, so a new box has to be paid for on the vmtx side or the
    # two stop agreeing (verify.py checks that they do)
    origin = vmtx_origin(base, name) if "vmtx" in base else None
    private = glyph_private(base, td, name)
    donor = latin.getGlyphSet()
    pen = T2CharStringPen(pen_width(private, cell), donor)
    donor[name].draw(pen)
    cs = pen.getCharString(private=private)
    td.CharStrings[name] = cs
    base["hmtx"].metrics[name] = (cell, charstring_lsb(cs))
    if origin is not None:
        box = charstring_box(cs)
        base["vmtx"].metrics[name] = (base["vmtx"].metrics[name][0],
                                      otRound(origin - (box[3] if box else 0)))
        state_of(base).vorigin.pop(name, None)
    note_redrawn(base, {name: cs})
    pinned = state_of(base).pinned_cell
    pinned.add(name)
    return True


def narrow_halfwidth(font, cell):
    """A character Unicode calls Halfwidth (East_Asian_Width H, taken
    from unicodedata so this and verify.py cannot disagree) is one cell,
    and every terminal's width table gives it one column. Source Han Sans
    aliases
    the halfwidth Hangul letters (U+FFA1-FFDC) to the wide compatibility
    jamo they came from — one 920-unit glyph for U+3131 and U+FFA1
    alike — so putting that glyph on the grid puts both on a full width.
    Each halfwidth codepoint whose glyph is wider than the cell — in
    advance or in ink — gets a one-cell copy of it, condensed, and
    whatever else shares that glyph keeps the original.

    Runs before fit_to_grid, so the scale is Source Han Sans's own
    advance and not the grid step that pass would give it, and before
    widen_fullwidth, which must not widen the copies. A glyph that
    already fits the cell is left for fit_to_grid to centre. A glyph
    the Latin donor supplied is left alone altogether: it is a cell
    wide by construction, and this pass's
    ink-width test is the wrong question for it -- the won sign
    (U+20A9, Halfwidth) came from Source Code Pro Italic with 605 units
    of ink at Bold and 527-581 at the other weights, so Bold Italic
    alone got a condensed copy with zero side bearings, 33 units left of
    where SemiBold Italic draws it, while the Latin face at the same
    weight keeps the donor's glyph as drawn. Returns the number made."""
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    gs = font.getGlyphSet()
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    vdon = vmtx_donor(font)
    built = state_of(font).built
    made, new = {}, {}
    for cp, name in sorted(cmap.items()):
        adv = hmtx[name][0]
        if adv <= 0 or unicodedata.east_asian_width(chr(cp)) != "H":
            continue
        if name in built:
            continue                      # the Latin donor's, already a cell
        box = _bounds(gs, name)
        ink = (box[2] - box[0]) if box else 0
        if adv <= cell and ink <= cell:
            # already fits: fit_to_grid centres it in the cell, and
            # condensing here would only stretch it (Source Han Sans's
            # half-width kana are 500 wide, and 600/500 is a 20% widening
            # of every vertical stroke against untouched horizontals)
            continue
        if name not in made:
            # the copy stays in the source glyph's own FontDict: it is a
            # Hangul jamo, and add_latin_fd would otherwise re-home it
            # with the grafted Latin and hint it against Latin blues
            fd = glyph_fd(font, td, name)
            private = glyph_private(font, td, name)
            # condensed into the cell, not just re-advanced: Source Han
            # Sans's jamo carry 810u of ink in a 920 advance, and moving
            # that into a 600 cell would spill 105u into each neighbour.
            # Scaling by the cell over the advance keeps the design's own
            # bearings in proportion, which is what a half-width form is;
            # over the ink instead where even that would not fit
            sx = min(1.0, cell / max(adv, ink))   # condense, never widen
            # centred in the cell, not scaled about the origin: a source
            # glyph whose ink starts left of zero would otherwise bleed
            # into the cell before it
            dx = (cell - (box[2] - box[0]) * sx) / 2 - box[0] * sx if box else 0
            pen = T2CharStringPen(pen_width(private, cell), gs)
            gs[name].draw(TransformPen(pen, (sx, 0, 0, 1, dx, 0)))
            made[name] = alloc_glyph_name(font)
            append_glyph(font, td, made[name], pen.getCharString(private=private),
                         fd, cell, None, vdon)
            # append_glyph records it in both sets; take it out of the
            # Latin-FontDict one only, so add_latin_fd leaves this copy
            # in the FontDict it came from. It stays in `built`, which is
            # what fit_to_grid reads to know a name is ours
            state_of(font).appended.discard(made[name])
        new[cp] = made[name]
    set_cmap(font, new)
    return len(new)


def repoint_features(font, replaced, tags=("vert", "vrt2")):
    """Source Han Sans's own features substitute FROM the glyphs the
    graft replaced, so once the cmap points at Gengou Code's they never
    fire. Re-point each of `tags` at the grafted glyph, so a vertical run
    still gets the rotated forms of what Gengou Code took over.

    Only the vertical features: 'locl' is on by default, and re-pointing
    it would swap Gengou Code's own design for Source Han Sans's in
    ordinary horizontal text (its JP locale form of '…' is full width).
    Returns the number re-pointed."""
    if "GSUB" not in font:
        return 0
    cmap = font.getBestCmap()
    gsub = font["GSUB"].table
    added = 0
    for tag in tags:
        fmap = feature_map(font, tag)
        pairs = {}
        for cp, old in replaced.items():
            if old not in fmap or cp not in cmap or cmap[cp] == old:
                continue
            src, want = cmap[cp], fmap[old]
            if pairs.setdefault(src, want) != want:
                raise ValueError(
                    f"{tag} for U+{cp:04X} cannot be wired: {src} is shared with "
                    f"another codepoint and already maps to {pairs[src]}, not {want}")
        if not pairs:
            continue
        _add_feature(gsub, tag, [_new_lookup(gsub, otl.buildSingleSubstSubtable(pairs))])
        added += len(pairs)
    if added:
        sort_feature_list(gsub)
    return added


def glyph_bounds(font):
    """{glyph name: (xMin, yMin, xMax, yMax)} for every glyph with ink,
    each drawn once. Drawing a CFF charstring decompiles it, and a
    decompiled charstring is recompiled at save — all 19k of a JP face,
    for a pass that changed nothing — so an untouched glyph gets its
    bytecode back and saves as it was loaded."""
    gs = font.getGlyphSet()
    charstrings = None
    if "CFF " in font:
        charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
    bounds = {}
    for name in font.getGlyphOrder():
        cs = charstrings[name] if charstrings is not None else None
        bytecode = cs.bytecode if cs is not None else None
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        if bytecode is not None:
            cs.bytecode, cs.program = bytecode, None
        if pen.bounds is not None:
            bounds[name] = pen.bounds
    return bounds


def update_bbox(font, bounds=None):
    """Recompute the font's extents from its outlines, in one pass:
    the CFF FontBBox, head's box and the hhea / vhea extents
    (advanceWidthMax, minLeftSideBearing, minRightSideBearing, xMaxExtent
    and their vertical counterparts — fontTools' own hhea.recalc /
    vhea.recalc, from the same bounds). Grafting, widening and rescaling
    all move ink around, and a stale box makes rasterizers clip or
    mis-cache glyphs. Every save of a face in this repo runs with
    TTFont.recalcBBoxes off (fontTools would otherwise draw every glyph
    three more times per save — 7 s of a JP face's 0.3 s save — and
    recompile them all), so this is the one place the extents are set.
    Returns the box, or None for a font with no ink. `bounds` — a
    glyph_bounds() result for this font — skips the pass when the caller
    already has one."""
    if bounds is None:
        bounds = glyph_bounds(font)
    if not bounds:
        return None
    xmin = min(b[0] for b in bounds.values())
    ymin = min(b[1] for b in bounds.values())
    xmax = max(b[2] for b in bounds.values())
    ymax = max(b[3] for b in bounds.values())
    box = [math.floor(xmin), math.floor(ymin), math.ceil(xmax), math.ceil(ymax)]
    # CFF2 (a variable font, build_latin_vf.py) has no FontBBox — head's
    # box is the only one that exists there
    if "CFF2" not in font:
        cff = font["CFF "].cff
        cff[cff.fontNames[0]].FontBBox = box
    head = font["head"]
    head.xMin, head.yMin, head.xMax, head.yMax = box
    if "hmtx" in font and "hhea" in font:
        _update_extents(font["hhea"], font["hmtx"].metrics, bounds, 0,
                        ("advanceWidthMax", "minLeftSideBearing",
                         "minRightSideBearing", "xMaxExtent"))
    if "vmtx" in font and "vhea" in font:
        _update_extents(font["vhea"], font["vmtx"].metrics, bounds, 1,
                        ("advanceHeightMax", "minTopSideBearing",
                         "minBottomSideBearing", "yMaxExtent"))
    return box


def _update_extents(table, metrics, bounds, axis, fields):
    """hhea (axis 0) / vhea (axis 1) extents the way fontTools' recalc
    computes them: the advance max over every glyph, and over the inked
    ones the min side bearing from the metrics table, the min far-side
    bearing and the max extent from the integer-widened outline size."""
    adv_max, min_sb, min_far, max_extent = fields
    setattr(table, adv_max, max(adv for adv, _ in metrics.values()))
    sizes = {name: int(math.ceil(b[2 + axis]) - math.floor(b[axis]))
             for name, b in bounds.items()}
    sb = {name: metrics[name][1] for name in sizes}
    setattr(table, min_sb, min(sb.values()))
    setattr(table, min_far, min(metrics[n][0] - sb[n] - sizes[n] for n in sizes))
    setattr(table, max_extent, max(sb[n] + sizes[n] for n in sizes))


def classify_marks(font, marks):
    """GDEF: the 0-advance combining marks grafted from SCP are class 3
    (Mark). Left as class 1 they are 'zero-width bases' — shapers would
    treat them as letters in their own right (mark-skipping lookups stop
    on them, cursor placement counts them). Only OUR grafted marks are
    touched; Source Han Sans's own classification (U+3099 etc.) stays."""
    if "GDEF" not in font or not marks:
        return
    gdef = font["GDEF"].table
    if gdef.GlyphClassDef is None:
        gdef.GlyphClassDef = otTables.GlyphClassDef()
        gdef.GlyphClassDef.classDefs = {}
    for g in marks:
        gdef.GlyphClassDef.classDefs[g] = 3


def panose_weight(us_weight_class):
    """PANOSE's weight digit for an OS/2 usWeightClass, the mapping
    Source Han Sans itself uses (400 -> 5 Book, 700 -> 8 Bold). The
    verifiers import this rather than repeat it, so a change is one
    edit and the checks stay checks."""
    return us_weight_class // 100 + 1


def set_monospace_metadata(font):
    """Declare the font monospaced, the way HackGen / PlemolJP do for the
    same two-width (3:5 / 1:2) CJK layout: post.isFixedPitch and PANOSE
    proportion 9 are what Windows Terminal's font picker and GDI's
    FIXED_PITCH filter read — Source Han Sans's 0 would hide the fonts
    there. xAvgCharWidth follows OS/2 v3+'s definition (mean of every
    non-zero advance). PANOSE weight is set_names' (the weight is known
    there)."""
    font["post"].isFixedPitch = 1
    font["OS/2"].panose.bProportion = 9
    font["OS/2"].recalcAvgCharWidth(font)


def _bounds(gs, name):
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return pen.bounds


def set_latin_heights(font):
    """OS/2 sxHeight / sCapHeight measured on the face's own 'x' and 'H'.
    Source Han Sans's values described ITS Latin (543 / 733); the 600-cell
    families carry SCP at native size (488 / 655), and CSS font-size-adjust
    or a terminal sizing icons to the cap height would be off by 12%."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    font["OS/2"].sxHeight = round(_bounds(gs, cmap[ord("x")])[3])
    font["OS/2"].sCapHeight = round(_bounds(gs, cmap[ord("H")])[3])


def latin_blue_zones(font):
    """Alignment zones and standard stems for the grafted Latin, measured
    on the final outlines: (BlueValues, OtherBlues, StdHW, StdVW).

    Zones (bottom, top), flat edge paired with the round overshoot:
    baseline 'o'/0, x-height 'x'/'o', cap 'H'/'O', ascender 'd' (flat
    only); OtherBlues: descender 'p' flat / 'g' round. StdHW is the '='
    bar the whole weight pairing is keyed on; StdVW the '|' stem."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()

    def top(ch):
        return _bounds(gs, cmap[ord(ch)])[3]

    def bottom(ch):
        return _bounds(gs, cmap[ord(ch)])[1]

    def zone(a, b):
        a, b = round(a), round(b)
        return (min(a, b), max(a, b))

    zones = sorted([zone(bottom("o"), 0), zone(top("x"), top("o")),
                    zone(top("H"), top("O")), zone(top("d"), top("d"))])
    blues = []
    for b, t in zones:
        if blues and b <= blues[-1] + 1:   # overlapping zones are illegal
            continue
        blues += [b, t]
    other = zone(bottom("g"), bottom("p"))
    bar = _bounds(gs, cmap[ord("|")])
    return (blues, list(other),
            round(bar_thickness(font, cmap[ord("=")])),
            round(bar[2] - bar[0]))


def add_latin_fd(font):
    """Give every glyph we appended its own CID FontDict, a copy of the
    Source Han Sans Latin one with the alignment zones re-measured on OUR
    outlines (latin_blue_zones). Autohinting reads zones from the FD; SHS's
    zones (x-height 543, cap 733) miss SCP's (488 / 655) and the hints
    would snap to nothing. Returns the FD index."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    src = td.FDArray[td.FDSelect[font.getGlyphID(cmap[ord("A")])]]
    fd = copy.deepcopy(src)
    fd.FontName = f"{cff.fontNames[0]}-Latin"
    private = fd.Private
    blues, other, std_hw, std_vw = latin_blue_zones(font)
    for key in ("FamilyBlues", "FamilyOtherBlues", "StemSnapH", "StemSnapV",
                "BlueValues", "OtherBlues", "StdHW", "StdVW"):
        private.rawDict.pop(key, None)
        if key in private.__dict__:
            delattr(private, key)
    private.BlueValues = blues
    private.OtherBlues = other
    private.StdHW = std_hw
    private.StdVW = std_vw
    private.StemSnapH = [std_hw]
    private.StemSnapV = [std_vw]
    td.FDArray.append(fd)
    index = len(td.FDArray) - 1
    state_of(font).latin_fd = index
    # only glyphs append_glyph() created: Source Han Sans's own glyphs also
    # live above CID_ALLOC_START (its CID space is sparse) and call THEIR
    # FD's subroutines, so a CID-range test would corrupt them
    for name in state_of(font).appended:
        td.FDSelect.gidArray[font.getGlyphID(name)] = index
    print(f"  Latin FD {index}: blues {blues} other {other} "
          f"StdHW {std_hw} StdVW {std_vw}")
    return index


def referenced_name_ids(font):
    """Every name ID a table of `font` points at: GSUB/GPOS FeatureParams
    (feature UI names, tooltips, sample text, the named-parameter run),
    STAT (axis and value names, the elided fallback) and fvar (axis and
    instance names). IDs below 256 are the standard slots and are never
    pruned, so they are not listed."""
    used = set()
    for tag in ("GSUB", "GPOS"):
        if tag not in font or font[tag].table.FeatureList is None:
            continue
        for fr in font[tag].table.FeatureList.FeatureRecord:
            params = fr.Feature.FeatureParams
            if params is None:
                continue
            for attr in ("UINameID", "FeatUILabelNameID", "FeatUITooltipTextNameID",
                         "SampleTextNameID", "SubfamilyNameID"):   # the last: 'size'
                used.add(getattr(params, attr, 0))
            first = getattr(params, "FirstParamUILabelNameID", 0)
            used.update(range(first, first + getattr(params, "NumNamedParameters", 0)))
    if "STAT" in font:
        stat = font["STAT"].table
        used.update(ax.AxisNameID for ax in stat.DesignAxisRecord.Axis)
        if stat.AxisValueArray:
            used.update(av.ValueNameID for av in stat.AxisValueArray.AxisValue)
        used.add(getattr(stat, "ElidedFallbackNameID", 0))
    if "fvar" in font:
        used.update(a.axisNameID for a in font["fvar"].axes)
        for inst in font["fvar"].instances:
            used.update((inst.subfamilyNameID, inst.postscriptNameID))
    return {nid for nid in used if nid}


def prune_orphan_names(font):
    """Drop every name record at ID 256 and up that no table refers to
    (referenced_name_ids). The Latin faces inherit Source Code Pro's own
    STAT / fvar strings ('Upright', 'Weight', ...) after the instancer
    drops those tables, and the VF's FeatureParams renumbering leaves the
    old records behind. Returns the IDs removed."""
    used = referenced_name_ids(font)
    orphans = sorted({r.nameID for r in font["name"].names
                      if r.nameID >= 256 and r.nameID not in used})
    for nid in orphans:
        font["name"].removeNames(nameID=nid)
    return orphans


def add_stat(font, weights, italic):
    """STAT: the wght values for `weights` (one weight name for a static
    face — its own value only: a static font listing the whole family's
    values confuses Windows' family model, fontbakery
    multiple-STAT-entries — or every weight for a variable font) from
    WEIGHT_CLASS, plus this file's ital value (0 upright / 1 italic).
    Regular links to Bold and upright to Italic (Format 3, elidable), the
    rest are plain Format 1 — Source Code Pro's own convention."""
    if isinstance(weights, str):
        weights = [weights]
    wght_values = []
    for weight in weights:
        value = {"value": WEIGHT_CLASS[weight], "name": weight}
        if weight == "Regular":
            value.update(flags=0x2, linkedValue=WEIGHT_CLASS["Bold"])
        wght_values.append(value)
    ital_value = ({"value": 1, "name": "Italic"} if italic else
                  {"value": 0, "name": "Regular", "flags": 0x2, "linkedValue": 1})
    axes = [{"tag": "wght", "name": "Weight", "values": wght_values},
            {"tag": "ital", "name": "Italic", "values": [ital_value]}]
    otl.buildStatTable(font, axes, elidedFallbackName="Regular",
                       macNames=False)


def subroutinize_face(path):
    """CFF subroutinization (cffsubr = AFDKO tx). Every charstring we
    generate is flat, and Term regenerates all 17k full-width ones; with
    hints on top the face grew 44%. tx folds the repetition back into
    subroutines — smaller than the v3.2.0 files — and keeps the hints."""
    import cffsubr
    font = TTFont(path)
    font.recalcBBoxes = False   # extents were set by update_bbox; outlines unchanged
    cffsubr.subroutinize(font)
    restore_cid_count(font)
    font.save(path)


def highest_cid(td):
    """The largest CID in a CID-keyed TopDict's charset, or -1."""
    return max((int(n[3:]) for n in td.charset
                if n.startswith("cid") and n[3:].isdigit()), default=-1)


def restore_cid_count(font):
    """A CID-keyed TopDict's CIDCount must cover every CID in the font.
    cffsubr sets it from the LAST charset entry, and Source Han Sans's
    CID space is sparse — the glyphs this build appends sit at the end
    of the order with CIDs from CID_ALLOC_START, well below the 65,497
    the Japanese glyphs reach — so it came out at 25,267 with 9,749
    glyphs above it. A consumer that sizes its CID-to-GID table from
    CIDCount (Adobe's interpreter; a face embedded in a PDF as
    CIDFontType0) resolves every one of those to .notdef. Returns the
    count, or None for a plain CFF."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    if not hasattr(td, "ROS"):      # ROS is what makes a CFF CID-keyed;
        return None                 # CIDCount has a spec default either way
    td.CIDCount = max(td.CIDCount, highest_cid(td) + 1)
    return td.CIDCount


def autohint_face(path, glyph_names):
    """Hint `glyph_names` with AFDKO's otfautohint, in place. The JP
    faces pass the glyphs they (re)drew (note_redrawn): Source Han Sans's
    own hints on untouched glyphs are kept as shipped, so the run is
    seconds rather than the minutes hinting 19,000 glyphs takes. That is
    the grafted Latin, the ligatures, and whatever fit_to_grid and
    widen_fullwidth moved.
    The Latin faces pass every glyph — the instancer drops SCP's hints.
    GENGOU_SKIP_AUTOHINT=1 skips it for quick local iterations."""
    if os.environ.get("GENGOU_SKIP_AUTOHINT"):
        print("  autohint skipped (GENGOU_SKIP_AUTOHINT)")
        return
    if not glyph_names:
        return
    # otfautohint's own entry point, in this process rather than a
    # `python -m afdko.otfautohint` child: its font is opened through
    # autohint.openFont, and that font gets TTFont.recalcBBoxes switched
    # off before it is saved (hints move no outline; update_bbox set the
    # extents; fontTools' recalc would draw every glyph of the face three
    # times over — 7 s a face). The glyph hinting still fans out over
    # otfautohint's own process pool.
    from afdko.otfautohint import autohint
    from afdko.otfautohint.__main__ import get_options

    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "glyphs.txt"
        listing.write_text(",".join(sorted(glyph_names)))
        out = Path(tmp) / path.name
        options, _ = get_options(["--glyphs-file", str(listing),
                                  "-o", str(out), str(path)])
        # get_options configured root logging; otfautohint's own per-glyph
        # warnings are counted below, not printed (as when it was a child
        # process), other libraries' warnings stay visible
        for handler in logging.root.handlers:
            if not any(isinstance(f, _MuteOtfautohint) for f in handler.filters):
                handler.addFilter(_MuteOtfautohint())
        counter = _WarningCounter()
        logger = logging.getLogger("afdko.otfautohint")
        logger.addHandler(counter)
        open_font = autohint.openFont

        def open_without_recalc(font_path, opts):
            data = open_font(font_path, opts)
            data.ttFont.recalcBBoxes = False
            return data

        autohint.openFont = open_without_recalc
        try:
            autohint.hintFiles(options)
        finally:
            autohint.openFont = open_font
            logger.removeHandler(counter)
        if not out.exists():
            raise RuntimeError(f"otfautohint wrote nothing for {path.name}")
        shutil.move(str(out), str(path))
    print(f"  autohint: {len(glyph_names)} glyphs, {counter.count} warnings")


class _MuteOtfautohint(logging.Filter):
    """Drops afdko's records below ERROR from a handler."""

    def filter(self, record):
        return not (record.name.startswith("afdko") and record.levelno < logging.ERROR)


class _WarningCounter(logging.Handler):
    """Counts otfautohint's WARNING+ records (the per-glyph notes it
    used to print to stdout when run as a child process)."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.count = 0

    def emit(self, record):
        self.count += 1


def face_matches(only, weight, face_label, suffix):
    """Command-line filter: words of three kinds — weight names
    ("Regular"), the styles "Italic" / "Upright", and variants ("Term",
    or "base" for the suffix-less family; "" alone is that family too).
    A face matches when, for every kind named, it is one of the words of
    that kind: "Regular" takes Regular and Regular Italic of every
    family, "Light Italic" one face per family, "Light Upright Term"
    exactly one face, "Light Regular base" four (the release workflow
    builds a family's two weights per job). Whole words only, never a
    substring match; a word that is none of these is a variant nobody
    has, so on its own it matches nothing."""
    if only is None:
        return True
    words = only.split()
    if not words:
        return suffix == ""
    weights = {w for w, _ in FACES}
    styles = {"Italic", "Upright"}
    kinds = {"weight": [], "style": [], "variant": []}
    for word in words:
        if word in weights:
            kinds["weight"].append(word)
        elif word in styles:
            kinds["style"].append(word)
        elif word == "base":
            kinds["variant"].append("")
        else:
            kinds["variant"].append(word)
    style = "Italic" if face_label.endswith(" Italic") else "Upright"
    return all(value in named for value, named in
               ((weight, kinds["weight"]), (style, kinds["style"]), (suffix, kinds["variant"]))
               if named)


def env_paths(spec):
    """{name: value} for the path environment variables in `spec`
    ({name: default or None when required}); exits naming every variable
    that is unset or points nowhere. GENGOU_VERSION (not a path) rides
    along as-is."""
    env = {k: os.environ.get(k, d) for k, d in spec.items()}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    env["GENGOU_VERSION"] = os.environ.get("GENGOU_VERSION")
    return env


def run_faces(jobs, worker, label, on_result, pool_from=3):
    """Run `worker` over `jobs`: in-process below `pool_from` jobs (one or
    two faces — a traceback then stays readable), else across a process
    pool. Every failure is collected and reported at the end,
    `label(job)` naming the face, and the run exits non-zero if any face
    failed."""
    failures = []

    def take(job, result):
        try:
            value = result()
        except Exception as exc:
            failures.append((label(job), exc, traceback.format_exception(exc)))
            return
        on_result(job, value)

    if len(jobs) < pool_from:
        for job in jobs:
            take(job, lambda: worker(job))
    else:
        with concurrent.futures.ProcessPoolExecutor() as pool:
            futures = {pool.submit(worker, j): j for j in jobs}
            for fut in concurrent.futures.as_completed(futures):
                take(futures[fut], fut.result)
    if failures:
        for face, exc, tb in failures:
            print(f"FAILED {face}: {exc!r}\n" + "".join(tb), file=sys.stderr)
        sys.exit(f"{len(failures)}/{len(jobs)} faces failed")


def write_face(font, out, hint_glyphs):
    """Save `font` to `out`, then hint `hint_glyphs` (otfautohint) and
    subroutinize the file in place — the tail every static face shares.
    The caller has run update_bbox: the save does not recompute the
    extents (see there)."""
    font.recalcBBoxes = False
    font.save(out)
    autohint_face(out, hint_glyphs)
    subroutinize_face(out)


def build_face(job):
    """Build one output face. Plain data in and out, so it can run in a
    pool worker (unfiltered builds) as well as in-process."""
    suffix, term, weight, shs_file, italic, env, out_dir, steps = job
    face_label = f"{weight}{' Italic' if italic else ''}"
    latin_path = latin_face_path(env["LATIN_DIR"], weight, italic)
    if not latin_path.exists():
        raise FileNotFoundError(f"{latin_path}: run scripts/build_latin.py first")
    latin = TTFont(latin_path)
    base = TTFont(Path(env["SHS_DIR"]) / shs_file)
    n_scp, replaced, default_map, marks = graft_halfwidth(base, latin)
    # before any grid pass, so the Term widening never sees a full-width
    # advance here (see notdef_to_cell)
    notdef_to_cell(base, latin, CELL)
    # the locl forms first: SCP's ccmp composes the Greek breathing
    # marks from them, so they have to exist before that graft runs
    locl_order, locl_where = _locl_lookups(latin["GSUB"].table)
    n_locl = graft_scp_outputs(base, latin, default_map, marks, locl_order)
    # then what ccmp composes, before the variant features are read, so
    # a variant rule on a composed glyph has a glyph to name
    n_ccmp = graft_scp_ccmp(base, latin, default_map, marks)
    variant_maps, variant_names = import_scp_variants(base, latin, default_map, marks)
    copy_line_metrics(base, latin)
    # the outlines' real slant lives in the Latin donor (SCP Italic's)
    ref_angle = (latin["post"].italicAngle or -12.0) if italic else None
    alts = {}
    added = latin_ligatures(base, latin, latin_path, alts, LIGATURES)
    add_gsub(base, added, alts, LIGATURES, variant_maps, variant_names)
    # after add_gsub, which appends to the same LookupList: the copied
    # ccmp lookups' nested lookup indices are absolute, so whatever
    # renumbers the list after this must renumber those too --
    # import_scp_locl (_insert_lookups_first) and prune_orphan_lookups
    # do, drop_features touches the FeatureList only
    n_ccmp += import_scp_ccmp(base, latin, default_map, marks)
    n_locl += import_scp_locl(base, latin, default_map,
                              scripts_with_langsys(base["GSUB"].table))
    classify_marks(base, marks)   # the grafted marks, the variants, ccmp's
    # and where each of them sits: after classify_marks, which is what
    # tells a shaper they are marks at all, and after the ccmp import,
    # whose composed accents the donor positions too
    n_mark = import_scp_marks(base, latin, default_map, marks)
    # and into the lookups Source Han Sans keeps for the accents
    # the graft replaced (the Bopomofo tone marks)
    n_mark += rehome_replaced_marks(base, replaced)
    # the Halfwidth block into one cell first, so its copies are
    # condensed from Source Han Sans's own advance and not from the one
    # the grid pass would give it
    n_half = narrow_halfwidth(base, CELL)
    # then Source Han Sans's proportional leftovers onto the grid — every
    # glyph, so hwid's 500-advance alternates and the locl forms no
    # codepoint reaches come along. It reads no features, so nothing
    # ties it to drop_features below
    n_fit = fit_to_grid(base, CELL, steps=steps)
    # kern would pull Japanese pairs off the cell in any shaper that
    # lays out a run (VS Code, a browser); halt and palt are alternate
    # horizontal metrics, which a fixed cell has no use for. fwid and
    # hwid are the width alternates: an editor applies a feature to the
    # whole buffer and a terminal applies none, so fwid could not give
    # one character its two-cell form without turning every A into Ａ,
    # and nothing could ask for it at all where a terminal draws. Only
    # the features go: their glyphs stay, aalt reaching about a third of
    # the full-width ones and most of the half-width ones, and nothing
    # here prunes a glyph no lookup reaches (Regular: 250 of fwid's 357
    # and 15 of hwid's 115 become such orphans), so the file does not
    # shrink. The
    # vertical features are left alone (the faces keep vmtx/vhea)
    drop_features(base, {"pwid", "palt", "kern", "halt", "fwid", "hwid"})
    freed = prune_orphan_lookups(base)
    if freed:
        print("  lookups no feature reaches any more: "
              + ", ".join(f"{t} {n}" for t, n in sorted(freed.items())))
    n_vert = repoint_features(base, replaced)
    if term:
        # the ligatures are the Latin layer's only multi-cell glyphs, so
        # the only ones an advance test cannot tell from a full width
        widen_fullwidth(base, CELL, skip=set(added.values()) | set(alts.values()))
    # the letters this face has that the Latin face did not: Source Han
    # Sans's full-width Latin (Ａ, on which an accent landed at the
    # cell's right edge) and any letter of the Latin scripts the donor lacks. Fitted
    # from the lookups imported above, as on the Latin face, and last,
    # on the ink every pass before has finished with
    import anchors
    n_loose = anchors.anchor_loose_letters(base)
    # OS/2 Unicode / code-page range bits, from the now-final cmap
    base["OS/2"].recalcUnicodeRanges(base)
    recalc_codepage_range(base)
    set_monospace_metadata(base)
    set_latin_heights(base)
    add_latin_fd(base)
    credits = donor_credits(latin)
    ps = set_names(base, suffix, weight, italic,
                   ref_angle if ref_angle is not None else -12.0,
                   version=env.get("GENGOU_VERSION"), credits=credits)
    add_stat(base, weight, italic)
    prune_orphan_names(base)
    update_bbox(base)
    out = Path(out_dir) / f"{ps}.otf"
    write_face(base, out, state_of(base).redrawn)
    return (f"{face_label}{f' [{suffix}]' if suffix else ''}: "
            f"latin={n_scp} vert={n_vert} "
            f"fitted={n_fit} half={n_half} "
            f"ligs={len(added)} ccmp={n_ccmp} locl={n_locl} mark={n_mark} loose={n_loose} "
            f"-> {out.name}")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = env_paths({"SHS_DIR": None,
                     "LATIN_DIR": str(ROOT / "dist" / "latin")})
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)

    if only is None:
        # a full build must not leave faces from an older roster (e.g. the
        # a weight dropped from FACES) for the release zip to pick up
        stale = sorted(out_dir.glob("GengouCodeJP*.otf"))
        for f in stale:
            f.unlink()
        if stale:
            print(f"removed {len(stale)} stale face(s) from {out_dir}")

    jobs = []
    for suffix, term in VARIANTS.items():
        for weight, shs_file in FACES:
            for italic in (False, True):
                face_label = f"{weight}{' Italic' if italic else ''}"
                if not face_matches(only, weight, face_label, suffix):
                    continue
                jobs.append([suffix, term, weight, shs_file, italic,
                             env, str(out_dir)])
    if not jobs:
        sys.exit(f"no face matches {only!r}")
    # measured once here, not once per pool worker (two whole Source Han
    # Sans faces), and after the filter, so a one-face build pays for it
    # only when there is a face to build
    steps = reference_steps(Path(env["SHS_DIR"]) / REFERENCE_SHS, CELL,
                            Path(env["SHS_DIR"]) / INK_SHS)
    jobs = [tuple(job) + (steps,) for job in jobs]
    run_faces(jobs, build_face,
              label=lambda job: f"{job[2]} [{job[0] or 'base'}]",
              on_result=lambda job, msg: print(msg))


if __name__ == "__main__":
    main()
