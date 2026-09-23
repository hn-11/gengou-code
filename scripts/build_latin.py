#!/usr/bin/env python3
"""Gengou Code: the Latin-only font, assembled straight from the variable
fonts — Source Code Pro VF as the base, Monaspace VF for the punctuation,
the ligatures and the one-cell arrows.

This is the Latin layer every Gengou Code JP family carries, built once
and on its own (docs/gengou-plan.md): build.py grafts these faces
into Source Han Sans. They are that donor and nothing else -- Gengou
Code itself ships as the variable fonts (build_latin_vf.py), which are
built from the same donors (donor_sources) and the same graft. Each
face is one of Source Code Pro's own named instances — Light 300 /
Regular 400 / Medium 500 / SemiBold 600 / Bold 700 (build.WEIGHT_CLASS),
instanced at exactly that wght, no bar search — with Monaspace's wght
matched to the instance's '=' bar. The Japanese faces follow the
Latin's weight (build.FACES), not the other way round: Source Code Pro
is the benchmark.

The base is the SCP VF instance converted to a static CID-keyed CFF
(fontTools CFF2ToCFF): SCP's own outlines, GSUB (cv01-cv17, zero, salt,
its stylistic sets moved to ss11-ss17) and GPOS (mark positioning)
survive untouched. On top: the 61 ligatures and the 32 ASCII
punctuation glyphs from Monaspace, weight-matched to the same bar and
baseline-aligned on '='; the ligature-paired symbols ← → ↑ ↓ ⇐ ⇒ ⇔ ≠ ≤ ≥
… as Monaspace's one-cell glyphs; calt/liga with the context guards,
ss01-ss08, cv99. The face is saved as it stands, unhinted and not
subroutinized: build.py redraws every glyph it takes and hints them
against the JP face's own zones.

Usage:
  python scripts/build_latin.py [FILTER]   # build.py's weight / style words
                                           # ("base" is accepted and means
                                           # nothing here: one family)
Env (all required):
  SCP_VF_U, SCP_VF_I, SS_VF_I, MONA_VF
Env (optional): GENGOU_VERSION
"""

import io
import sys
from pathlib import Path

from fontTools.cffLib.CFF2ToCFF import convertCFF2ToCFF
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anchors  # noqa: E402
import build  # noqa: E402
import vfsource  # noqa: E402
from verifylib import static_faces  # noqa: E402

CELL = build.CELL   # 600
MONA_K = CELL / build.MONA_CELL

FAMILY, PS_FAMILY = build.LATIN_FAMILY   # "Gengou Code", "GengouCode"


def static_base(scp):
    """The matched Source Code Pro VF instance as a static CID-keyed CFF
    font: CFF2 -> CFF, then a save/load round trip so every table is keyed
    by the CFF charset's cid names (the VF's post names are gone with
    CFF2's charset; fontTools rebuilds a format-3 post), and hmtx left
    side bearings measured from the instanced outlines (the instancer
    leaves the VF's default-master bearings in place — vfsource.sync_lsb)."""
    inst = scp
    convertCFF2ToCFF(inst)
    inst.recalcBBoxes = False
    buf = io.BytesIO()
    inst.save(buf)
    buf.seek(0)
    base = TTFont(buf)
    vfsource.sync_lsb(base)
    return base


def round_outlines(font):
    """Every charstring redrawn through build.draw_clean and a
    T2CharStringPen: the overlaps merged, the points rounded where
    they are (absolute coordinates), the advance kept, hints dropped
    (the instancer had dropped them already). A CFF font's operands are relative, so rounding them one by
    one — what fontTools' instancer does — drifts an outline several
    units along a path; rounding the absolute points keeps each within
    half a unit of the VF's blend, which is what HarfBuzz renders the
    VF as. The overlaps go for the reason draw_clean gives: a variable
    font's masters keep them (Adobe's static releases do not), and 300
    letters a face -- A K Q R e f k, the Cyrillic њ љ -- rendered with
    a seam or a darker join in FreeType where the JP faces, redrawn
    through the same pen on the graft, did not."""
    cff = font["CFF "].cff
    td = cff.topDictIndex[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"].metrics
    for name in font.getGlyphOrder():
        private = build.glyph_private(font, td, name)
        pen = T2CharStringPen(build.pen_width(private, hmtx[name][0]), gs)
        build.draw_clean([(gs, name, (1, 0, 0, 1, 0, 0))], pen)
        td.CharStrings[name] = pen.getCharString(private=private)
    vfsource.sync_lsb(font)


# the Private-dict entries the CFF spec stores as integer deltas or
# integer numbers. BlueScale is the one real number in the group, so it
# is not here
_INT_PRIVATE = ("BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues",
                "StemSnapH", "StemSnapV", "StdHW", "StdVW",
                "BlueShift", "BlueFuzz")


def fix_zone_order(font):
    """Sort and round the alignment zones and stem widths on every
    FontDict -- of each variable font master (build_latin_vf.scp_base_at),
    whose zones varLib blends into the shipped CFF2.

    Instancing a CFF2 blends each zone edge separately, and at some
    weights a pair comes out inverted (SCP Regular: OtherBlues [-217,
    -222]); otfautohint refuses a zone with the wrong sign.

    The blend also leaves them fractional, and the spec stores them as
    integer deltas: eight of the ten static faces shipped values like
    733.9999999 and 671.9999999 (GengouCode-BoldItalic had nine, and
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
    ctx = build.append_context(font)
    td, cmap, fd_index, private, vdon = ctx
    mona_cm, mona_gs = mona.getBestCmap(), vfsource.mona_glyphset(mona)
    new = {}
    for ch in chars:
        cp = ord(ch)
        if cp in cmap or cp not in mona_cm:
            continue
        name = build.graft_outline(font, ctx,
                                   [(mona_gs, mona_cm[cp], vfsource.mona_transform(mona, 0, dy, k))],
                                   CELL, simplify=not vfsource.keeps_overlaps(mona))
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
# (build.cell_fit, the one rule for seating a proportional glyph in a
# monospaced cell).
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
    ctx = build.append_context(font)
    td, cmap, fd_index, private, vdon = ctx
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
            # centred in the cell, condensed only where the ink will not
            # fit: build.cell_fit, the same rule for every donor glyph
            sx, dx = build.cell_fit(build._bounds(sans_gs, src), CELL,
                                    build.LETTER_BEARING)
            condensed += sx != 1.0
            name = build.graft_outline(font, ctx, [(sans_gs, src, (sx, 0, 0, 1, dx, 0))],
                                       CELL, simplify=not vfsource.keeps_overlaps(sans))
            new[cp] = name
            # one donor glyph can draw more than one codepoint (Source
            # Sans draws U+03C6 and U+03D5 with a single 'phi'), so this
            # collects our names rather than keeping the last
            donor_map.setdefault(src, []).append(name)
            placements[name] = (sx, dx)
    build.set_cmap(font, new, add_new=True)
    anchored = anchors.import_donor_base_anchors(font, sans, donor_map, placements)
    taken_apart = anchors.import_donor_decompositions(font, sans, donor_map)
    print(f"  Greek and Cyrillic from Source Sans: "
          f"{len(new)} ({condensed} condensed, {anchored} base anchors, "
          f"{taken_apart} decomposed)")
    return len(new), condensed, anchored


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
    are pin_win_metrics' business."""
    hhea = font["hhea"]
    os2 = font["OS/2"]
    os2.sTypoAscender = hhea.ascent
    os2.sTypoDescender = hhea.descent
    os2.sTypoLineGap = hhea.lineGap
    os2.fsSelection |= 0x80


# (usWinAscent, usWinDescent) for every Latin face, static and variable
# alike: pinned rather than fit per face or harmonized after the fact,
# the way build.WIN_METRICS is pinned for the JP faces. Every face this
# family has ever built draws the same two extremes -- U+2593 SHADE at
# head.yMin -454 and Powerline U+E0A0 at head.yMax 1060 -- at every
# weight, so a single pair already covers the whole family; measuring
# it per face and then reconciling the faces against each other (as
# harmonize_latin.py used to, once a whole family was assembled) never
# once changed the answer. If an upstream update ever draws past this
# box, pin_win_metrics below fails the build that first sees it, naming
# the glyph extents, rather than silently widening the GDI clip (and
# the line height every legacy GDI path derives from it).
LATIN_WIN_METRICS = (1060, 454)


def pin_win_metrics(font):
    """Set OS/2 usWinAscent/usWinDescent to the pinned LATIN_WIN_METRICS.
    Raises when the font's own glyph extents (head.yMax / -head.yMin)
    have grown past the pinned pair -- verify.py's "win metrics cover
    the bbox" check would fail too, but the build should say so first,
    with the extents that broke it."""
    head = font["head"]
    ascent, descent = LATIN_WIN_METRICS
    if head.yMax > ascent or -head.yMin > descent:
        raise RuntimeError(
            f"glyph extents {head.yMax}/{-head.yMin} exceed the pinned "
            f"LATIN_WIN_METRICS {LATIN_WIN_METRICS}")
    font["OS/2"].usWinAscent, font["OS/2"].usWinDescent = LATIN_WIN_METRICS


def scp_source(path):
    """A Source Code Pro VF as a vfsource.VFSource: wght only, bars in
    SCP's own units (scale 1.0)."""
    return vfsource._vf_source(path, 1.0, {"wght": 0})


def donor_sources(env, italic):
    """The donors one style is built from, as (scp, mona, sans, upright):
    the style's Source Code Pro VF, Monaspace (scaled to our cell, its
    other axes pinned at the regular width and no slant), for an italic
    Source Sans Italic and the codepoints the upright draws that bound
    it (else None, None). The static faces and the variable fonts both
    take them from here, so the two are matched against the same donors
    by construction -- nothing compares the one with the other."""
    scp = scp_source(env["SCP_VF_I" if italic else "SCP_VF_U"])
    mona = vfsource._vf_source(env["MONA_VF"], MONA_K,
                               {"wght": 0, "wdth": 100, "slnt": 0})
    if not italic:
        return scp, mona, None, None
    # Source Code Pro Italic draws no Cyrillic and one Greek letter, so
    # the italic takes both scripts from Source Sans 3 Italic, bounded
    # by what the upright draws (add_missing_from_sans)
    return (scp, mona, scp_source(env["SS_VF_I"]), upright_cmap(env["SCP_VF_U"]))


def build_face(job):
    """One static face: the Latin donor build.py grafts into Source Han
    Sans, and nothing else -- it ships as nothing, so it carries only
    what build.py reads off it (outlines, advances, GSUB/GPOS/GDEF, the
    line metrics, italic angle and the donors' credits). The JP face
    redraws every glyph it takes from here and hints them itself, and
    recomputes the OS/2 ranges, heights, STAT and extents on its own
    result, so none of that is done here."""
    weight, italic, env, out_dir = job
    label = f"{weight}{' Italic' if italic else ''}"
    wght = build.WEIGHT_CLASS[weight]
    scp_src, mona_src, sans_src, upright = donor_sources(env, italic)
    # SCP's exact blend at its named instance's wght; round_outlines
    # rounds it point by point below (the instancer's own operand
    # rounding drifts an outline several units along a path —
    # vfsource.unrounded_cff2_instancing)
    with vfsource.unrounded_cff2_instancing():
        scp = scp_src.at(wght)
    # the stroke weight Monaspace is matched to: this instance's own bar
    target = build.bar_thickness(scp, scp.getBestCmap()[ord("=")])
    ref_angle = (scp["post"].italicAngle or -12.0) if italic else None
    mona = mona_src.matched(target, ref_angle)
    # the italic faces' Greek and Cyrillic, matched on the same '=' bar
    # as Monaspace is. No slant argument: Source Sans ships a drawn
    # italic at the same -11 degrees, so there is no residual to shear
    sans = sans_src.matched(target) if italic else None
    credits = credits_from(("Source Code Pro", scp), ("Monaspace", mona),
                           *([("Source Sans", sans)] if italic else []))

    base = static_base(_copy_instance(scp))
    round_outlines(base)
    added = graft(base, mona, sans, upright)
    use_typo_metrics(base)
    ps = build.set_names(base, "", weight, italic,
                         ref_angle if ref_angle is not None else -12.0,
                         version=env.get("GENGOU_VERSION"), credits=credits,
                         family_base=FAMILY, ps_base=PS_FAMILY, base_credit=None)
    anchors.classify_unicode_marks(base)
    # after classify_unicode_marks, which is what makes the shaper treat
    # these as marks (and so zero their spacing advance) in the first
    # place
    loose = anchors.anchor_loose_letters(base)
    if loose < LOOSE_FLOOR:
        # a count, not a truthiness test: one rule turned away leaves the
        # rest placing thousands, and a pass that placed 37 letters where
        # it should place 2,800 ships the defect this exists to undo --
        # an accent on any letter it missed a whole cell right, on the
        # next character -- with every gate green
        raise RuntimeError(f"only {loose} letters were given a fitted base "
                           f"anchor, against a floor of {LOOSE_FLOOR}; "
                           f"see anchors.anchor_loose_letters")
    print(f"  letters given a fitted base anchor: {loose}")
    # the marks' side of the same gap, and the italic's stacked-accent
    # lift copied from the upright at this weight (both no-ops on the
    # upright; see the two functions)
    print(f"  marks given a lookup's anchor: {anchors.anchor_loose_marks(base)}")
    if italic:
        with vfsource.unrounded_cff2_instancing():
            model = scp_source(env["SCP_VF_U"]).at(wght)
        print(f"  stacked-accent anchors lifted as the upright's: "
              f"{anchors.mirror_stack_lift(base, model)}")
    out = Path(out_dir) / f"{ps}.otf"
    # a plain save: build.py redraws and hints what it takes from here,
    # so hints or subroutines written now would only be thrown away
    base.recalcBBoxes = False
    base.save(out)
    return (f"{label}: wght {wght} bar {target:.1f} ligs={len(added)} "
            f"glyphs={base['maxp'].numGlyphs} -> {out.name}")


def graft(base, mona, sans=None, upright=None):
    """The Latin layer's grafts onto one Source Code Pro instance, in
    place: Monaspace's ligatures and the punctuation they are cut with
    (at the baseline shift that aligns the two '=' signs), the
    characters Source Code Pro lacks, for an italic Source Sans's Greek
    and Cyrillic (`sans`, bounded by the upright's codepoints
    `upright`), then the stylistic-set remap and the GSUB the ligatures
    need. Returns add_glyphs' {sequence: ligature glyph}. The static
    faces and every master of the variable fonts take exactly this
    sequence; what differs between them is the donor instances passed
    in (a master's are matched with master=True)."""
    dy = vfsource.mona_baseline_shift(base, mona, MONA_K)
    alts = {}
    added = vfsource.add_glyphs(base, mona, alts, build.LIGATURES, dy, cell=CELL)
    vfsource.replace_from_mona(base, mona,
                            build.MONA_STANDALONE + build.MONA_AMBIGUOUS, dy, MONA_K)
    add_missing_from_mona(base, mona, build.MONA_AMBIGUOUS, dy, MONA_K)
    if sans is not None:
        add_missing_from_sans(base, sans, upright)
    remap_scp_stylistic_sets(base)
    build.add_gsub(base, added, alts, build.LIGATURES)
    print(f"  capitals added to the raised-accent context: "
          f"{anchors.raise_marks_after_capitals(base)}")
    if "DSIG" in base:
        del base["DSIG"]
    return added


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
        # nerdpatch.py to pick up (same as build.py)
        for stale in static_faces(out_dir, PS_FAMILY):
            stale.unlink()
    # a weight's two styles side by side, not one after the other
    build.run_faces(jobs, build_face, pool_from=2,
                    label=lambda job: f"{job[0]}{' Italic' if job[1] else ''}",
                    on_result=lambda job, msg: print(msg))


if __name__ == "__main__":
    main()
