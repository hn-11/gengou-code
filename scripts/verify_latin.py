#!/usr/bin/env python3
"""Regression test for the Latin-only faces (dist/latin/Gengou-*.otf):
every ligature fires, the guards hold, everything sits on the 600 grid,
nothing CJK or full-width is left, and the metadata is the Latin font's
own. Usage: python scripts/verify_latin.py dist/latin/Gengou-Regular.otf"""

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_latin  # noqa: E402
from verify import CASES  # noqa: E402
from verifylib import (  # noqa: E402
    Checker,
    check_cells,
    check_coverage_order,
    check_features_work,
    check_gdef_marks,
    check_gdi_family_name,
    check_grid,
    check_heights,
    check_latin_repertoire,
    check_mark_class_closure,
    check_marks,
    check_monospace_metadata,
    check_name_ids,
    check_one_cell,
    check_private,
    check_stat,
    check_style_bits,
    check_tables,
    check_version_stamp,
    check_zones,
    glyph_has_hint,
    hmtx_mismatches,
    ink_spill,
    make_shaper,
    weight_name,
)

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "latin" / "Gengou-Regular.otf")
CELL = build.CELL

def main():
    tf = TTFont(str(FONT))
    check = Checker()

    name = tf["name"]
    fam = name.getDebugName(16) or name.getDebugName(1)
    # a Nerd Fonts variant ("Gengou Nerd Font Mono", nerdpatch.nf_name)
    # appends Nerd Fonts' own marker after the family — strip it before
    # matching against the family name.
    is_nf = bool(fam) and fam.endswith(" Nerd Font Mono")
    base_fam = fam[:-len(" Nerd Font Mono")] if is_nf else (fam or "")
    check(base_fam == build_latin.FAMILY, f"family name {fam!r}")
    ps_family = build_latin.PS_FAMILY + ("NFM" if is_nf else "")
    check((name.getDebugName(6) or "").startswith(ps_family + "-"),
          f"PostScript name {name.getDebugName(6)!r}")
    subfamily = name.getDebugName(17) or name.getDebugName(2) or ""
    italic = "Italic" in subfamily
    check_style_bits(tf, check, name.getDebugName(2) or "", italic)
    check_gdi_family_name(tf, check)
    check_name_ids(tf, check, (1, 2, 3, 4, 5, 6, 8, 9, 11, 13, 14))
    # the weight the face calls ITSELF, in the number Windows sorts by:
    # the PANOSE check below derives what it wants FROM usWeightClass,
    # so the pair stayed self-consistent at any value — a Regular
    # stamped 700 passed, and it is build.set_names' single line
    weight = weight_name(subfamily)
    if check(weight in build.WEIGHT_CLASS, f"subfamily names a weight ({weight!r})"):
        check(tf["OS/2"].usWeightClass == build.WEIGHT_CLASS[weight],
              f"OS/2 usWeightClass {tf['OS/2'].usWeightClass} "
              f"(want {build.WEIGHT_CLASS[weight]} for {weight})")
        check_stat(tf, check, weight, italic)
    check_version_stamp(tf, check)
    n0 = name.getDebugName(0) or ""
    check("Source Code Pro:" in n0 and "Monaspace:" in n0
          and "Source Han Sans" not in n0,
          "nameID 0 credits Source Code Pro and Monaspace, not Source Han Sans")

    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"]
    check_latin_repertoire(check, cmap)
    check_grid(check, hmtx.metrics, CELL)
    check_one_cell(tf, check, cmap, hmtx.metrics, CELL)
    widths, bearings, bounds = hmtx_mismatches(tf)
    check(not widths, f"CFF charstring widths agree with hmtx ({widths[:3]})")
    check_tables(tf, check, bounds, tf["hmtx"].metrics, cmap, codepages=True)
    check(not bearings, f"hmtx bearings are the outlines' xMin ({len(bearings)} off, "
                        f"e.g. {bearings[:3]})")

    # WHERE the ink lands, not just how wide it is (verify.py has the same
    # two; ink_spill says what the bound is): every check above holds on
    # a face whose glyphs are all blank, or all drawn one cell to the
    # right, so 'e' would sit wholly in its neighbour's column and the
    # release would ship it. `bounds` holds only the glyphs that draw —
    # hmtx_mismatches skips a blank one — so the count below is ink, not
    # cmap entries
    spill = ink_spill(bounds, lambda g: hmtx[g][0], cmap, CELL)
    check(not spill, f"every glyph's ink is inside its advance, give or take "
                     f"the lean ({len(spill)} are not, e.g. {spill[:3]})")
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
    gs, order = tf.getGlyphSet(), tf.getGlyphOrder()
    # the mark gates: the anchors themselves, their coverage, and what
    # the shaper makes of them (verifylib says why there are seven)
    check_marks(tf, check, shape, gs)
    check_cells(tf, check, shape, gs, CELL)
    check_heights(tf, check, gs, cmap)
    check_zones(tf, check, cmap)
    check_features_work(shape, check, cmap)
    on = {"calt": True, "liga": True}
    for text, want in CASES:
        if any(ord(c) > 0x2FFF for c in text):
            continue   # the CJK case belongs to the JP families
        got = len(shape(text, on)[0])
        check(got == want, f"{text!r}: {got} glyphs (want {want})")
    order = tf.getGlyphOrder()
    for seq, spec in build.LIGATURES.items():
        infos, positions = shape(f"a {seq} b", on)
        mid = positions[2:len(infos) - 2]
        adv = sum(p.x_advance for p in mid)
        # and it draws: only the count and the advance were read, so a
        # build that emptied all 61 set them as whitespace and passed
        blank = [order[i.codepoint] for i in infos[2:len(infos) - 2]
                 if order[i.codepoint] not in bounds]
        check(adv == spec["cells"] * CELL and len(infos) <= 5 and not blank,
              f"ligature {seq!r}: {len(infos)} glyphs, {adv}u"
              + (f", blank: {blank}" if blank else ""))
    off = {"calt": False, "liga": False}
    check(len(shape("a -> b", off)[0]) == 6, "calt/liga off leaves '->' plain")
    check(len(shape("a -> b", dict(off, ss02=True))[0]) == 5, "ss02 alone ligates '->'")

    if is_nf:
        import nerdpatch
        for ok, msg in nerdpatch.icon_checks(tf, nerdpatch.symbols_for_checks()):
            check(ok, msg)

    print("FAILED" if check.failed else "all checks passed")
    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
