#!/usr/bin/env python3
"""Gengou: the Latin-only font, assembled straight from the variable
fonts — Source Code Pro VF as the base, Monaspace VF for the punctuation,
the ligatures and the one-cell arrows.

This is the Latin layer every Gengou JP family carries, built once
and on its own (docs/gengou-plan.md): build.py grafts these faces
into Source Han Sans as they are. Each face is one of Source Code Pro's
own named instances — Light 300 / Regular 400 / Medium 500 / SemiBold
600 / Bold 700 (build.WEIGHT_CLASS), instanced at exactly that wght, no
bar search — with Monaspace's wght matched to the instance's '=' bar.
The Japanese faces follow the Latin's weight (build.FACES), not the
other way round: Source Code Pro is the benchmark.

The base is the SCP VF instance converted to a static CID-keyed CFF
(fontTools CFF2ToCFF): SCP's own outlines, alignment zones, GSUB
(cv01-cv17, zero, salt, its stylistic sets moved to ss11-ss17) and GPOS
(mark positioning) survive untouched; the hints do not survive the
instancer, so the whole font is re-hinted against SCP's zones. On top:
the 61 ligatures and the 32 ASCII punctuation glyphs from Monaspace,
weight-matched to the same bar and baseline-aligned on '='; the
ligature-paired symbols ← → ↑ ↓ ⇐ ⇒ ⇔ ≠ ≤ ≥ … as Monaspace's one-cell
glyphs; calt/liga with the context guards, ss01-ss08, cv99. otfautohint
hints everything against SCP's zones; cffsubr subroutinizes.

Usage:
  python scripts/build_latin.py [FILTER]   # build.py's weight / style words
                                           # ("base" is accepted and means
                                           # nothing here: one family)
Env (all required):
  SCP_VF_U, SCP_VF_I, SS_VF_I, MONA_VF
Env (optional): GENGOU_VERSION, GENGOU_SKIP_AUTOHINT
"""

import io
import sys
from pathlib import Path

from fontTools.cffLib.CFF2ToCFF import convertCFF2ToCFF
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from verifylib import static_faces  # noqa: E402

CELL = build.CELL   # 600
MONA_K = CELL / build.MONA_CELL

FAMILY, PS_FAMILY = build.LATIN_FAMILY   # "Gengou", "Gengou"


def static_base(scp):
    """The matched Source Code Pro VF instance as a static CID-keyed CFF
    font: CFF2 -> CFF, then a save/load round trip so every table is keyed
    by the CFF charset's cid names (the VF's post names are gone with
    CFF2's charset; fontTools rebuilds a format-3 post), and hmtx left
    side bearings measured from the instanced outlines (the instancer
    leaves the VF's default-master bearings in place — build.sync_lsb)."""
    inst = scp
    convertCFF2ToCFF(inst)
    inst.recalcBBoxes = False
    buf = io.BytesIO()
    inst.save(buf)
    buf.seek(0)
    base = TTFont(buf)
    build.sync_lsb(base)
    return base


def round_outlines(font):
    """Every charstring redrawn through a T2CharStringPen: the points
    rounded where they are (absolute coordinates), the advance kept,
    hints dropped (the instancer had dropped them already; otfautohint
    puts them back). A CFF font's operands are relative, so rounding
    them one by one — what fontTools' instancer does — drifts an outline
    several units along a path; rounding the absolute points keeps each
    within half a unit of the VF's blend, which is what HarfBuzz renders
    the VF as."""
    cff = font["CFF "].cff
    td = cff.topDictIndex[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"].metrics
    for name in font.getGlyphOrder():
        private = td.FDArray[td.FDSelect[font.getGlyphID(name)]].Private
        pen = T2CharStringPen(build.pen_width(private, hmtx[name][0]), gs)
        gs[name].draw(pen)
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = \
            pen.getCharString(private=private)
    build.sync_lsb(font)


# the Private-dict entries the CFF spec stores as integer deltas or
# integer numbers. BlueScale is the one real number in the group, so it
# is not here
_INT_PRIVATE = ("BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues",
                "StemSnapH", "StemSnapV", "StdHW", "StdVW",
                "BlueShift", "BlueFuzz")


def fix_zone_order(font):
    """Sort and round the alignment zones and stem widths on every
    FontDict.

    Instancing a CFF2 blends each zone edge separately, and at some
    weights a pair comes out inverted (SCP Regular: OtherBlues [-217,
    -222]); otfautohint refuses a zone with the wrong sign.

    The blend also leaves them fractional, and the spec stores them as
    integer deltas: eight of the ten static faces shipped values like
    733.9999999 and 671.9999999 (Gengou-BoldItalic had nine, and
    StdHW 115.33964), which a reader that truncates rather than rounds
    reads a unit low — the zone then sits under the overshoot it is
    there to suppress. Only Regular and Regular Italic were integral,
    because they sit on Source Code Pro's own default master. The JP
    faces never saw this: build.latin_blue_zones re-measures and rounds
    what it writes."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    for fd in td.FDArray:
        private = fd.Private
        for key in ("BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues"):
            values = getattr(private, key, None)
            if not values:
                continue
            pairs = sorted(tuple(sorted(values[i:i + 2]))
                           for i in range(0, len(values) - 1, 2))
            setattr(private, key, [v for pair in pairs for v in pair])
        for key in _INT_PRIVATE:
            value = getattr(private, key, None)
            if isinstance(value, (list, tuple)):
                setattr(private, key, [int(round(v)) for v in value])
            elif isinstance(value, float):
                setattr(private, key, int(round(value)))


def add_missing_from_mona(font, mona, chars, dy, k):
    """Characters Source Code Pro lacks but Monaspace has (⇔): append the
    one-cell Monaspace glyph and map it."""
    td, cmap, fd_index, private, vdon = build.append_context(font)
    mona_cm, mona_gs = mona.getBestCmap(), build.mona_glyphset(mona)
    new = {}
    for ch in chars:
        cp = ord(ch)
        if cp in cmap or cp not in mona_cm:
            continue
        pen = build.T2CharStringPen(build.pen_width(private, CELL), mona_gs)
        build.draw_clean([(mona_gs, mona_cm[cp], build.mona_transform(mona, 0, dy, k))], pen)
        name = build.alloc_glyph_name(font)
        build.append_glyph(font, td, name, pen.getCharString(private=private),
                           fd_index, CELL, None, vdon)
        new[cp] = name
    build.set_cmap(font, new, add_new=True)
    print(f"  one-cell glyphs SCP lacks, from Monaspace: {len(new)}")


# Greek and Cyrillic, which Source Code Pro Italic does not draw.
# Measured on the pinned releases: the upright VF carries 234 codepoints
# in these two blocks, the italic VF carries one -- U+03C0, the letter a
# programmer types. Adobe drew that italic by hand and stopped there; it
# is a deliberate edge, not an oversight, so the gap does not close by
# waiting.
#
# Source Sans 3 Italic is the nearest thing to what Source Code Pro
# Italic would have drawn. Source Code Pro was derived from Source Sans,
# and measured at wght 400 and 700 the two italics agree exactly on the
# italic angle (-11.0) and the cap height, and to a unit on the
# x-height. It is proportional where this family is not, so each glyph
# is centred in the cell and condensed only where its ink will not fit
# -- the rule narrow_letters applies to these same two scripts on the JP
# side, for the same reason.
#
# Greek Extended is in the range because Source Code Pro's upright draws
# sixteen of its codepoints (the koronis, psili, dasia and perispomeni
# spacing forms) and its italic draws none, so the italic faces reached
# .notdef where their own upright had the letter -- at Source Han Sans's
# full width on the JP side, which moved the rest of the line. The
# `upright` bound below keeps the import to those sixteen: Source Sans
# draws 233 of the block, and a family whose italic reaches past its
# upright is the defect this donor exists to undo.
SANS_BLOCKS = ((0x0370, 0x04FF), (0x1F00, 0x1FFF))


# the fewest letters anchor_loose_letters may place before the build is
# refusing to ship. These donors leave about 2,800 per face; the floor
# is well under that so an upstream that anchors more of its own
# alphabet does not trip it, and well over the handful a single
# surviving rule would place.
LOOSE_FLOOR = 1500


def add_missing_from_sans(font, sans, upright):
    """Draw the Greek and Cyrillic of `sans` into this face, one cell
    each, for the whole of SANS_BLOCKS -- replacing what the face has
    where it has anything. Returns (added, condensed, base anchors
    carried across).

    The whole block, not the gaps: Source Code Pro's italic draws one
    letter in it, a pi it does not anchor, so an accent over pi sat a
    cell and a half to the right, on top of whatever followed. Source
    Sans anchors its own. Taking the block from one donor also retires
    the exception -- there is no longer a "what this face already has"
    for the block to be inconsistent about.

    `upright` is the codepoint set the upright faces draw, and bounds
    this one: Source Sans covers ten letters in these blocks that Source
    Code Pro's upright does not (Greek sho, Cyrillic ka with hook and
    the like), and a family whose italic reaches codepoints its upright
    cannot is a defect of its own -- the one this whole change is
    undoing, pointing the other way."""
    td, cmap, fd_index, private, vdon = build.append_context(font)
    sans_cm, sans_gs = sans.getBestCmap(), sans.getGlyphSet()
    new, condensed = {}, 0
    # {donor glyph: [ours]} and {ours: the x scale and offset cell_fit
    # used}, for import_donor_base_anchors: an anchor is a point on the
    # outline and has to move with it
    donor_map, placements = {}, {}
    for lo, hi in SANS_BLOCKS:
        for cp in range(lo, hi + 1):
            if cp not in sans_cm or cp not in upright:
                continue
            # set_cmap below replaces the entry, so a glyph the face
            # already had for this codepoint is left behind unreached
            # (nothing but cmap points at it -- checked for pi, the one
            # such glyph Source Code Pro Italic draws in the block)
            src = sans_cm[cp]
            # the same rule narrow_letters puts on these two scripts on
            # the JP side, from the same place
            sx, dx = build.cell_fit(build._bounds(sans_gs, src), CELL,
                                    build.LETTER_BEARING)
            condensed += sx != 1.0
            pen = build.T2CharStringPen(build.pen_width(private, CELL), sans_gs)
            build.draw_clean([(sans_gs, src, (sx, 0, 0, 1, dx, 0))], pen)
            name = build.alloc_glyph_name(font)
            build.append_glyph(font, td, name, pen.getCharString(private=private),
                               fd_index, CELL, None, vdon)
            new[cp] = name
            # one donor glyph can draw more than one codepoint (Source
            # Sans draws U+03C6 and U+03D5 with a single 'phi'), so this
            # collects our names rather than keeping the last
            donor_map.setdefault(src, []).append(name)
            placements[name] = (sx, dx)
    build.set_cmap(font, new, add_new=True)
    anchors = build.import_donor_base_anchors(font, sans, donor_map, placements)
    taken_apart = build.import_donor_decompositions(font, sans, donor_map)
    print(f"  Greek and Cyrillic from Source Sans: "
          f"{len(new)} ({condensed} condensed, {anchors} base anchors, "
          f"{taken_apart} decomposed)")
    return len(new), condensed, anchors


def remap_scp_stylistic_sets(font):
    """SCP's ss01-ss07 become ss11-ss17 (their UI names come along), so
    ss01-ss08 are free for the ligature groups — the same numbering the
    JP families expose."""
    gsub = font["GSUB"].table
    for fr in gsub.FeatureList.FeatureRecord:
        tag = build._remap_scp_tag(fr.FeatureTag)
        if tag and tag != fr.FeatureTag:
            fr.FeatureTag = tag
    build.sort_feature_list(gsub)


def credits_from(*donors):
    return [(label, donor["name"].getDebugName(0)
             or donor["name"].getDebugName(7),
             donor["name"].getDebugName(9))
            for label, donor in donors]


def use_typo_metrics(font):
    """typo == hhea (SCP ships hhea 984/-273 but typo 750/-250, which only
    agree if nobody reads typo) and USE_TYPO_METRICS on. The win metrics
    are fit_win_metrics'/harmonize_win_metrics' business."""
    hhea = font["hhea"]
    os2 = font["OS/2"]
    os2.sTypoAscender = hhea.ascent
    os2.sTypoDescender = hhea.descent
    os2.sTypoLineGap = hhea.lineGap
    os2.fsSelection |= 0x80


def fit_win_metrics(font, ascent=0, descent=0):
    head = font["head"]
    os2 = font["OS/2"]
    os2.usWinAscent = max(os2.usWinAscent, head.yMax, ascent)
    os2.usWinDescent = max(os2.usWinDescent, -head.yMin, descent)


def harmonize_win_metrics(paths):
    """One usWinAscent/Descent pair over `paths`: the max over every one
    of them. main() passes the whole family present in the output
    directory, not only the faces this run built, so a filtered run (CI
    builds Regular and Light Italic in separate steps) cannot leave the
    family split between two pairs."""
    fonts = {p: TTFont(p) for p in paths}
    ascent = max(f["OS/2"].usWinAscent for f in fonts.values())
    descent = max(f["OS/2"].usWinDescent for f in fonts.values())
    for p, f in fonts.items():
        if (f["OS/2"].usWinAscent, f["OS/2"].usWinDescent) != (ascent, descent):
            fit_win_metrics(f, ascent, descent)
            f.save(p)
    return ascent, descent


def build_face(job):
    weight, italic, env, out_dir = job
    label = f"{weight}{' Italic' if italic else ''}"
    wght = build.WEIGHT_CLASS[weight]
    scp_src = build._vf_source(env["SCP_VF_I" if italic else "SCP_VF_U"], 1.0,
                               {"wght": 0})
    # SCP's exact blend at its named instance's wght; round_outlines
    # rounds it point by point below (the instancer's own operand
    # rounding drifts an outline several units along a path —
    # build.unrounded_cff2_instancing)
    with build.unrounded_cff2_instancing():
        scp = scp_src.at(wght)
    # the stroke weight Monaspace is matched to: this instance's own bar
    target = build.bar_thickness(scp, scp.getBestCmap()[ord("=")])
    ref_angle = (scp["post"].italicAngle or -12.0) if italic else None
    mona_src = build._vf_source(env["MONA_VF"], MONA_K,
                                {"wght": 0, "wdth": 100, "slnt": 0})
    mona = mona_src.matched(target, ref_angle)
    # the italic faces' Greek and Cyrillic, matched on the same '=' bar
    # as Monaspace is. No slant argument: Source Sans ships a drawn
    # italic at the same -11 degrees, so there is no residual to shear
    sans = (build._vf_source(env["SS_VF_I"], 1.0, {"wght": 0}).matched(target)
            if italic else None)
    credits = credits_from(("Source Code Pro", scp), ("Monaspace", mona),
                           *([("Source Sans", sans)] if italic else []))

    base = static_base(_copy_instance(scp))
    round_outlines(base)
    fix_zone_order(base)
    dy = build.mona_baseline_shift(base, mona, MONA_K)
    alts = {}
    added = build.add_glyphs(base, mona, alts, build.LIGATURES, dy, cell=CELL)
    build.replace_from_mona(base, mona,
                            build.MONA_STANDALONE + build.MONA_AMBIGUOUS, dy, MONA_K)
    add_missing_from_mona(base, mona, build.MONA_AMBIGUOUS, dy, MONA_K)
    if sans is not None:
        add_missing_from_sans(base, sans, upright_cmap(env["SCP_VF_U"]))
    remap_scp_stylistic_sets(base)
    build.add_gsub(base, added, alts, build.LIGATURES)
    if "DSIG" in base:
        del base["DSIG"]
    use_typo_metrics(base)
    base["OS/2"].recalcUnicodeRanges(base)
    build.recalc_codepage_range(base)
    build.set_monospace_metadata(base)
    build.set_latin_heights(base)
    ps = build.set_names(base, "", weight, italic,
                         ref_angle if ref_angle is not None else -12.0,
                         version=env.get("GENGOU_VERSION"), credits=credits,
                         family_base=FAMILY, ps_base=PS_FAMILY, base_credit=None)
    build.classify_unicode_marks(base)
    # after classify_unicode_marks, which is what makes the shaper treat
    # these as marks (and so zero their spacing advance) in the first
    # place; before the bbox, which the new anchors do not move
    loose = build.anchor_loose_letters(base)
    if loose < LOOSE_FLOOR:
        # a count, not a truthiness test: one rule turned away leaves the
        # rest placing thousands, and a pass that placed 37 letters where
        # it should place 2,800 ships the defect this exists to undo --
        # an accent on any letter it missed a whole cell right, on the
        # next character -- with every gate green
        raise RuntimeError(f"only {loose} letters were given a fitted base "
                           f"anchor, against a floor of {LOOSE_FLOOR}; "
                           f"see build.anchor_loose_letters")
    print(f"  letters given a fitted base anchor: {loose}")
    build.add_stat(base, weight, italic)
    build.prune_orphan_names(base)
    build.update_bbox(base)
    fit_win_metrics(base)
    out = Path(out_dir) / f"{ps}.otf"
    # every glyph: fontTools' CFF2 instancing leaves the SCP outlines
    # without their hints (the VF's charstrings carry them inside blended
    # subroutines that the instancer flattens), so the whole font is
    # hinted here against SCP's own alignment zones
    build.write_face(base, out, base.getGlyphOrder())
    return (f"{label}: wght {wght} bar {target:.1f} ligs={len(added)} "
            f"glyphs={base['maxp'].numGlyphs} -> {out.name}")


def upright_cmap(path):
    """The codepoints the upright faces draw, read straight off the
    upright VF — the italic build's bound, and the same set at every
    instance, so no instancing is needed to ask."""
    return set(TTFont(path, lazy=True).getBestCmap())


def _copy_instance(scp):
    """VFSource caches its converged instance; convertCFF2ToCFF mutates,
    so work on a fresh load of the same bytes."""
    buf = io.BytesIO()
    scp.save(buf)
    buf.seek(0)
    return TTFont(buf)


# all required, the italic donor included: a build that skipped it would
# ship italic faces silently missing two scripts, which is the state
# this donor was added to end
VF_ENV = ("SCP_VF_U", "SCP_VF_I", "SS_VF_I", "MONA_VF")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = build.env_paths(dict.fromkeys(VF_ENV))
    out_dir = build.ROOT / "dist" / "latin"
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for weight, _ in build.FACES:
        for italic in (False, True):
            label = f"{weight}{' Italic' if italic else ''}"
            # one family: the "base" variant word is the only one that
            # matches (a Term face has no Latin of its own)
            if not build.face_matches(only, weight, label, ""):
                continue
            jobs.append((weight, italic, env, str(out_dir)))
    if not jobs:
        sys.exit(f"no face matches {only!r}")
    if only is None:
        # a full build must not leave faces from an older roster for
        # harmonize_win_metrics / nerdpatch.py to pick up (same as build.py)
        for stale in static_faces(out_dir, PS_FAMILY):
            stale.unlink()
    try:
        # a weight's two styles side by side, not one after the other
        build.run_faces(jobs, build_face, pool_from=2,
                        label=lambda job: f"{job[0]}{' Italic' if job[1] else ''}",
                        on_result=lambda job, msg: print(msg))
    finally:
        # over every face of the family in the output directory (see
        # harmonize_win_metrics). A face a failed worker left half
        # written would raise here and replace run_faces' own report of
        # which faces failed, so it is swallowed only while that report
        # is already on its way out
        in_flight = sys.exc_info()[1]                  # run_faces' own report?
        try:
            paths = static_faces(out_dir, PS_FAMILY)
            if paths:
                a, d = harmonize_win_metrics(paths)
                print(f"win metrics {a}/{d} over {len(paths)} faces")
        except Exception as exc:                       # noqa: BLE001
            if in_flight is None:
                raise                                  # this pass IS the failure
            print(f"win metrics skipped: {exc!r}")


if __name__ == "__main__":
    main()
