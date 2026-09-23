#!/usr/bin/env python3
"""The JP faces' gates (dist/GengouCodeJP*.otf, patched or not):
every ligature fires, == stays untouched, the Term face is its
sibling widened, and the vertical layout is Source Han Sans's own.
Reached through scripts/verify.py, which picks the gate set a font
gets from the font itself."""

import json
import os
import sys
import unicodedata
from pathlib import Path

import pathops
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import anchors  # noqa: E402
import build  # noqa: E402
from build import (  # noqa: E402
    FULLWIDTH,
    MONA_AMBIGUOUS,
    MONA_STANDALONE,
    WEIGHT_CLASS,
    _unwrap,
    _unwrap_pos,
    bar_thickness,
    contour_boxes,
    highest_cid,
    tiling_glyphs,
)
from verifylib import (  # noqa: E402
    FEATURE_SURFACE,
    LATIN_LETTERS,
    WIDE_IN_ONE_CELL,
    Checker,
    check_blank_glyphs,
    check_cases,
    check_cells,
    check_charstring_metrics,
    check_coverage_order,
    check_donor_draws,
    check_donor_letters,
    check_donor_repertoire,
    check_family_cmap,
    check_family_names,
    check_features_work,
    check_font_matrix,
    check_gdef_classes,
    check_gdi_family_name,
    check_heights,
    check_ink_inside,
    check_ligature_cells,
    check_line_metrics,
    check_mark_class_closure,
    check_marks,
    check_monospace_metadata,
    check_name_composition,
    check_name_ids,
    check_nerd_font_icons,
    check_pair_positioning,
    check_private,
    check_stat,
    check_style_bits,
    check_substitution_identity,
    check_tables,
    check_version_stamp,
    check_weight_class,
    check_zones,
    family_reference,
    glyph_has_hint,
    glyph_shape,
    hmtx_mismatches,
    is_italic,
    make_shaper,
    mean_ink_offset,
    weight_name,
)

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "GengouCodeJP-Regular.otf"
)
with open(ROOT / "data" / "mona_ligs.json") as _f:
    LIGATURES = json.load(_f)

# the (usWinAscent, usWinDescent) copy_line_metrics pins on every JP
# face: Source Han Sans's own ascent, and a descent deep enough for the
# Latin layer's box drawing. Read from build so the two cannot drift
WIN_METRICS = build.WIN_METRICS

# what the italic faces genuinely cannot do, so the two checks that
# used to skip themselves on "the italic donor has no Greek/Cyrillic"
# -- true before this build gave them 234 letters from Source Sans --
# can stay live and fail on anything NEW. Both are the same root: the
# second donor's own features are not imported, only its outlines and
# its base anchors. `git show a7c86ec:docs/gengou-plan.md` carries the measurements.
# Keyed by what was MEASURED, not by the probe alone: the language
# check records two quite different failures under one key -- "renders
# the other language's letterform" and "shaped into more than one
# glyph" -- so excusing the key excused either. Injecting a ccmp that
# split the Serbian b into two glyphs, a defect with nothing to do with
# the known one, passed on the italic and failed on the upright. (The
# Greek gaps live with their gate, verifylib.GREEK_ITALIC_GAP.)
LOCL_ITALIC_GAP = {("cyrl", "sr"): "unchanged"}
# where Source Han Sans draws the dakuten and handakuten after a
# half-width kana (the mark's ink, y): measured 652..875 at Regular,
# 655..902 at Bold Italic
VOICING_Y = (620, 940)
# the ASCII punctuation whose full-width vertical form is its Unicode
# vertical presentation form's glyph (check_vertical_forms)
VERTICAL_AS_FULLWIDTH = frozenset(b"()[]{},")

# drawn to tile, so a run of them must show no seam: the full-width low
# line and overline, the wave dash, a quadrant, and the box-drawing and
# block elements a terminal draws frames and bars with
TILING = "\uFF3F\uFFE3\u3030\u25E2\u2500\u2501\u253C\u252C\u2588\u2584"
# ... and the ones that tile DOWN a column: a vertical rule, its heavy
# and double forms, and the full block
VTILING = "\u2502\u2503\u2551\u2588"
# base + combining mark sequences the Latin donor's ccmp composes:
# the dotless i and j, the precomposed g̃, SCP's Vietnamese
# circumflex-breve, and the Cyrillic ї it decomposes first
CCMP_PROBES = (("i", "\u0307"), ("j", "\u0301"), ("g", "\u0303"),
               ("\u00ea", "\u0306"), ("\u0457", "\u0301"))
# the above-base accents an ascender has to clear: grave, acute,
# circumflex, tilde, macron, breve, dot, diaeresis, caron, ring
# (the same ten codepoints as verifylib.CLEAR_MARKS, but in a different
# order: `stacked()` below walks them as ADJACENT cyclic pairs, and its
# calibration against the donor -- "the donor stacks {want}" -- was
# measured on exactly this ordering, so importing CLEAR_MARKS would
# probe a different set of pairs under the same name)
ACCENTS = "\u0300\u0301\u0302\u0303\u0304\u0306\u0307\u0308\u030c\u030a"

# suffix in the base family name -> expected (half-width, full-width) advances
FAMILY_METRICS = {
    "Term": (600, 1200),
}
DEFAULT_METRICS = (600, 1000)

# Unicode calls these Wide, they end up one cell, and neither donor has
# anything wider to offer (README, Gengou Code JP): six emoji only
# Source Code Pro carries at 600, five Bopomofo final letters only Source
# Han Sans carries at 600, and two Hangul tone marks Source Han Sans
# draws 250 wide that fit_to_grid centres in the cell -- verifylib's
# WIDE_IN_ONE_CELL (imported above), which also carries the Nerd Fonts
# ⚡ U+26A1 that a grafted NF face adds to `grafted` below anyway

# the line metrics of an English terminal font: Source Code Pro's, hhea
# and typo alike, with USE_TYPO_METRICS set (build.copy_line_metrics)

# a few ligature sequences (rendered text -> glyph to probe) and CJK
# codepoints, checked for self-intersecting outlines alongside the Latin set
OVERLAP_LIG_SEQS = ["!=", ":=", "->"]
OVERLAP_CJK = "日永"


def family_name(tf):
    name = tf["name"]
    for nid in (16, 1):
        n = name.getDebugName(nid)
        if n:
            return n
    return ""


def subfamily_name(tf):
    name = tf["name"]
    for nid in (17, 2):
        n = name.getDebugName(nid)
        if n:
            return n
    return ""


def expected_metrics(tf):
    fam = family_name(tf)
    # whole-token match: "Term" is a separate word in the family name
    # ("Gengou Code JP Term"), never a substring of another word
    for suffix, pair in FAMILY_METRICS.items():
        if suffix in fam.split(" "):
            return pair
    return DEFAULT_METRICS


def check_vertical_forms(tf, check, shape):
    """'vert' gives the glyph Unicode already encodes for the form: the
    vertical form of a full-width punctuation mark is its <vertical>
    presentation form (U+FE10.., U+FE30..). A substitution re-pointed to
    the wrong glyph of the right width passed every other gate (round 9,
    mutant J5)."""
    cmap = tf.getBestCmap()
    order = tf.getGlyphOrder()
    off, probed = {}, 0
    for cp in list(range(0xFE10, 0xFE1A)) + list(range(0xFE30, 0xFE45)):
        form = unicodedata.decomposition(chr(cp))
        if not form.startswith("<vertical>") or cp not in cmap:
            continue
        base = int(form.split()[1], 16)
        # an ASCII base stands for its full-width form -- the brackets
        # and the comma, whose vertical glyph Source Han Sans shares
        # with the presentation form; ：；！？ and the wavy low line
        # take rotated forms of their own and are not asked
        if base in VERTICAL_AS_FULLWIDTH:
            base = 0xFF01 + base - 0x21
        elif base < 0x3000:
            continue
        if base not in cmap:
            continue
        infos, _ = shape(chr(base), {"vert": True})
        probed += 1
        if len(infos) != 1 or order[infos[0].codepoint] != cmap[cp]:
            off[chr(base)] = "vert"
    check(probed and not off, f"vert gives the encoded forms "
                              f"({probed} probed; off: {off})")


# how far a glyph's shape may drift from the donor's: measured 2e-12
# on every kana and ideograph of all twenty JP and Term faces
_DONOR_SHAPE = 1e-6

VORG_DEFAULT = 880    # Source Han Sans's vertical origin, kept as is


# the kana and the ideographs, which the build takes from the donor
# as drawn (the Term face moves them, and moving is invisible to
# glyph_shape) -- 13,944 characters of a JP face
DONOR_AS_DRAWN = ((0x3040, 0x30FF), (0x31F0, 0x31FF), (0x3400, 0x4DBF),
                  (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x2FFFF))


def source_han_sans(tf, check):
    """This face's own Source Han Sans weight, opened, or None -- with
    the gate that says SHS_DIR has to name it."""
    from fontTools.ttLib import TTFont
    weight = weight_name(subfamily_name(tf))
    donor = dict(build.FACES).get(weight)
    root = os.environ.get("SHS_DIR")
    path = Path(root) / donor if root and donor else None
    if not check(bool(path and path.is_file()),
                 f"SHS_DIR points at Source Han Sans ({donor} for {weight})"):
        return None
    return TTFont(str(path))


def check_donor_shapes(tf, check):
    """Every kana and every ideograph is drawn the way Source Han Sans
    draws it -- four fifths of the font, and nothing read a single one
    of those outlines before.

    Held by glyph_shape, which divides out size and position, so the
    Term face's 100-unit shift and any refitting are invisible and the
    comparison is exact: 13,944 characters on all twenty JP and Term
    faces, worst difference 2e-12. A kana mirrored inside its own box
    keeps its advance, its bounding box, its ink area and its cmap
    entry, so every other gate passes it (round 12, mutant W3); this
    reads 1.03."""
    theirs = source_han_sans(tf, check)
    if theirs is None:
        return
    cmap, their_cmap = tf.getBestCmap(), theirs.getBestCmap()
    gs, their_gs = tf.getGlyphSet(), theirs.getGlyphSet()
    off, n = {}, 0
    for cp, g in sorted(cmap.items()):
        if cp not in their_cmap or not any(lo <= cp <= hi for lo, hi in DONOR_AS_DRAWN):
            continue
        mine, theirs_shape = glyph_shape(gs, g), glyph_shape(their_gs, their_cmap[cp])
        if mine is None or theirs_shape is None:
            continue
        n += 1
        drift = max(abs(a - b) for a, b in zip(mine, theirs_shape))
        if drift > _DONOR_SHAPE:
            off[chr(cp)] = round(drift, 4)
    check(n and not off, f"every kana and ideograph is drawn as Source Han Sans draws it "
                         f"({n} characters; off: {dict(list(off.items())[:5])})")


def check_vertical_origins(tf, check, full):
    """Every vertical origin is Source Han Sans's own. The build copies
    VORG across and writes the default for the glyphs it appends, so
    the donor is the answer for every record; without it the gate reads
    each glyph's origin against itself, and 620 instead of 880 on ○ ■
    〇 ￥ moved them 3 px up their column with every gate passing
    (round 11, mutant B1b). The kana and the ideographs have a rule of
    their own below -- they keep the default -- which is a third of the
    repertoire; this is the rest of what the donor draws full width
    (15,778 characters of a JP face).

    Source Han Sans is required, as the Symbols font is for a Nerd Font
    face: a donor-less run would be a gate that reads nothing."""
    theirs = source_han_sans(tf, check)
    if theirs is None:
        return
    their_vorg, their_cmap = theirs["VORG"], theirs.getBestCmap()
    ours, cmap = tf["VORG"], tf.getBestCmap()
    # and while the donor is open: it is a floor under the JP families
    # the way Source Code Pro is under the Latin layer (16,742
    # codepoints, all 40 JP faces cover them). check_family_cmap cannot
    # see this -- a family's own reference face is compared with
    # nothing, and its siblings still contain the reduced reference --
    # so 356 kanji deleted from GengouCodeJP-Regular passed every gate
    # (round 12, mutant F1); they would draw .notdef boxes at the
    # half-width advance, moving the column as well
    missing = sorted(set(their_cmap) - set(cmap))
    check(not missing, f"every character Source Han Sans draws, this face draws "
                       f"({len(their_cmap)} codepoints; missing {len(missing)}: "
                       f"{[hex(cp) for cp in missing[:5]]})")
    check(ours.defaultVertOriginY == their_vorg.defaultVertOriginY,
          f"the default vertical origin is the donor's "
          f"({ours.defaultVertOriginY} vs {their_vorg.defaultVertOriginY})")
    hmtx, their_hmtx = tf["hmtx"].metrics, theirs["hmtx"].metrics
    off, n = {}, 0
    for cp, g in sorted(cmap.items()):
        theirs_g = their_cmap.get(cp)
        if theirs_g is None:
            continue                  # ours: the Latin layer has no vertical design
        # and only where both draw the character full width: where the
        # Latin layer supplies it (Ω, ‰, ℅ ...) ours is a cell wide and
        # takes the default origin, which is not the donor's business
        if hmtx[g][0] != full or their_hmtx[theirs_g][0] != theirs["head"].unitsPerEm:
            continue
        n += 1
        mine = ours.VOriginRecords.get(g, ours.defaultVertOriginY)
        want = their_vorg.VOriginRecords.get(theirs_g, their_vorg.defaultVertOriginY)
        if mine != want:
            off[chr(cp)] = (mine, want)
    check(n and not off, f"every vertical origin is the donor's ({n} characters; "
                         f"off: {dict(list(off.items())[:4])})")


def check_vertical_layout(tf, check, shape, full):
    """Vertical text is the grid too: every full-width character shaped
    top-to-bottom advances one em, centred on the column (x offset
    -half the width) from its own vertical origin, alone and in a pair;
    and the default origin is Source Han Sans's. A vertical kern, a
    placement under 'vert' and a lowered origin all passed (round 10,
    mutants J20, J21, J42)."""
    cmap = tf.getBestCmap()
    order = tf.getGlyphOrder()
    hmtx = tf["hmtx"].metrics
    vorg = tf["VORG"]
    em = tf["head"].unitsPerEm
    check_vertical_origins(tf, check, full)
    check_donor_shapes(tf, check)
    check(vorg.defaultVertOriginY == VORG_DEFAULT,
          f"VORG default {vorg.defaultVertOriginY} (want {VORG_DEFAULT})")
    # (the two-em repeat marks 〱〲 and the Bopomofo letters, which
    # Source Han Sans sets on their own vertical metrics, are not asked)
    wide = [chr(cp) for cp, g in sorted(cmap.items()) if hmtx[g][0] == full
            and cp not in (0x3031, 0x3032) and cp not in anchors.BOPOMOFO]

    def place(text):
        infos, positions = shape(text, {}, script="Hani", language="ja", direction="ttb")
        out = []
        for info, pos in zip(infos, positions):
            g = order[info.codepoint]
            origin = vorg.VOriginRecords.get(g, vorg.defaultVertOriginY)
            out.append((pos.x_offset, pos.y_offset, pos.y_advance) == (-full // 2, -origin, -em))
        return out

    off = [ch for ch in wide if not all(place(ch))]
    kana = [ch for ch in wide if 0x3041 <= ord(ch) <= 0x30FF]
    pairs = sum(1 for a in kana for b in kana[::7] if not all(place(a + b)))
    check(wide and not off and not pairs,
          f"vertical text is the grid ({len(wide)} full-width characters, "
          f"{len(kana) * len(kana[::7])} kana pairs; off: {off[:5]}, pairs off: {pairs})")


def check_term_sibling(tf, check, full):
    """A Term face is its JP sibling with every kana and ideograph moved
    half the extra width to the right, and every half-width glyph drawn
    the same: held glyph by glyph against the sibling built beside it,
    when it is there (CI builds both). One kanji left at its 1000 width
    in the 1200 cell passed every gate (round 9, mutant J11). The
    symbols are not modelled -- a rule is extended to tile, a dashed
    line stretched, a wide numeral refitted -- and are left to the
    general gates."""
    from fontTools.ttLib import TTFont
    name = FONT.name
    if "Term" not in name:
        return
    sibling = FONT.with_name(name.replace("Term", "", 1))
    if not sibling.exists():
        # "skip", not "ok": a gate that did not run must not read as
        # green on a dashboard (round 11)
        check(None, "Term against its JP sibling: no sibling beside the face")
        return
    jp = TTFont(str(sibling))
    jp_full = expected_metrics(jp)[1]
    shift = (full - jp_full) / 2
    gs, jp_gs = tf.getGlyphSet(), jp.getGlyphSet()
    jp_hmtx = jp["hmtx"].metrics
    cmap, jp_cmap = tf.getBestCmap(), jp.getBestCmap()
    off, n = {}, 0
    for cp, g in cmap.items():
        theirs = jp_cmap.get(cp)
        if theirs is None:
            off[chr(cp)] = "not in the sibling"
            continue
        wide = jp_hmtx[theirs][0] == jp_full
        if wide and not (0x3041 <= cp <= 0x30FF or 0x4E00 <= cp <= 0x9FFF):
            continue
        if not wide and jp_hmtx[theirs][0] != build.CELL:
            continue            # a zero-advance mark or a multi-em dash
        box, jp_box = build._bounds(gs, g), build._bounds(jp_gs, theirs)
        if box is None or jp_box is None:
            if (box is None) != (jp_box is None):
                off[chr(cp)] = "drawn in one"
            continue
        n += 1
        dx = shift if wide else 0
        want = (jp_box[0] + dx, jp_box[1], jp_box[2] + dx, jp_box[3])
        if any(abs(a - b) > 1 for a, b in zip(box, want)):
            off[chr(cp)] = (tuple(round(v) for v in box), tuple(round(v) for v in want))
    check(n and not off, f"the Term face is its JP sibling, the kana and ideographs {shift:g} over "
                         f"({n} glyphs; off: {dict(list(off.items())[:4])})")


class Face:
    """The face every gate below reads, opened once, with what they all
    need measured once: its advances, its outlines' boxes, a shaper.
    main() used to hold these as locals across 1,400 lines, and each
    gate there could read any of the others' as well."""

    def __init__(self, path):
        self.tf = tf = TTFont(str(path))
        self.cmap = cmap = tf.getBestCmap()
        self.hmtx = hmtx = tf["hmtx"]
        self.hhea = tf["hhea"]
        self.a_adv = hmtx[cmap[ord("a")]][0] if ord("a") in cmap else 0
        self.cjk_adv = hmtx[cmap[0x65E5]][0] if 0x65E5 in cmap else 0
        self.fam = family_name(tf)
        self.sub = subfamily_name(tf)
        self.italic = is_italic(tf)
        self.exp_half, self.exp_full = expected_metrics(tf)
        self.order = tf.getGlyphOrder()
        self.gs = tf.getGlyphSet()
        self.tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
        # bounds holds the glyphs that draw: hmtx_mismatches skips a blank one
        self.widths, self.bearings, self.bounds = hmtx_mismatches(tf)
        self.shape = make_shaper(path)


# the two double-span marks straddle the pair they join: Source
# Code Pro pulls them half a cell left in GPOS, and dropping that
# with the advance beside it centred the tie on the first letter —
# or, with no placement at all, 154 units left of where the line
# starts
def placed(face, text, feats=None):
    """[(xMin, xMax), ...] where a run's ink actually lands: the
    pen's own advance, plus what GPOS moves each glyph by."""
    infos, positions = face.shape(text, feats or {})
    out, pen_x = [], 0
    for info, pos in zip(infos, positions):
        ink = build._bounds(face.gs, face.order[info.codepoint])
        out.append(None if ink is None else
                   (ink[0] + pen_x + pos.x_offset,
                    ink[2] + pen_x + pos.x_offset))
        pen_x += pos.x_advance
    return out


def y_rows(face, gname):
    """(yMin, yMax) of each contour of `gname`, bottom first."""
    return sorted((round(b[1]), round(b[3])) for b in contour_boxes(face.tf, gname))


def lig_glyph(face, text):
    """The ligature glyph "a <op> b" shapes its operator into."""
    infos, _ = face.shape(text, {"calt": True, "liga": True})
    return face.order[infos[2].codepoint]


def ink_overlap(face, text):
    """The ink two shaped glyphs share, in square units (0 unless
    `text` shapes to exactly two)."""
    paths, pen_x = [], 0
    infos, positions = face.shape(text, {})
    if len(infos) != 2:
        return 0
    for info, pos in zip(infos, positions):
        path = pathops.Path()
        face.gs[face.order[info.codepoint]].draw(path.getPen())
        moved = pathops.Path()
        path.draw(TransformPen(moved.getPen(),
                               (1, 0, 0, 1, pen_x + pos.x_offset, pos.y_offset)))
        paths.append(moved)
        pen_x += pos.x_advance
    return abs(pathops.op(paths[0], paths[1], pathops.PathOp.INTERSECTION).area)


def check_advances(face, check):
    a_adv, cjk_adv, fam, italic, exp_half, exp_full = (
        face.a_adv, face.cjk_adv, face.fam, face.italic, face.exp_half, face.exp_full)
    ratio = f"{cjk_adv / a_adv:.3f}" if a_adv else "?"
    print(f"family={fam!r} italic={italic} half={a_adv} full={cjk_adv} ratio={ratio}")
    check((a_adv, cjk_adv) == (exp_half, exp_full),
          f"(half, full) == ({exp_half}, {exp_full}) for family {fam!r}, "
          f"got ({a_adv}, {cjk_adv})")


def check_width_policy(face, check):
    cmap, hmtx, exp_half, exp_full = face.cmap, face.hmtx, face.exp_half, face.exp_full
    # every codepoint Gengou Code has is one cell in both families — the
    # ligature-paired arrows and operators, Greek, box drawing, SCP-only
    # Latin (ł ğ ₽), '−' — and Source Han Sans's own full-width symbols
    # (① ※) stay two cells. The italic faces' Greek comes from Source
    # Sans (build_latin.add_missing_from_sans), a cell wide by
    # construction like the upright's from Source Code Pro
    policy = {"\u2192": exp_half, "\u2026": exp_half, "\u2500": exp_half,
              "\u2212": exp_half, "\u2460": exp_full, "\u203b": exp_full,
              "\u0142": exp_half, "\u011f": exp_half, "\u20bd": exp_half}
    policy["\u03b1"] = policy["\u03c2"] = exp_half
    # half-width kana and the half-width symbols (￩ U+FFE9): Source Han
    # Sans's 500 centred in the cell (fit_to_grid)
    policy["\uff71"] = policy["\uffe9"] = exp_half
    off_policy = {}
    for ch, want in policy.items():
        g = cmap.get(ord(ch))
        got = hmtx[g][0] if g else None           # a donor that dropped it
        if got != want:
            off_policy[ch] = got
    check(not off_policy, f"width policy ({len(policy)} probes; off: {off_policy})")


def check_greek_cyrillic_cells(face, check):
    cmap, hmtx, exp_half = face.cmap, face.hmtx, face.exp_half
    # and every Greek and Cyrillic letter, whichever donor drew it:
    # both scripts are East_Asian_Width A, so every terminal
    # allots them one column, and a full width would paint over the
    # next character
    greek_cyrillic = {cp: hmtx[g][0] for cp, g in cmap.items()
                      if 0x370 <= cp <= 0x4FF}
    full = {cp for cp, adv in greek_cyrillic.items() if adv != exp_half}
    check(not full, f"every Greek and Cyrillic letter is one cell "
                    f"({len(greek_cyrillic)} of them; off: "
                    f"{sorted(hex(c) for c in full)})")


def check_pinned_wide(face, check):
    cmap = face.cmap
    # the exception to the policy: characters both donors draw one cell
    # wide although Unicode calls them Wide, so a terminal reserves two
    # columns and the glyph sits in the left one. check_widths_by_class
    # asks both directions of it character by character -- a Wide
    # character at one cell that is not in the set fails there, and a
    # member of the set at full width fails there too -- so all that is
    # left to ask here is that the set is still in the cmap at all,
    # which nothing walking the cmap can see (round 12). U+26A1 reaches
    # a face only through the Nerd Fonts graft, so it is not asked of
    # one that has not been patched
    pinned = WIDE_IN_ONE_CELL - {0x26A1}
    gone = sorted(hex(cp) for cp in pinned - set(cmap))
    check(not gone, f"the {len(pinned)} pinned East-Asian-Wide characters are "
                    f"still mapped (gone: {gone})")


def check_advance_grid(face, check):
    hmtx, exp_half, exp_full = face.hmtx, face.exp_half, face.exp_full
    # nothing anywhere in the font is off the grid, cmap'd or not: a
    # feature on by default (locl, ccmp) can put a glyph on the page
    # that no codepoint reaches (fit_to_grid). Not verifylib.check_grid
    # (a single cell's whole multiples): the default (non-Term) family
    # pairs a 600-unit half cell with a 1000-unit full one, and 1000 is
    # no multiple of 600, so a glyph on the grid has to clear either
    # modulus, not one fixed cell's
    off_grid = sorted(name for name, (adv, _lsb) in hmtx.metrics.items()
                      if adv > 0 and adv % exp_half and adv % exp_full)
    check(not off_grid,
          f"every advance in the font is on the grid ({len(hmtx.metrics)} glyphs; "
          f"off: {[(n, hmtx[n][0]) for n in off_grid[:5]]})")


def check_names(face, check):
    tf, exp_full = face.tf, face.exp_full
    # the names the face ships under -- GengouCodeJP.zip carries these
    # faces. The family pair and the weight are verifylib's
    # (check_family_names, check_weight_class)
    term = exp_full > 1000
    is_nf = check_family_names(tf, check, "Gengou Code JP" + (" Term" if term else ""),
                       "GengouCodeJP" + ("Term" if term else ""))
    n0 = tf["name"].getDebugName(0) or ""
    for donor in ("Source Han Sans", "Source Code Pro", "Monaspace"):
        check(donor in n0, f"nameID 0 credits {donor}")
    check_name_ids(tf, check, (1, 2, 3, 4, 5, 6, 8, 9, 11, 13, 14, 16, 17))
    # the version the face is stamped with, against the one the build
    # was asked for: one dist/ with two versions in it passed every
    # gate, and a release step that misses GENGOU_VERSION makes exactly
    # that
    check_version_stamp(tf, check, unique_id=True)
    check_weight_class(tf, check, face.sub)
    return is_nf


def check_jp_tables(face, check):
    tf, cmap, hmtx, bounds = face.tf, face.cmap, face.hmtx, face.bounds
    check_tables(tf, check, bounds, hmtx, cmap)
    # the tables a JP face is not a JP face without. Both sets were
    # behind an `if`: deleting vhea, vmtx and VORG dropped five checks
    # and passed, and the STAT table the grafts are built to preserve
    # was read by nothing at all
    for tag in ("DSIG",):
        # Source Han Sans ships one; a signature no longer
        # matches the file the build rewrote
        check(tag not in tf, f"no {tag} table")
    for tag in ("vhea", "vmtx", "VORG", "STAT", "GDEF"):
        check(tag in tf, f"the face carries {tag}")
    ivs = [t for t in tf["cmap"].tables if t.format == 14]
    named = {g for t in ivs for sel in t.uvsDict.values()
             for _cp, g in sel if g}
    check(ivs and named <= set(tf.getGlyphOrder()),
          f"the variation-sequence cmap is there and names glyphs the "
          f"face has ({len(named)} glyphs over "
          f"{sum(len(t.uvsDict) for t in ivs)} selectors)")
    cff_top = tf["CFF "].cff[tf["CFF "].cff.fontNames[0]]
    check(hasattr(cff_top, "ROS"),
          "the face is still CID-keyed (CFF ROS)")
    check_stat(tf, check, weight_name(subfamily_name(tf)), is_italic(tf))
    # vhea's extents as well as hhea's: the same pass writes both
    if "vhea" in tf and "vmtx" in tf:
        vhea, vmtx = tf["vhea"], tf["vmtx"].metrics
        heights = [vmtx[n][0] for n in tf.getGlyphOrder()]
        tops = [vmtx[n][1] for n in bounds]
        bottoms = [vmtx[n][0] - vmtx[n][1] - (b[3] - b[1])
                   for n, b in bounds.items()]
        for label, got, want in (
                ("advanceHeightMax", vhea.advanceHeightMax, max(heights)),
                ("minTopSideBearing", vhea.minTopSideBearing, min(tops)),
                ("minBottomSideBearing", vhea.minBottomSideBearing,
                 min(bottoms)),
                ("yMaxExtent", vhea.yMaxExtent,
                 max(t + (b[3] - b[1]) for t, b in zip(tops, bounds.values())))):
            check(abs(got - want) <= 1,
                  f"vhea {label} is the outlines' ({got} vs {round(want)})")


def check_ink_placement(face, check):
    cmap, hmtx, exp_half, bounds = face.cmap, face.hmtx, face.exp_half, face.bounds
    # and nothing paints a whole cell past its own advance: an italic
    # overhangs by design (up to 138u in the Latin layer), a glyph put on
    # a step too small for its ink would not (grid_step). The boxes are
    # the pass above's, not a second one
    check_ink_inside(check, bounds, hmtx, cmap, exp_half)

    # and, for the glyphs that fill their advance, WHERE inside it: the
    # bound above is half a cell, which a quarter-cell mistranslation
    # slips under (every kanji moved 250u right passed it, and in Term a
    # kanji flush against the right edge of its 1200 did too). One
    # radical (氵) is drawn 278u off centre by design, so no single glyph
    # is held to a bound; the MEAN over all of them is, and it sits
    # within 2u of the advance centre for kanji and 8u for kana (spacing
    # glyphs; +5.6 Bold to +7.3 Light). A pass that shifts the layer
    # moves the mean with it
    # (spacing glyphs only: a combining mark such as ゛゜ U+3099/309A has
    # no advance to be centred in, and its -360u would pull the mean.)
    # And the Latin layer's letters and digits the same way: asked only
    # of the Latin statics before, which no longer ship, so a uniform
    # 100u shift of the layer -- under the per-glyph band of
    # check_glyph_placement -- would have reached the JP faces
    def advance(name):
        return hmtx[name][0]

    centred = {"kanji": mean_ink_offset(bounds, advance, cmap, ((0x4E00, 0x9FFF),)),
               "kana": mean_ink_offset(bounds, advance, cmap, ((0x3041, 0x30FF),)),
               "latin": mean_ink_offset(bounds, advance, cmap, LATIN_LETTERS)}
    check(all(v is not None and abs(v) <= 25 for v in centred.values()),
          f"every layer is centred in its advance (mean ink-centre offset "
          f"{', '.join(f'{k} {v:+.1f}u' if v is not None else f'{k} none' for k, v in centred.items())}; "
          f"bound 25u)")


def check_repertoire_draws(face, check):
    cmap, bounds = face.cmap, face.bounds
    # the repertoire, and DRAWN, not merely mapped: nothing here counted
    # what the face covers, so one that lost 25,000 cmap entries — or
    # kept every one of them and emptied the outlines — was a
    # well-formed, correctly named, correctly sized asset that rendered
    # all Japanese as whitespace and passed every gate. `bounds` holds
    # the glyphs that draw (hmtx_mismatches skips a blank one), so this
    # counts ink. The face maps 17,355 codepoints — Source Han Sans
    # JP's 16,742 and Gengou Code's 1,335 — 12,746 of them kanji in the
    # unified block; the floors sit well under that, because a subset that
    # shrank on purpose is a decision and one that shrank by accident is
    # this
    def drawn(lo, hi):
        return sum(1 for cp, g in cmap.items() if lo <= cp <= hi and g in bounds)

    kanji, kana = drawn(0x4E00, 0x9FFF), drawn(0x3040, 0x30FF)
    latin = drawn(0x0041, 0x007A)
    check(len(cmap) >= 15000 and kanji >= 10000 and kana >= 150 and latin >= 50,
          f"the Japanese repertoire is there and draws ({len(cmap)} "
          f"codepoints; {kanji} kanji, {kana} kana, {latin} Latin with ink)")
    # and the Latin layer, letter by letter
    check_donor_draws(check, cmap, set(bounds))


def check_vertical_metrics(face, check):
    tf, cmap, hmtx, bounds = face.tf, face.cmap, face.hmtx, face.bounds
    # the vertical origin, stated twice: CFF gives it outright in VORG,
    # and vmtx gives it as a bearing DOWN from each glyph's own yMax.
    # They must agree, or a vertical run sits at one height under a
    # shaper that reads VORG (HarfBuzz, CoreText, DirectWrite) and
    # another under one that reads vmtx (FreeType's vertical layout,
    # which has no VORG at all). Every glyph this build appended used to
    # inherit its donor's bearing verbatim, and stood 250-570 units low
    if "vmtx" in tf and "VORG" in tf:
        vorg = tf["VORG"]
        vmtx = tf["vmtx"].metrics
        off = [(name, round(box[3] + vmtx[name][1]),
                vorg.VOriginRecords.get(name, vorg.defaultVertOriginY))
               for name, box in bounds.items() if name in vmtx]
        # within 2 units: yMax here is a BoundsPen reading of the curve,
        # and the font's own is the rounded design value
        off = [row for row in off if abs(row[1] - row[2]) > 2]
        check(not off, f"vmtx and VORG agree on the vertical origin "
                       f"({len(off)} off, e.g. {off[:3]})")
        # and the column itself: every glyph with a horizontal advance
        # is one em tall in vertical text, and an ideograph or kana
        # keeps Source Han Sans's default origin -- the ones it moves
        # are its full-width forms and symbols. A vertical advance of
        # 1500 on one kanji, or its origin 300 down, passed (round 9,
        # mutants J3, J3b)
        em = tf["head"].unitsPerEm
        # the vertical kana repeat marks 〱〲 are two em tall by design
        tall = {chr(cp): vmtx[g][0] for cp, g in cmap.items()
                if g in vmtx and hmtx[g][0] > 0 and cp not in (0x3031, 0x3032)
                and vmtx[g][0] != em}
        moved = {cp: vorg.VOriginRecords[g] for cp, g in cmap.items()
                 if g in vorg.VOriginRecords
                 and (0x3040 <= cp <= 0x30FF or 0x4E00 <= cp <= 0x9FFF)}
        check(not tall, f"every glyph with an advance is one em tall in "
                        f"vertical text ({len(tall)} off, e.g. {list(tall.items())[:3]})")
        check(not moved, f"no kana or ideograph moves its vertical origin "
                         f"({len(moved)} off, e.g. {list(moved.items())[:3]})")


def check_hints(face, check):
    tf, cmap, shape_infos = face.tf, face.cmap, face.shape
    # the hinting the build spends a minute a face on: nothing here read
    # it, and a face whose autohint pass silently did nothing — which is
    # what an empty BuildState.redrawn produces — passed every check
    hint_td = tf["CFF "].cff[tf["CFF "].cff.fontNames[0]]
    unhinted = []
    for ch in "HAx=":
        name_ = cmap.get(ord(ch))
        if name_ and not glyph_has_hint(hint_td.CharStrings[name_]):
            unhinted.append(ch)
    for text in ("a != b", "a -> b"):     # a ligature this build drew
        infos, _p = shape_infos(text, {"calt": True, "liga": True})
        if len(infos) > 4:
            name_ = tf.getGlyphOrder()[infos[2].codepoint]
            if not glyph_has_hint(hint_td.CharStrings[name_]):
                unhinted.append(text.strip("ab "))
    check(not unhinted, f"the glyphs this build redrew carry hints "
                        f"(unhinted: {unhinted})")
    # and the zones they are hinted AGAINST. add_latin_fd gives the
    # grafted Latin its own FontDict and latin_blue_zones measures the
    # face's own x-height and cap; swapping in Source Han Sans's
    # (540/733 against an actual 486/656) snaps every stem to the wrong
    # place at small sizes, and nothing read the Private dict
    check_zones(tf, check, cmap)


def check_cid_count(face, check):
    tf = face.tf
    # a CID-keyed font's CIDCount must cover every CID it uses: cffsubr
    # takes it from the last charset entry, and Source Han Sans's space
    # is sparse (build.restore_cid_count)
    cff = tf["CFF "].cff
    td = cff[cff.fontNames[0]]
    if hasattr(td, "ROS"):      # ROS is what makes a CFF CID-keyed
        top = highest_cid(td)
        check(td.CIDCount > top,
              f"CFF CIDCount {td.CIDCount} covers every CID (highest {top})")


def check_feature_set(face, check):
    tf, exp_full, shape_infos, tags = face.tf, face.exp_full, face.shape, face.tags
    # nothing may move a glyph off the horizontal cell: 'kern' is on by
    # default in every horizontal shaper and Source Han Sans kerns あ+て
    # 20u tighter than the cell; 'halt' and 'palt' are alternate
    # horizontal metrics (drop_features). The vertical features stay
    gpos = {fr.FeatureTag for fr in tf["GPOS"].table.FeatureList.FeatureRecord} \
        if "GPOS" in tf else set()
    for tag in ("kern", "halt", "palt"):
        check(tag not in gpos, f"GPOS has no {tag} ({sorted(gpos)})")
    # ... and the donor's own mark positioning is there: 'mark' puts an
    # accent on the letter, 'mkmk' stacks a second on the first, 'ccmp'
    # lifts the tie bar over an ascender (build.import_scp_marks)
    for tag in ("mark", "mkmk", "ccmp"):
        check(tag in gpos, f"GPOS carries {tag} ({sorted(gpos)})")
    # vert must still reach the characters that need it: Source Han
    # Sans's own lookups substitute FROM the glyphs the graft replaced
    # (build.repoint_features), so a missing re-point looks exactly like
    # a working feature from the outside
    vert_off = []
    for tag in ("vert", "vrt2"):   # repoint_features re-points both
        for ch in "「、ー…":     # Source Han Sans rotates these; not — or “
            infos, _p = shape_infos(ch, {})
            rot, _p = shape_infos(ch, {tag: True})
            if not infos or not rot or infos[0].codepoint == rot[0].codepoint:
                vert_off.append((tag, ch))
    check({"vert", "vrt2"} <= tags and not vert_off,
          f"vert and vrt2 reach the characters that rotate (off: {vert_off})")
    # and the rest of what the build keeps: dropping a feature outright
    # looked the same as a working one from the outside
    for tag in ("fwid", "hwid"):
        check(tag not in tags, f"GSUB has no {tag}")
    for tag in ("aalt", "dlig", "ruby",
                "jp78", "jp83", "jp90", "nlck", "locl", "ccmp") + FEATURE_SURFACE:
        check(tag in tags, f"GSUB carries {tag}")
    for tag in ("vkrn", "vhal", "vpal"):
        check(tag in gpos, f"GPOS carries {tag} ({sorted(gpos)})")
    for text, want in (("あて", exp_full), ("いて", exp_full)):
        _infos, positions = shape_infos(text, {})
        check(positions[0].x_advance == want,
              f"{text!r} shapes on the grid ({positions[0].x_advance}u, want {want})")


def check_cv11(face, check):
    # a combining mark's variant (cv11: the Cyrillic breve for U+0306, in
    # the upright faces) must stay a 0-advance mark, not become a spacing
    # glyph that takes a cell when selected
    shape_infos = face.shape
    tags = face.tags
    if "cv11" in tags:
        # 'x' + U+0306 has no precomposed form, so HarfBuzz cannot fold
        # the pair into one glyph ('a' + U+0306 becomes U+0103 ă)
        mark_gids = []
        for feats in ({}, {"cv11": True}):
            infos, positions = shape_infos("x\u0306", feats)
            ok = len(infos) == 2 and positions[1].x_advance == 0
            check(ok, f"U+0306 with {feats or 'defaults'}: {len(infos)} glyphs, mark advance "
                      f"{positions[1].x_advance if len(positions) > 1 else '?'} (want 2, 0)")
            mark_gids.append(infos[1].codepoint if len(infos) > 1 else None)
        check(None not in mark_gids and mark_gids[0] != mark_gids[1],
              "cv11 swaps the combining breve")


def check_standalone_operators(face, check):
    cmap = face.cmap
    # standalone operators redrawn from Monaspace must match the ligatures
    # cut from the same instance: every contour of the lone glyph has a
    # counterpart in the ligature at the same y extent (ligatures span
    # more cells, so only y is comparable). '==' '<<' '>>' '||' '..' '!!'
    # ';;' repeat the glyph outright; '~' ('~>' is a fused wave-arrow),
    # ':' ('::' is the raised colon.case) and '&' (no '&&' ligature) have
    # no such ligature and are not checked.
    pairs = {"=": "a == b", "<": "a << b", ">": "a >> b", "|": "a || b",
             ".": "a .. b", "!": "a !! b", ";": "a ;; b"}
    for ch in MONA_STANDALONE:
        if ch not in pairs:
            continue
        rows_ch, rows_lig = y_rows(face, cmap[ord(ch)]), y_rows(face, lig_glyph(face, pairs[ch]))
        ok = bool(rows_ch) and all(
            any(abs(a - c) <= 2 and abs(b - d) <= 2 for c, d in rows_lig)
            for a, b in rows_ch)
        check(ok, f"{ch!r} rows {rows_ch} "
                  f"found in {pairs[ch].split()[1]!r} {rows_lig}")


def check_ambiguous_symbols(face, check):
    a_adv, shape_infos = face.a_adv, face.shape
    # the ligature-paired symbols (← → ≠ … etc.): one cell in both
    # families, shaped as well as mapped
    for ch in MONA_AMBIGUOUS:
        got = shape_infos(ch, {})[1][0].x_advance
        check(got == a_adv, f"{ch!r} default {got} (want {a_adv})")


def check_tiling(face, check):
    tf, shape_infos, glyph_order, gs = face.tf, face.shape, face.order, face.gs
    # characters drawn to TILE: a run of them must show no seam, in
    # either family. Term widens a full width from
    # 1000 to 1200, and centring the outline there left 100u of white at
    # every cell join — a rule of ＿ came out dashed and █ striped
    # (build.widen_fullwidth lengthens them instead)
    seam = {}
    for ch in TILING:
        infos, _ = shape_infos(ch, {})
        name = glyph_order[infos[0].codepoint]
        adv = tf["hmtx"][name][0]
        box = build._bounds(gs, name)
        if box is None or box[0] > 2 or box[2] < adv - 2:
            seam[ch] = None if box is None else (round(box[0]), round(box[2]), adv)
    check(not seam, f"every tiling character spans its whole advance "
                    f"({len(TILING)} probes; off: {seam})")


def check_box_drawing_draws(face, check):
    cmap, bounds = face.cmap, face.bounds
    # every box-drawing and block character draws: the probes below
    # name fourteen of them, and a build that emptied any of the other
    # 146 shipped a font that set a terminal frame as whitespace and
    # passed every gate
    blank = [cmap[cp] for cp in range(0x2500, 0x25A0)
             if cp in cmap and cmap[cp] not in bounds]
    check(not blank, f"every box-drawing and block glyph draws "
                     f"(160 probes; blank: {blank[:6]})")


def check_dashed_rules(face, check):
    cmap, hmtx, shape_infos, glyph_order, gs = (
        face.cmap, face.hmtx, face.shape, face.order, face.gs)
    # a dashed rule's pattern must not break where two of them meet:
    # the gap across the join has to be the gap inside the glyph. Such
    # a rule is never faulted by the span test above — by construction
    # its ink does not fill its advance — so a Term face that centred ┄
    # instead of stretching it (111 inside against 312 at the join)
    # passed every gate this file had
    def dashes(name, axis):
        """[(lo, hi)] of each piece of `name` along `axis` (0 = x)."""
        import pathops
        path = pathops.Path()
        gs[name].draw(path.getPen())
        return sorted((c.bounds[axis], c.bounds[axis + 2])
                      for c in path.contours)

    # across the line only: the vertical dashes are Source Code Pro's own
    # drawing, and they do not repeat at this line pitch (┆ measures 134
    # inside against 191 across, in the donor and here alike) — that is
    # the donor's design, not ours
    pattern = {}
    for cp in (0x2504, 0x2505, 0x2508, 0x2509, 0x254C, 0x254D):
        if cp not in cmap:
            continue
        infos, _ = shape_infos(chr(cp), {})
        name = glyph_order[infos[0].codepoint]
        pieces = dashes(name, 0)
        if len(pieces) < 2:
            continue
        inside = [pieces[i + 1][0] - pieces[i][1] for i in range(len(pieces) - 1)]
        join = pieces[0][0] + hmtx[name][0] - pieces[-1][1]
        if max(abs(g - join) for g in inside) > 3:
            pattern[chr(cp)] = ([round(g) for g in inside], round(join))
    check(not pattern, f"a dashed rule keeps its pattern across the join "
                       f"(inside vs across: {pattern})")


def check_vertical_rules(face, check):
    hhea, shape_infos, glyph_order, gs = face.hhea, face.shape, face.order, face.gs
    # and DOWN the page: a line is 1257 units tall here (Source Code
    # Pro's metrics on a face whose Japanese is drawn to a 1000-unit em),
    # and a rule has to reach both edges of it for a column of them to
    # join. The Latin donor draws its box drawing -400..1000, which does.
    def spans_line(box):
        return box is not None and box[1] <= hhea.descent and box[3] >= hhea.ascent

    vseam = {}
    for ch in VTILING:
        infos, _ = shape_infos(ch, {})
        ink = build._bounds(gs, glyph_order[infos[0].codepoint])
        if not spans_line(ink):
            vseam[ch] = None if ink is None else (
                round(ink[1]), round(ink[3]))
    check(not vseam, f"every vertical rule spans the whole line "
                     f"({hhea.ascent}..{hhea.descent}; "
                     f"{len(VTILING)} probes; off: {vseam})")


def check_long_dashes(face, check):
    cmap, hmtx, gs = face.cmap, face.hmtx, face.gs
    # the dashes that exist to butt together. Source Han Sans draws ⸺
    # 1580 units of ink in a 1672 advance — a 92-unit joint — and the
    # grid step rounds that to two full widths: centred there the joint
    # was 420, and 820 in Term (build.fit_to_grid stretches them
    # instead). A sixteenth of the advance is the bound; the design is
    # an eighteenth of it, the centred version three times over the bound
    joints = {}
    for ch in "⸺⸻":
        if ord(ch) not in cmap:
            continue
        name = cmap[ord(ch)]
        adv = hmtx[name][0]
        box = build._bounds(gs, name)
        joint = None if box is None else box[0] + adv - box[2]
        if joint is None or joint > adv // 16:
            joints[ch] = joint if joint is None else round(joint)
    check(not joints, f"the two-em and three-em dashes butt together "
                      f"(joint over a sixteenth of the advance: {joints})")


def check_ccmp_composes(face, check):
    cmap, shape_infos, glyph_order, gs = face.cmap, face.shape, face.order, face.gs
    # the Latin donor's 'ccmp' — on by default in every shaper, and
    # nothing carried it across the graft for six versions: 'i' before a
    # combining dot kept its own and drew a second one 84 units away,
    # 'j' collided with ten accents, and g̃ ê̆ ї́ never composed
    # (build.import_scp_ccmp). Each probe either loses a glyph to a
    # composition or has its base substituted, and what is left does not
    # overlap the accent
    ccmp = {}
    probes = 0
    for base, mark in CCMP_PROBES:
        if ord(base) not in cmap:
            continue       # SCP Italic has no Cyrillic ї to decompose
        probes += 1
        infos, _ = shape_infos(base + mark, {})
        names = [glyph_order[i.codepoint] for i in infos]
        if len(names) > 1 and names[0] == cmap[ord(base)]:
            ccmp[base + mark] = "not composed"
            continue
        if len(names) == 2:
            boxes = []
            for name in names:
                ink = build._bounds(gs, name)
                boxes.append(ink)
            if boxes[0] and boxes[1] and boxes[0][3] > boxes[1][1]:
                ccmp[base + mark] = (round(boxes[0][3]), round(boxes[1][1]))
    check(not ccmp, f"the donor's ccmp composes ({probes} probes; "
                    f"off: {ccmp})")


def check_ccmp_context(face, check):
    cmap, shape_infos, glyph_order = face.cmap, face.shape, face.order
    # ... and only where the donor lets it. Its dotless i and its raised
    # accents live in lookups a chain context calls — listing those in
    # the feature as well, as the first copy did, ran them with the
    # context thrown away: every 'i' and 'j' in running text came out
    # dotless and every accent over a lowercase letter jumped to capital
    # height (129u, on a 486u x-height)
    loose = {}
    for ch in "ij":
        if ord(ch) not in cmap:
            continue
        infos, _ = shape_infos(ch, {})
        got = glyph_order[infos[0].codepoint]
        if len(infos) != 1 or got != cmap[ord(ch)]:
            loose[ch] = got
    if 0x0300 in cmap:
        for base, want_default in (("x", True), ("X", False)):
            infos, _ = shape_infos(base + "\u0300", {})
            got = glyph_order[infos[-1].codepoint]
            if (got == cmap[0x0300]) is not want_default:
                loose[base + "\u0300"] = got
    check(not loose, f"ccmp fires only in the donor's own context "
                     f"(off: {loose})")


def check_accent_stacking(face, check):
    tf, cmap, italic, shape_infos, glyph_order, gs = (
        face.tf, face.cmap, face.italic, face.shape, face.order, face.gs)
    # and a second accent is lifted clear of the first ('mkmk'). Not
    # every pair needs the lift — a flat macron under a ring keeps its
    # place in the donor too — but without the feature, or without the
    # GDEF classes its lookup flag reads, NONE of them move and the two
    # accents draw on top of one another
    def stacked(shape, gs, order, chars):
        """(pairs where the second accent sits no lower than the first,
        pairs probed, pairs the shaper lifted)."""
        lifted = above = probes = 0
        for base in "xz":
            for first, second in zip(ACCENTS, ACCENTS[1:] + ACCENTS[:1]):
                text = base + first + second
                if any(ord(c) not in chars for c in text):
                    continue
                infos, positions = shape(text, {})
                if len(infos) != 3:
                    continue      # composed: nothing left to stack
                probes += 1
                lifted += positions[2].y_offset > 0
                feet = []
                for info, pos in zip(infos, positions):
                    ink = build._bounds(gs, order[info.codepoint])
                    feet.append(None if ink is None
                                else ink[1] + pos.y_offset)
                above += None not in feet and feet[2] >= feet[1]
        return above, probes, lifted

    above, probes, lifted = stacked(shape_infos, gs, glyph_order, cmap)
    # against the DONOR at this weight, not a constant: Source Code Pro
    # leaves a flat accent over a round one where it is, and how often
    # it does that moves with the weight and the slope — 11 of 13 in the
    # italic at wght 400, 9 at 700, 12 in the upright. The constant this
    # started as (probes - 2) was read off Regular and failed every
    # italic face from Medium up, on faces that reproduce the donor
    # exactly
    want = probes - 2
    donor_weight = weight_name(subfamily_name(tf))
    donor_path = os.environ.get("SCP_VF_I" if italic else "SCP_VF_U")
    if donor_weight in WEIGHT_CLASS and donor_path and Path(donor_path).is_file():
        loc = {"wght": WEIGHT_CLASS[donor_weight]}
        donor = TTFont(donor_path)
        want = stacked(make_shaper(donor_path, loc),
                       donor.getGlyphSet(location=loc), donor.getGlyphOrder(),
                       donor.getBestCmap())[0]
    check(probes and above >= want,
          f"a second accent sits no lower than the first "
          f"({above} of {probes} stacked, {lifted} of them lifted; "
          f"the donor stacks {want})")


def check_voicing_marks(face, check):
    cmap, shape_infos, glyph_order, gs = face.cmap, face.shape, face.order, face.gs
    # a voicing mark over a HALF-width kana must not be drawn into it.
    # The mark is registered to the cell before it, and Term widens the
    # full-width cell only — moving the mark with it put 100 units of ｶ
    # ﾈ ｳ under the dakuten (build.realign_halfwidth_marks)

    # a bold stroke touches on its own: Source Han Sans Bold shares
    # 2,844 square units between ﾈ and its dakuten and 4,647 with the
    # handakuten, where Normal shares 1,077 and 1,569 — so "no ink at
    # all" is a Regular-only bound, and it failed every weight from
    # Medium up. Ours share at most 176 (the half-width kana is a whole
    # cell here, not Source Han Sans's 500), and the regression this
    # catches shared up to 4,651
    budget = build.CELL * build.CELL // 400
    voiced = {}
    # every half-width kana that takes a voicing mark, not three of
    # them: the Term re-shift is a chain context naming each kana, and
    # one dropped from it put the mark 100 units left (round 9, mutant
    # J15). The mark's own ink is held to the kana's cell and to the
    # height Source Han Sans draws it at (VOICING_Y), which nothing
    # else bounds for a zero-advance glyph (mutant J6)
    # the shared-ink budget on the three kana it was measured for (the
    # strokes of ﾁ ｻ ｿ ﾃ reach under the mark in Source Han Sans's own
    # design, up to 6,800 square units at Bold); the mark's PLACE on
    # every kana: Source Han Sans sets the voicing mark at one place
    # in the cell whatever the kana, so each is held to where it lands
    # after ｶ, and to the height the mark is drawn at (VOICING_Y) --
    # which nothing else bounds for a zero-advance glyph (mutant J6)
    for kana in "\uff76\uff88\uff73":
        for mark in "\u3099\u309a":
            if ord(kana) not in cmap or ord(mark) not in cmap:
                continue
            area = ink_overlap(face, kana + mark)
            if area > budget:
                voiced[kana + mark] = round(area)
    places = {}
    for kana in [chr(cp) for cp in range(0xFF73, 0xFF8F) if cp in cmap]:
        for mark in "\u3099\u309a":
            if ord(mark) not in cmap:
                continue
            infos, positions = shape_infos(kana + mark, {})
            if len(infos) != 2:
                continue
            ink = build._bounds(gs, glyph_order[infos[1].codepoint])
            if ink is None:
                continue
            x0 = positions[0].x_advance + positions[1].x_offset
            place = (round(x0 + ink[0]), round(positions[1].y_offset + ink[1]),
                     round(x0 + ink[2]), round(positions[1].y_offset + ink[3]))
            first = places.setdefault(mark, (kana, place))
            if place != first[1]:
                voiced[kana + mark] = ("place", place, "after", first[0], first[1])
            elif place[0] < 0 or place[2] > build.CELL + 12 \
                    or not VOICING_Y[0] <= place[1] <= place[3] <= VOICING_Y[1]:
                voiced[kana + mark] = ("ink", place)
    check(len(places) == 2 and not voiced,
          f"a voicing mark clears the half-width kana it marks, at one "
          f"place (over {budget} square units of shared ink, or off: {voiced})")


def check_language_forms(face, check):
    cmap, italic, shape_infos, glyph_order = face.cmap, face.italic, face.shape, face.order
    # the Serbian and Northern Sami forms are copied in with the Greek;
    # Source Han Sans JP has no LangSys for either, so they were
    # unreachable until the import made one (build._new_langsys)
    langs = {}
    for script, lang, text in (("cyrl", "sr", "\u0431"),
                               ("latn", "se", "\u014a")):
        if ord(text) not in cmap:
            continue
        tagged = shape_infos(text, {}, script=script, language=lang)[0]
        default = shape_infos(text, {}, script=script)[0]
        # WHY it failed, not just that it did: "the language form is the
        # default one" and "the letter came apart" are different defects
        # and only the first of them is known
        if len(tagged) != 1:
            langs[script, lang] = ("split into "
                                   f"{len(tagged)}", glyph_order[tagged[0].codepoint])
        elif tagged[0].codepoint == default[0].codepoint:
            langs[script, lang] = ("unchanged", glyph_order[tagged[0].codepoint])
    # as with the Greek above: this skipped the Cyrillic probe on every
    # italic face, saying the italic donor had no Cyrillic. It has 234
    # letters now. Source Sans's own Serbian locl is not imported --
    # import_scp_locl reads the Latin donor's, and the Greek and
    # Cyrillic come from a second one -- so Serbian italic renders the
    # Russian letterforms. Enumerated rather than skipped.
    # matched on the REASON, so a different defect under the same probe
    # is not excused by it
    known = LOCL_ITALIC_GAP if italic else {}
    off = {k: v for k, v in langs.items() if known.get(k) != v[0]}
    check(not off, f"the donor's language forms are reachable "
                   f"(the Serbian б and the Sami Ŋ; unchanged: {off}"
                   + (f"; known italic gaps: {sorted(known)}" if known else "")
                   + ")")


def check_enclosing_mark(face, check):
    cmap = face.cmap
    # and an enclosing mark stays around the character it encloses: it
    # hangs a full width LEFT of the origin, so the Term widening has to
    # take it further left, not leave it on the 1000-unit cell
    around = {}
    for base in "\u56fd\u4e00":
        if ord(base) not in cmap or 0x20DD not in cmap:
            continue
        boxes = placed(face, base + "\u20dd")
        if len(boxes) != 2:
            continue
        if None in boxes:
            around[base] = None
            continue
        # 5 units, not 2: Source Han Sans's own 一 sits 2.5 left of
        # centre in its cell at ExtraLight (the ring 40..960 against
        # 50..955, identical upstream), and the regression this catches
        # is 100
        off = (boxes[1][0] + boxes[1][1]) / 2 - (boxes[0][0] + boxes[0][1]) / 2
        if abs(off) > 5 or boxes[1][0] > boxes[0][0] or boxes[1][1] < boxes[0][1]:
            around[base] = (round(off, 1), tuple(round(v) for v in boxes[1]))
    check(not around, f"an enclosing mark stays around its character "
                      f"(off centre: {around})")


def check_mark_after_ligature(face, check):
    cmap, shape_infos, glyph_order, gs = face.cmap, face.shape, face.order, face.gs
    # and it lands the same way over EVERY base the Term widening left
    # alone, not only over a one-cell one. The Latin layer owns 63
    # multi-cell ligature glyphs (== is 1200 units, === and !== 1800,
    # their cv99 designs too) whose advance is the same in both
    # families — the widening skips them — but the rule that gives
    # Term's 100 units back asked whether the base was ONE CELL wide,
    # so all 488 ligature-and-mark pairs kept the move and the ring
    # came out 100 units left of the cells it encloses. Advance alone
    # cannot tell a skipped ligature from a widened full-width glyph:
    # both are 1200 in Term
    def mark_offset(text):
        """Where the last glyph's ink centre sits relative to the pen
        the base run leaves it at — GPOS placement included."""
        infos, positions = shape_infos(text, {"calt": True, "liga": True})
        ink = build._bounds(gs, glyph_order[infos[-1].codepoint])
        if ink is None or positions[-1].x_advance:
            return None
        return round((ink[0] + ink[2]) / 2
                     + positions[-1].x_offset)

    after_lig = {}
    for mark in ("\u20dd", "\u3099"):
        if ord(mark[0]) not in cmap:
            continue
        want = mark_offset("A" + mark)     # one cell, the settled case
        # U+F120 is a Nerd Fonts icon: one cell, and appended to the
        # face AFTER the widening, so it was in no backtrack coverage
        # and every one of the 10,402 icons kept the -100 in the Term
        # NF faces (U+F120 + U+20DD drew the ring at -465..465 where
        # the same one-cell base gives -365..565)
        for seq in ("==", "===", "!==", "::", "=>", "...", "\uf120"):
            if any(ord(c) not in cmap for c in seq):
                continue
            got = mark_offset(seq + mark)
            if want is None or got != want:
                after_lig[seq + mark] = (got, want)
    check(not after_lig, f"a full-width mark lands the same after a "
                         f"multi-cell ligature as after a letter "
                         f"(off: {after_lig})")


def check_enclosing_mark_down_a_column(face, check):
    cmap, shape_infos, glyph_order, gs = face.cmap, face.shape, face.order, face.gs
    # and it stays around it DOWN a column too. Source Han Sans centres
    # these marks on the vertical column with a placement in 'vert',
    # measured against the outline — move the outline for Term and
    # leave that, and the circle sat 100 units left of the character,
    # the tone marks U+302A/302B hung outside the column's left edge
    # and U+302C/302D stood inside its right
    column = {}
    for base in "\u56fd\u4e00":
        if ord(base) not in cmap or 0x20DD not in cmap:
            continue
        infos, positions = shape_infos(base + "\u20dd", {}, direction="ttb")
        if len(infos) != 2:
            continue
        boxes = []
        for info, pos in zip(infos, positions):
            ink = build._bounds(gs, glyph_order[info.codepoint])
            boxes.append(None if ink is None else
                         (ink[0] + pos.x_offset,
                          ink[2] + pos.x_offset))
        if None in boxes:
            column[base] = None
            continue
        off = (boxes[1][0] + boxes[1][1]) / 2 - (boxes[0][0] + boxes[0][1]) / 2
        if abs(off) > 5:      # as above: upstream's own 一 is 2.5 off
            column[base] = (round(off, 1), tuple(round(v) for v in boxes[1]))
    check(not column, f"an enclosing mark stays around its character "
                      f"down a column (off centre: {column})")


def check_stacked_marks(face, check):
    cmap = face.cmap
    # and where it lands must not depend on how many marks come
    # before it: the rule that gives Term's shift back over a
    # half-width base reads the glyph in front, and a mark is 0 wide,
    # so with one backtrack only the FIRST mark of a stack was put back
    stacked_marks = {}
    for base in "\uff76\uff88AB":
        for between in ("\u3099", "\u0301", "\u3099\u0301", "\u0300\u0301"):
            if any(ord(c) not in cmap for c in base + between + "\u20dd"):
                continue
            alone = placed(face, base + "\u20dd")
            after = placed(face, base + between + "\u20dd")
            if len(alone) != 2 or None in alone or None in after:
                continue
            if max(abs(a - b) for a, b in zip(alone[1], after[-1])) > 2:
                stacked_marks[base + between] = (
                    tuple(round(v) for v in alone[1]),
                    tuple(round(v) for v in after[-1]))
    check(not stacked_marks, f"a mark lands the same behind other marks as "
                             f"behind none (off: {stacked_marks})")


def check_marks_on_the_column(face, check):
    cmap, shape_infos, glyph_order, gs = face.cmap, face.shape, face.order, face.gs
    # ... and a mark after a HALF-width base stays on the column too.
    # The rule that gives Term's shift back is horizontal-only ('dist'):
    # under 'mark' a shaper ran it in a vertical run as well, on top of
    # the placement that puts the mark on the column, and the tone
    # marks stood 100 units clear of it
    outside = {}
    for base in "\uff76A":
        for mark in "\u20dd\u302c\u3099":
            if ord(base) not in cmap or ord(mark) not in cmap:
                continue
            infos, positions = shape_infos(base + mark, {}, direction="ttb")
            if len(infos) != 2:
                continue
            ink = build._bounds(gs, glyph_order[infos[1].codepoint])
            if ink is None:
                continue
            # the vertical column is ±500, and Source Han Sans's own
            # tone marks sit right against its edge: at Bold U+302C
            # reaches 513 and the dakuten 505 upstream, identically, so
            # the bound is the stroke's own growth and not zero. The
            # regression it catches is 100 units
            column = FULLWIDTH / 2
            slack = FULLWIDTH // 20
            lo = ink[0] + positions[1].x_offset
            hi = ink[2] + positions[1].x_offset
            if lo < -column - slack or hi > column + slack:
                outside[base + mark] = (round(lo), round(hi))
    check(not outside, f"a mark stays on the column after a half-width "
                       f"base (outside ±{FULLWIDTH // 2 + FULLWIDTH // 20}: "
                       f"{outside})")


def check_alternate_marks(face, check):
    tf = face.tf
    # every mark a feature substitutes for a positioned one is
    # positioned too: cv11's breve was grafted twice, and the copy the
    # feature selects carried none of the donor's anchors — 229 units
    # low under every ascender, its outline inside the letter's for 35
    # of them
    positioned = set()
    for lookup in tf["GPOS"].table.LookupList.Lookup:
        kind, subs = _unwrap_pos(lookup)
        if kind not in (4, 5, 6):
            continue
        for table in subs:
            for attr in ("MarkCoverage", "Mark1Coverage"):
                cov = getattr(table, attr, None)
                if cov is not None:
                    positioned.update(cov.glyphs)
    adrift = []
    for lookup in tf["GSUB"].table.LookupList.Lookup:
        kind, subs = _unwrap(lookup)
        if kind != 1:
            continue
        for table in subs:
            for src, dst in table.mapping.items():
                if src in positioned and dst not in positioned:
                    adrift.append((src, dst))
    check(not adrift, f"a mark's alternate is positioned like the mark "
                      f"({len(positioned)} positioned; adrift: {adrift[:4]})")


def check_bopomofo_tone_marks(face, check):
    cmap = face.cmap
    # a full-width base carries its own anchors: Source Han Sans hangs
    # the Bopomofo tone marks off ㄓ, and widening it to two cells moves
    # its ink 100u right — leave the anchor behind (shift_anchors) and
    # the mark stands over the letter instead of after it
    tone = {}
    for base, mark in (("\u3113", "\u02ea"), ("\u3113", "\u02eb")):
        if ord(base) not in cmap or ord(mark) not in cmap:
            continue
        boxes = placed(face, base + mark)
        if len(boxes) != 2:
            continue
        # the mark hangs off the letter's own right edge — 107 units
        # inside it in Light through 151 in Bold, the same in both
        # families. Left behind by the widening it sits 100 further in,
        # back over the letter
        gap = None if None in boxes else boxes[0][1] - boxes[1][0]
        if gap is None or not 0 < gap <= 180:
            tone[base + mark] = gap if gap is None else round(gap)
    check(not tone, f"a Bopomofo tone mark hangs off its letter's ink, "
                    f"not its cell (off: {tone})")


def check_grafted_bopomofo_accents(face, check):
    cmap, shape_infos = face.cmap, face.shape
    # ... and the four Source Han Sans attaches that the Latin graft
    # REPLACED hang off it too. Their mark lookups name Source Han Sans's
    # own U+0300/U+0301/U+0307/U+030C, which no codepoint reaches once
    # the graft has re-pointed the cmap, so nothing attached and the
    # accent drew through the letter's strokes: 139 of the 172 pairs
    # shared ink where Source Han Sans shares none. 58 still do — the
    # pairs Source Han Sans never anchored, where its own accent falls
    # clear into the next cell and ours, drawn one cell left, falls over
    # the letter. That is the graft's convention everywhere (日 and あ
    # take an unanchored accent the same way) and not this fix's to
    # change. The two the graft
    # left alone (U+02EA, U+02EB, above) always worked, which is why
    # this went unseen — they are the only two this file probed
    grafted, attaches = {}, 0
    for mark in "\u0300\u0301\u0307\u030c":
        base = "\u3113"      # the letter Source Han Sans anchors all four on
        if ord(base) not in cmap or ord(mark) not in cmap:
            continue
        infos, positions = shape_infos(base + mark, {})
        if len(infos) != 2:
            continue
        attaches += positions[1].x_offset != 0
        # Source Han Sans shares no ink here; unattached, the accent
        # drew straight through the letter's strokes. And WHERE it sits
        # is bounded too: every one of these hangs about the letter's
        # right shoulder — upstream's own centres are 6 to 326 units
        # from that edge, U+0307's the furthest — so an anchor shifted a
        # whole cell, which shares no ink either, is caught
        area = ink_overlap(face, base + mark)
        boxes = placed(face, base + mark)
        off = None if None in boxes else \
            (boxes[1][0] + boxes[1][1]) / 2 - boxes[0][1]
        if area > 1 or off is None or abs(off) > FULLWIDTH / 2:
            grafted[base + mark] = (positions[1].x_offset, round(area),
                                    off if off is None else round(off))
    check(not grafted, f"an attached Bopomofo tone mark hangs off the "
                       f"letter's right shoulder (x_offset, shared ink, "
                       f"centre past the letter: {grafted})")
    check(attaches == 4, f"the grafted accents reach Source Han Sans's own "
                         f"Bopomofo mark lookups ({attaches} of 4 attach)")


def check_variants_reach_ccmp(face, check):
    cmap, shape_infos, glyph_order, tags = face.cmap, face.shape, face.order, face.tags
    # the two imports need each other: SCP's variant features have rules
    # on what ccmp composes (cv02's single-storey g̃) and ccmp has rules
    # on what the variants draw (the ogonek under cv04's serifed i). A
    # variant that cannot reach a composed glyph leaves the default
    # design on the page with the feature on
    missed = {}
    for text, group in (("g\u0303", ("cv02", "ss13")),
                        ("i\u0307", ("cv04", "ss14"))):
        if any(ord(c) not in cmap for c in text):
            continue
        plain = [i.codepoint for i in shape_infos(text, {})[0]]
        for tag in group:
            if tag not in tags:
                continue
            got = [i.codepoint for i in shape_infos(text, {tag: True})[0]]
            if got == plain:
                missed[text, tag] = [glyph_order[g] for g in got]
    check(not missed, f"a variant feature reaches what ccmp composes "
                      f"(unchanged: {missed})")


def check_rules_not_slabs(face, check):
    cmap, gs = face.cmap, face.gs
    # ＿ and ￣ are full width in the default too, so there is no
    # one-cell form for a full-width one to match: lengthening them down
    # the page drew the 41-unit rule as a 320-unit slab (Source Han Sans
    # draws it 36 to 50 units through the weights)
    slabs = {}
    for ch in "\uFF3F\uFFE3":
        if ord(ch) not in cmap:
            continue
        box = build._bounds(gs, cmap[ord(ch)])
        if box is None or box[3] - box[1] > 100:
            slabs[ch] = None if box is None else round(box[3] - box[1])
    check(not slabs, f"the full-width low line and macron are rules, not "
                     f"slabs (over 100u tall: {slabs})")


def check_term_growth(face, check):
    tf, cmap, hmtx, exp_full, bounds = face.tf, face.cmap, face.hmtx, face.exp_full, face.bounds
    # ... and nothing ELSE grew with the advance. A Source Han Sans glyph
    # is drawn inside its 1000 em, so in Term, where the advance is 1200,
    # any of them outside the tiling blocks with more than 1000 of ink
    # was stretched — which is how Ⅷ, ㌄ and a Bold 孰 shipped 20% wide
    # for two rounds while the ten tiling probes above stayed green. The
    # glyphs examined are the ones a reader can reach: the cmap, closed
    # over every one-to-one and alternate substitution in the font —
    # the vertical forms ｜ and ⎰ take under vert, the old shapes under jp78/jp83, and every aalt
    # alternate are 1200 wide too, and a pre-round-33 Term Bold stretched
    # six of them where the check saw four. The closure leaves out the
    # Latin donor's two-cell ligatures, which are 1200 wide in both
    # families and reached only through ligature lookups. (A CID
    # threshold cannot do any of this: Source Han Sans's own CIDs are
    # sparse and run to 65497, and a first cut that used one never
    # looked at 60% of the kanji.)
    if exp_full > 1000:
        tiling = tiling_glyphs(tf)
        pairs = []
        for lookup in tf["GSUB"].table.LookupList.Lookup:
            kind, subtables = _unwrap(lookup)
            if kind == 1:
                for st in subtables:
                    pairs.extend(st.mapping.items())
            elif kind == 3:
                for st in subtables:
                    pairs.extend((src, alts[0])
                                 for src, alts in st.alternates.items() if alts)
        reach = set(cmap.values())
        reach.update(g for t in tf["cmap"].tables if t.format == 14
                     for sel in t.uvsDict.values() for _cp, g in sel if g)
        while True:
            more = {dst for src, dst in pairs if src in reach} - reach
            if not more:
                break
            reach |= more
        grown = [(name, round(box[2] - box[0])) for name, box in bounds.items()
                 if name in reach and hmtx[name][0] == exp_full
                 and name not in tiling and box[2] - box[0] > 1000 + 10]
        check(not grown, f"no ordinary full-width glyph grew with the Term "
                         f"advance ({len(reach)} reachable glyphs examined; "
                         f"{len(grown)} did, e.g. {grown[:4]})")


def check_bar_weights(face, check):
    tf, cmap, italic, sub = face.tf, face.cmap, face.italic, face.sub
    # stroke weight: the Latin is Source Code Pro's named instance for
    # this weight, so its '=' bar must measure the VF's at that wght
    # (SCP_VF_U / SCP_VF_I when set), and the Japanese face is the Source
    # Han Sans weight whose '＝' bar matches it (build.FACES: within 4u)
    weight = weight_name(sub)   # "Regular Italic" collapses to "Italic"
    got = bar_thickness(tf, cmap[ord("=")]) if ord("=") in cmap else 0
    scp_path = os.environ.get("SCP_VF_I" if italic else "SCP_VF_U")
    if weight not in WEIGHT_CLASS:
        print(f"skip  '=' bar vs Source Code Pro (unknown weight {weight!r})")
    elif not (scp_path and Path(scp_path).is_file()):
        print("skip  '=' bar vs Source Code Pro (SCP_VF_U / SCP_VF_I unset)")
    else:
        scp = TTFont(scp_path)
        want = bar_thickness(scp.getGlyphSet(location={"wght": WEIGHT_CLASS[weight]}),
                             scp.getBestCmap()[ord("=")])
        check(abs(got - want) <= 1.5,
              f"'=' bar vs Source Code Pro {weight} (wght {WEIGHT_CLASS[weight]}): "
              f"{got:.1f}u (want {want:.1f}u)")
    if 0xFF1D in cmap:
        cjk = bar_thickness(tf, cmap[0xFF1D])
        # build.FACES pairs Source Han Sans's '＝' with Source Code Pro's
        # UPRIGHT '=' at this weight. An italic face's own '=' is Source
        # Code Pro Italic's, some 4u lighter at the same wght, so measure
        # against the upright bar where the VF is at hand — and give the
        # face's own '=' that much more room where it is not
        ref, against, budget = got, "'='", 5
        upright = os.environ.get("SCP_VF_U")
        if italic and weight in WEIGHT_CLASS and upright and Path(upright).is_file():
            u = TTFont(upright)
            ref = bar_thickness(u.getGlyphSet(location={"wght": WEIGHT_CLASS[weight]}),
                                u.getBestCmap()[ord("=")])
            against = "Source Code Pro upright '='"
        elif italic:
            budget = 9
        check(abs(cjk - ref) <= budget,
              f"'＝' bar (Source Han Sans) {cjk:.1f}u vs {against} {ref:.1f}u: "
              f"paired within {budget}u")


def check_overlaps(face, check):
    cmap, shape_infos, glyph_order = face.cmap, face.shape, face.order
    # imported outlines must be overlap-free (VF instancing leaves seams)
    gs = face.gs

    def overlap_ok(gname):
        p = pathops.Path()
        gs[gname].draw(p.getPen())
        eo = pathops.Path(p)
        eo.fillType = pathops.FillType.EVEN_ODD
        x = pathops.op(pathops.simplify(p, clockwise=p.clockwise),
                       pathops.simplify(eo), pathops.PathOp.XOR)
        return not list(x.segments)

    for ch in "AKkxRvw&ag":
        gname = cmap[ord(ch)]
        ok = overlap_ok(gname)
        check(ok, f"no overlap in {ch!r}")

    for ch in OVERLAP_CJK:
        cp = ord(ch)
        if cp not in cmap:
            check(False, f"no overlap in {ch!r}: not in cmap")
            continue
        gname = cmap[cp]
        ok = overlap_ok(gname)
        check(ok, f"no overlap in CJK {ch!r}")

    for seq in OVERLAP_LIG_SEQS:
        infos, _ = shape_infos(seq, {"calt": True, "liga": True})
        for info in infos:
            gname = glyph_order[info.codepoint]
            # only check glyphs actually produced by the ligature subst,
            # i.e. glyphs not reachable from a single input codepoint
            if len(infos) == 1 or gname not in (cmap.get(ord(c)) for c in seq):
                ok = overlap_ok(gname)
                check(ok, f"no overlap in ligature "
                          f"{seq!r} glyph {gname!r}")


def check_win_metrics(face, check):
    tf = face.tf
    # the win metrics, pinned, not merely positive (copy_line_metrics,
    # README, Gengou Code JP). They are the GDI line height as much as a
    # clipping bound, and this family's ink reaches 1808/-1048 —
    # covering it would give a 2856u line, more than twice the 1257u
    # every renderer that honours USE_TYPO_METRICS uses. The descent
    # does cover the Latin layer's box drawing (-400) and shade blocks
    # (-454); `git show a7c86ec:docs/gengou-plan.md` carries the
    # measurement and the two codepoints left outside
    os2 = tf["OS/2"]
    check((os2.usWinAscent, os2.usWinDescent) == WIN_METRICS,
          f"win metrics are the pinned {WIN_METRICS}, got "
          f"({os2.usWinAscent}, {os2.usWinDescent})")
    # a terminal gives a codepoint no font in the fallback chain covers
    # one column, and Source Han Sans's .notdef is full width -- 1000
    # here, 1200 in Term -- so one such character moved the rest of the
    # line. build.notdef_to_cell replaces it with the Latin donor's --
    # asked above, through check_cells -> verifylib.check_widths_by_class,
    # which holds .notdef to exp_half by the same policy


def main():
    # the order below is the order the lines print in, and it is kept:
    # a run's log diffed against the last one is how a change to these
    # gates is shown to have changed nothing it did not mean to
    check = Checker()          # every check reports; none aborts the rest
    face = Face(FONT)
    tf, cmap = face.tf, face.cmap
    check_advances(face, check)
    check_width_policy(face, check)
    check_greek_cyrillic_cells(face, check)
    check_pinned_wide(face, check)
    # and the other direction: Unicode's Halfwidth block is one column in
    # every terminal's width table, whatever the donor draws it at
    # (build.narrow_halfwidth) -- asked again, cmap-wide, by
    # check_cells -> check_widths_by_class below
    check_advance_grid(face, check)
    is_nf = check_names(face, check)

    check_coverage_order(tf, check)
    # the Latin layer's anchors survive the graft into this face, so
    # they are worth asserting here as well as on the face they came
    # from: import_scp_marks moves every one of them by a cell, and the
    # exact-attachment check is what says the moved anchor and the moved
    # mark still meet
    check_mark_class_closure(tf, check)
    check_private(tf, check)
    check_line_metrics(tf, check)
    check_font_matrix(tf, check)
    check_gdef_classes(tf, check)
    check_pair_positioning(tf, check)
    check_substitution_identity(tf, check)
    check_blank_glyphs(tf, check, tf.getGlyphSet())
    check_name_composition(tf, check)
    check_family_cmap(tf, check, family_reference(FONT, tf))

    check_charstring_metrics(tf, check, face.widths, face.bearings)
    check_jp_tables(face, check)
    check_ink_placement(face, check)
    check_repertoire_draws(face, check)
    check_vertical_metrics(face, check)
    check_style_bits(tf, check, face.sub, face.italic)
    check_gdi_family_name(tf, check)

    # the exact-attachment half of the mark gates (the anchor half runs
    # above, before a shaper is asked): the moved anchor and the moved
    # mark still meet
    check_marks(tf, check, face.shape, tf.getGlyphSet())
    check_cells(tf, check, face.shape, tf.getGlyphSet(), face.exp_half, face.exp_full)
    # the Latin layer is grafted whole, so the donor's cmap is a floor
    # here too -- and the JP faces are where a dropped codepoint would
    # otherwise hide, their own repertoire being ten times the donor's
    check_donor_repertoire(check, cmap)
    # the Latin layer is the same glyphs here as in its donor
    check_donor_letters(tf, check, tf.getGlyphSet())
    check_vertical_forms(tf, check, face.shape)
    check_term_sibling(tf, check, face.exp_full)
    check_ligature_cells(tf, face.shape, check, tf.getGlyphSet(), face.exp_half)
    check_vertical_layout(tf, check, face.shape, face.exp_full)
    check_hints(face, check)
    check_cases(tf, face.shape, check)
    check_features_work(face.shape, check, cmap)
    check_cid_count(face, check)
    check_feature_set(face, check)
    check_cv11(face, check)
    check_standalone_operators(face, check)
    check_ambiguous_symbols(face, check)
    check_tiling(face, check)
    check_box_drawing_draws(face, check)
    check_dashed_rules(face, check)
    check_vertical_rules(face, check)
    check_long_dashes(face, check)
    check_ccmp_composes(face, check)
    check_ccmp_context(face, check)
    check_accent_stacking(face, check)
    # the lift is read through GDEF: 'mkmk' asks which marks it may
    # stack on by the mark attachment class in its lookup flag, and a
    # font that carries the lookup without the classes stacks nothing
    # -- asked above, through check_marks -> verifylib.check_mark_features
    # ("GDEF names the mark classes GPOS filters on")
    check_voicing_marks(face, check)
    check_language_forms(face, check)
    check_enclosing_mark(face, check)
    check_mark_after_ligature(face, check)
    check_enclosing_mark_down_a_column(face, check)
    check_stacked_marks(face, check)
    check_marks_on_the_column(face, check)
    check_alternate_marks(face, check)
    check_bopomofo_tone_marks(face, check)
    check_grafted_bopomofo_accents(face, check)
    check_variants_reach_ccmp(face, check)
    check_rules_not_slabs(face, check)
    check_term_growth(face, check)
    check_bar_weights(face, check)
    check_overlaps(face, check)
    # width metadata: declared monospaced (set_monospace_metadata — what
    # Windows Terminal's picker and GDI's FIXED_PITCH filter read; Source
    # Han Sans's own 0/0 hid it there), xAvgCharWidth per OS/2 v3+ (mean of every
    # non-zero advance), x/cap height measured on the face's own glyphs.
    check_monospace_metadata(tf, check, win_covers_bbox=False)
    check_heights(tf, check, tf.getGlyphSet(), cmap)
    check_win_metrics(face, check)
    # keyed on the name check_names read, not on a spelling of its own:
    # tested as `"Nerd Font" in fam`, this skipped all twenty JP Nerd
    # Fonts faces once their marker became "NF"
    if is_nf:
        check_nerd_font_icons(tf, check)

    print("FAILED" if check.failed else "all checks passed")
    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
