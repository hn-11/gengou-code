#!/usr/bin/env python3
"""Regression test for the Latin-only faces (dist/latin/GengouCode-*.otf):
every ligature fires, the guards hold, everything sits on the 600 grid,
nothing CJK or full-width is left, and the metadata is the Latin font's
own. Usage: python scripts/verify_latin.py dist/latin/GengouCode-Regular.otf"""

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_latin  # noqa: E402
from verifylib import (  # noqa: E402
    Checker,
    check_blank_glyphs,
    check_cases,
    check_cells,
    check_charstring_metrics,
    check_coverage_order,
    check_donor_letters,
    check_donor_repertoire,
    check_family_cmap,
    check_family_names,
    check_features_work,
    check_font_matrix,
    check_gdef_classes,
    check_gdef_marks,
    check_gdi_family_name,
    check_grid,
    check_heights,
    check_ink_inside,
    check_latin_repertoire,
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
    hmtx_mismatches,
    make_shaper,
)

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "latin" / "GengouCode-Regular.otf")
CELL = build.CELL

def main():
    tf = TTFont(str(FONT))
    check = Checker()

    name = tf["name"]
    # a Nerd Fonts variant ("Gengou Code NF", nerdpatch.nf_name)
    # appends Nerd Fonts' own marker after the family
    is_nf = check_family_names(tf, check, build_latin.FAMILY, build_latin.PS_FAMILY)
    subfamily = name.getDebugName(17) or name.getDebugName(2) or ""
    italic = "Italic" in subfamily
    check_style_bits(tf, check, name.getDebugName(2) or "", italic)
    check_gdi_family_name(tf, check)
    check_name_ids(tf, check, (1, 2, 3, 4, 5, 6, 8, 9, 11, 13, 14))
    weight = check_weight_class(tf, check, subfamily)
    if weight:
        check_stat(tf, check, weight, italic)
    check_version_stamp(tf, check)
    n0 = name.getDebugName(0) or ""
    check("Source Code Pro:" in n0 and "Monaspace:" in n0
          and "Source Han Sans" not in n0,
          "nameID 0 credits Source Code Pro and Monaspace, not Source Han Sans")

    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"]
    check_latin_repertoire(check, cmap)
    check_donor_repertoire(check, cmap)
    check_grid(check, hmtx.metrics, CELL)
    widths, bearings, bounds = hmtx_mismatches(tf)
    check_charstring_metrics(tf, check, widths, bearings)
    check_tables(tf, check, bounds, tf["hmtx"].metrics, cmap)

    # every check above holds on a face whose glyphs are all blank, or
    # all drawn one cell to the right. `bounds` holds only the glyphs
    # that draw -- hmtx_mismatches skips a blank one -- so the count
    # below is ink, not cmap entries
    check_ink_inside(check, bounds, hmtx, cmap, CELL)
    inked = sum(1 for g in cmap.values() if g in bounds)
    check(inked >= 700, f"{inked} of {len(cmap)} mapped codepoints draw ink")
    # and where inside the advance: half a cell of lean lets a quarter-
    # cell mistranslation through, so the MEAN ink-centre offset over the
    # letters and digits is held near zero as well (it measures +3..+4u
    # on every weight and style; a pass that shifts the layer moves it)
    offs = [(bounds[g][0] + bounds[g][2]) / 2 - hmtx[g][0] / 2
            for cp, g in cmap.items() if g in bounds
            and (0x30 <= cp <= 0x39 or 0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A)]
    mean = sum(offs) / len(offs) if offs else 0.0
    check(offs and abs(mean) <= 25,
          f"the letters sit centred in the cell (mean ink-centre offset "
          f"{mean:+.1f}u over {len(offs)}; bound 25u)")

    cff = tf["CFF "].cff
    td = cff[cff.fontNames[0]]
    # CID-keyed as built, the Nerd Fonts variants included (the graft
    # leaves the keying alone, where font-patcher used to flatten it)
    fds = getattr(td, "FDArray", None)
    check(fds is not None and len(fds) == 1,
          f"CID-keyed with one FontDict "
          f"({[getattr(fd, 'FontName', '?') for fd in fds] if fds else 'plain CFF'})")

    for ch in "HAx=":
        check(glyph_has_hint(td.CharStrings[cmap[ord(ch)]]), f"{ch!r} carries hints")

    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
    for tag in ("calt", "liga", "ss01", "ss08", "cv99", "zero", "cv01", "ss11"):
        check(tag in tags, f"GSUB has {tag}")
    for tag in ("vert", "hwid", "fwid", "jp78", "pwid"):
        check(tag not in tags, f"GSUB has no {tag}")
    for tbl in ("vhea", "vmtx", "VORG", "DSIG"):
        check(tbl not in tf, f"no {tbl} table")
    check_gdef_marks(tf, check, cmap)
    check_gdef_classes(tf, check)
    check_line_metrics(tf, check)
    check_font_matrix(tf, check)
    check_pair_positioning(tf, check)
    check_substitution_identity(tf, check)
    check_blank_glyphs(tf, check, tf.getGlyphSet())
    check_name_composition(tf, check)
    # the Regular of THIS face's own family (GengouCodeNF-Regular.otf
    # beside a Nerd Font face): a hard-coded GengouCode-Regular.otf never
    # sits beside dist/nerd/latin, so the gate was a no-op on all ten
    # of those faces and 37 IPA letters could go (round 11, mutant B2)
    check_family_cmap(tf, check, family_reference(FONT, tf))
    check_coverage_order(tf, check)
    check_mark_class_closure(tf, check)
    check_private(tf, check)
    gpos = {fr.FeatureTag for fr in tf["GPOS"].table.FeatureList.FeatureRecord} \
        if "GPOS" in tf else set()
    check("mark" in gpos and "kern" not in gpos,
          f"GPOS keeps SCP's mark positioning, no kern ({sorted(gpos)})")
    check("STAT" in tf, "STAT present")

    check_monospace_metadata(tf, check)

    shape = make_shaper(FONT)
    gs = tf.getGlyphSet()
    # the mark gates: the anchors themselves, their coverage, and what
    # the shaper makes of them (verifylib says why there are seven)
    check_marks(tf, check, shape, gs)
    check_cells(tf, check, shape, gs, CELL)
    check_ligature_cells(tf, shape, check, gs, CELL)
    check_heights(tf, check, gs, cmap)
    check_zones(tf, check, cmap)
    check_features_work(shape, check, cmap)
    check_cases(tf, shape, check)
    check_donor_letters(tf, check, gs)
    off = {"calt": False, "liga": False}
    check(len(shape("a -> b", off)[0]) == 6, "calt/liga off leaves '->' plain")
    check(len(shape("a -> b", dict(off, ss02=True))[0]) == 5, "ss02 alone ligates '->'")

    if is_nf:
        check_nerd_font_icons(tf, check)

    print("FAILED" if check.failed else "all checks passed")
    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
