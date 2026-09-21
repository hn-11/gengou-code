#!/usr/bin/env python3
"""Shaping regression test: every ligature fires, == stays untouched."""

import json
import os
import sys
from pathlib import Path

import pathops
from fontTools.pens.transformPen import TransformPen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
from build import FULLWIDTH, _unwrap, _unwrap_pos  # noqa: E402
from verifylib import (  # noqa: E402
    Checker,
    check_coverage_order,
    check_features_work,
    check_gdi_family_name,
    check_mark_class_closure,
    check_marks,
    check_name_ids,
    check_private,
    check_stat,
    check_style_bits,
    check_tables,
    check_version_stamp,
    glyph_has_hint,
    hmtx_mismatches,
    ink_spill,
    make_shaper,
    weight_name,
)

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "GengouJP-Regular.otf"
)
with open(ROOT / "data" / "mona_ligs.json") as _f:
    LIGATURES = json.load(_f)

# (text, expected glyph count after shaping)
CASES = [
    ("a != b", 5), ("x := 0", 5), ("a <= b", 5), ("a >= b", 5),
    ("a -> b", 5), ("a <- b", 5), ("a === b", 5), ("a !== b", 5),
    ("a == b", 5), ("a => b", 5), ("x |> f", 5), ("t :: u", 5),
    ("m >>= g", 5), ("s // c", 5),
    # context guards: an operator run longer than any ligature stays plain
    ("x <|> y", 7), ("a ->> b", 7), ("a ==> b", 7),
    # every one of these ligated before ligature_guards' prefix guards
    # were made unconditional — JavaScript's '>>>=' shaped as '>' '>' '≥'
    ("x >>>= 2", 8), ("a <=== b", 8), ("a ==!= b", 8), ("a <<<= b", 8),
    ("a <<-> b", 8), ("a <<--> b", 9), ("a <</> b", 8), ("a <~~> b", 8),
    ("a ==>> b", 8), ("a >>== b", 8),
    # ... while runs that ARE ligatures (added in 3.3) collapse
    ("a &&= b", 5), ("a ~~> b", 5), ("a <!-- b", 5), ("a && b", 5),
    ("a ++ b", 5), ("a =~ b", 5),
    ("日本語 != x", 7),
]

# the (usWinAscent, usWinDescent) copy_line_metrics pins on every JP
# face: Source Han Sans's own ascent, and a descent deep enough for the
# Latin layer's box drawing. Read from build so the two cannot drift
WIN_METRICS = build.WIN_METRICS

# what the italic faces genuinely cannot do, so the two checks that
# used to skip themselves on "the italic donor has no Greek/Cyrillic"
# -- true before this build gave them 234 letters from Source Sans --
# can stay live and fail on anything NEW. Both are the same root: the
# second donor's own features are not imported, only its outlines and
# its base anchors. docs/gengou-plan.md carries the measurements.
# Keyed by what was MEASURED, not by the probe alone: the language
# check records two quite different failures under one key -- "renders
# the other language's letterform" and "shaped into more than one
# glyph" -- so excusing the key excused either. Injecting a ccmp that
# split the Serbian b into two glyphs, a defect with nothing to do with
# the known one, passed on the italic and failed on the upright. (The
# Greek gaps live with their gate, verifylib.GREEK_ITALIC_GAP.)
LOCL_ITALIC_GAP = {("cyrl", "sr"): "unchanged"}

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
ACCENTS = "\u0300\u0301\u0302\u0303\u0304\u0306\u0307\u0308\u030c\u030a"

# suffix in the base family name -> expected (half-width, full-width) advances
FAMILY_METRICS = {
    "Term": (600, 1200),
}
DEFAULT_METRICS = (600, 1000)

# Unicode calls these Wide, they end up one cell, and neither donor has
# anything wider to offer under fwid (README, 幅の方針): six emoji only
# Source Code Pro carries at 600, five Bopomofo final letters only Source
# Han Sans carries at 600, and two Hangul tone marks Source Han Sans
# draws 250 wide that fit_to_grid centres in the cell
WIDE_AT_ONE_CELL = {0x2615, 0x302E, 0x302F, 0x31B4, 0x31B5, 0x31B6, 0x31B7,
                    0x31BB, 0x1F3B5, 0x1F3B6, 0x1F4A9, 0x1F512, 0x1F916}

# the line metrics of an English terminal font: Source Code Pro's, hhea
# and typo alike, with USE_TYPO_METRICS set (build.copy_line_metrics)
LINE_METRICS = (984, -273, 0)

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


def is_italic(tf):
    sub = subfamily_name(tf)
    if "Italic" in sub:
        return True
    if tf["post"].italicAngle:
        return True
    return bool(tf["head"].macStyle & 0x2)


def expected_metrics(tf):
    fam = family_name(tf)
    # whole-token match: "Term" is a separate word in the family name
    # ("Gengou JP Term"), never a substring of another word
    for suffix, pair in FAMILY_METRICS.items():
        if suffix in fam.split(" "):
            return pair
    return DEFAULT_METRICS


def main():
    from fontTools.ttLib import TTFont
    check = Checker()          # every check reports; none aborts the rest
    tf = TTFont(str(FONT))
    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"]
    a_adv = hmtx[cmap[ord("a")]][0] if ord("a") in cmap else 0
    cjk_adv = hmtx[cmap[0x65E5]][0] if 0x65E5 in cmap else 0
    fam = family_name(tf)
    italic = is_italic(tf)
    exp_half, exp_full = expected_metrics(tf)
    ratio = f"{cjk_adv / a_adv:.3f}" if a_adv else "?"
    print(f"family={fam!r} italic={italic} half={a_adv} full={cjk_adv} ratio={ratio}")
    check((a_adv, cjk_adv) == (exp_half, exp_full),
          f"(half, full) == ({exp_half}, {exp_full}) for family {fam!r}, "
          f"got ({a_adv}, {cjk_adv})")


    # every codepoint Gengou has is one cell in both families — the
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

    # and every Greek and Cyrillic letter, whichever donor drew it (and
    # build.narrow_letters, should one ever stand on Source Han Sans's
    # own glyph): both scripts are East_Asian_Width A, so every terminal
    # allots them one column, and a full width would paint over the
    # next character
    greek_cyrillic = {cp: hmtx[g][0] for cp, g in cmap.items()
                      if 0x370 <= cp <= 0x4FF}
    full = {cp for cp, adv in greek_cyrillic.items() if adv != exp_half}
    check(not full, f"every Greek and Cyrillic letter is one cell "
                    f"({len(greek_cyrillic)} of them; off: "
                    f"{sorted(hex(c) for c in full)})")

    # the exception to the policy: characters both donors draw one cell
    # wide although Unicode calls them Wide, so a terminal reserves two
    # columns and the glyph sits in the left one. There is no wider form
    # in either donor to offer under fwid, so the set is pinned here — an
    # upstream release that adds one has to be looked at, not absorbed
    import unicodedata
    wide_one_cell = {cp for cp, g in cmap.items()
                     if hmtx[g][0] == exp_half
                     and unicodedata.east_asian_width(chr(cp)) in ("W", "F")}
    grafted = set()
    if "Nerd Font" in fam:
        # every Nerd Fonts icon is one cell — that is what Mono means —
        # and a few of them (⚡ U+26A1) live outside the private use area
        import nerdpatch
        symbols = nerdpatch.symbols_for_checks()
        if symbols is None:
            print("skip  East-Asian-Wide exception (NF face, NF_SYMBOLS unset)")
            wide_one_cell = None
        else:
            grafted = set(symbols.getBestCmap())
    if wide_one_cell is not None:
        # a grafted icon may add to the set (every Nerd Fonts icon is one
        # cell), never take from it
        added = wide_one_cell - WIDE_AT_ONE_CELL - grafted
        gone = WIDE_AT_ONE_CELL - wide_one_cell
        check(not added and not gone,
              f"{len(WIDE_AT_ONE_CELL)} East-Asian-Wide characters at one cell "
              f"(the documented exception; added {sorted(hex(c) for c in added)}, "
              f"gone {sorted(hex(c) for c in gone)})")

    # and the other direction: Unicode's Halfwidth block is one column in
    # every terminal's width table, whatever the donor draws it at
    # (build.narrow_halfwidth)
    wide_half = sorted(cp for cp, g in cmap.items()
                       if unicodedata.east_asian_width(chr(cp)) == "H"
                       and hmtx[g][0] not in (0, exp_half))   # 0: a combining one
    check(not wide_half,
          f"every Halfwidth character is one cell "
          f"({len(wide_half)} off: {[hex(c) for c in wide_half[:5]]})")

    # nothing anywhere in the font is off the grid, cmap'd or not: a
    # feature on by default (locl, ccmp) can put a glyph on the page
    # that no codepoint reaches (fit_to_grid)
    off_grid = sorted(name for name, (adv, _lsb) in hmtx.metrics.items()
                      if adv > 0 and adv % exp_half and adv % exp_full)
    check(not off_grid,
          f"every advance in the font is on the grid ({len(hmtx.metrics)} glyphs; "
          f"off: {[(n, hmtx[n][0]) for n in off_grid[:5]]})")

    # the names the face ships under. verify_latin.py checks its side;
    # nothing checked this one, and the JP faces are what GengouJP.zip
    # carries
    name = tf["name"]
    fam = family_name(tf)
    is_nf = fam.endswith(" Nerd Font Mono")
    base_fam = fam[:-len(" Nerd Font Mono")] if is_nf else fam
    want_fam = "Gengou JP" + (" Term" if exp_full > 1000 else "")
    check(base_fam == want_fam, f"family name {fam!r} (want {want_fam!r})")
    ps_family = "GengouJP" + ("Term" if exp_full > 1000 else "") \
        + ("NFM" if is_nf else "")
    check((name.getDebugName(6) or "").startswith(ps_family + "-"),
          f"PostScript name {name.getDebugName(6)!r} (want {ps_family}-...)")
    n0 = name.getDebugName(0) or ""
    for donor in ("Source Han Sans", "Source Code Pro", "Monaspace"):
        check(donor in n0, f"nameID 0 credits {donor}")
    check_name_ids(tf, check, (1, 2, 3, 4, 5, 6, 8, 9, 11, 13, 14, 16, 17))
    # the version the face is stamped with, against the one the build
    # was asked for: one dist/ with two versions in it passed every
    # gate, and a release step that misses GENGOU_VERSION makes exactly
    # that
    check_version_stamp(tf, check, unique_id=True)
    # the weight the face calls itself, in the number Windows sorts by
    weight = weight_name(subfamily_name(tf))
    if check(weight in build.WEIGHT_CLASS,
             f"subfamily {subfamily_name(tf)!r} names a weight ({weight!r})"):
        check(tf["OS/2"].usWeightClass == build.WEIGHT_CLASS[weight],
              f"OS/2 usWeightClass {tf['OS/2'].usWeightClass} "
              f"(want {build.WEIGHT_CLASS[weight]} for {weight})")

    check_coverage_order(tf, check)
    # the Latin layer's anchors survive the graft into this face, so
    # they are worth asserting here as well as on the face they came
    # from: import_scp_marks moves every one of them by a cell, and the
    # exact-attachment check is what says the moved anchor and the moved
    # mark still meet
    check_mark_class_closure(tf, check)
    check_private(tf, check)

    # line metrics: Source Code Pro's, hhea and typo alike, USE_TYPO_METRICS
    hhea, os2 = tf["hhea"], tf["OS/2"]
    got = ((hhea.ascent, hhea.descent, hhea.lineGap),
           (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap))
    check(got == (LINE_METRICS, LINE_METRICS),
          f"line metrics {LINE_METRICS} (hhea = typo), got {got}")
    check(bool(os2.fsSelection & (1 << 7)), "USE_TYPO_METRICS set")

    # every charstring's own width (encoded against its FD's nominalWidthX)
    # must agree with hmtx: a glyph appended under one FD and re-homed to
    # another (add_latin_fd) would carry a stale width — invisible to
    # renderers, which read hmtx, but wrong for anything reading the CFF
    # (a TTFont glyph set's .width is hmtx's; the charstring's own decoded
    # width is what has to be compared)
    # -- and the left side bearing must be the outline's xMin (a CFF
    # font's lsb is nothing fontTools maintains: the Latin donors used to
    # carry SCP's default-master bearings at every weight)
    widths, bearings, bounds = hmtx_mismatches(tf)
    check(not widths, f"CFF charstring widths agree with hmtx "
                      f"({len(tf.getGlyphOrder())} glyphs, {len(widths)} off: {widths[:5]})")
    check(not bearings, f"hmtx bearings are the outlines' xMin "
                        f"({len(bearings)} off: {bearings[:5]})")

    check_tables(tf, check, bounds, hmtx, cmap, codepages=True)
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


    # and nothing paints a whole cell past its own advance: an italic
    # overhangs by design (up to 138u in the Latin layer), a glyph put on
    # a step too small for its ink would not (grid_step). The boxes are
    # the pass above's, not a second one
    # WHERE the ink lands, not just how wide it is: a width test says
    # nothing about position, and translating every kanji a whole column
    # to the right left it reporting a clean face (ink_spill says what
    # the bound is)
    spill = ink_spill(bounds, lambda name: hmtx[name][0], cmap, exp_half)
    check(not spill, f"every glyph's ink is inside its advance, give or "
                     f"take the lean ({len(spill)} are not, "
                     f"e.g. {spill[:3]})")

    # and, for the glyphs that fill their advance, WHERE inside it: the
    # bound above is half a cell, which a quarter-cell mistranslation
    # slips under (every kanji moved 250u right passed it, and in Term a
    # kanji flush against the right edge of its 1200 did too). One
    # radical (氵) is drawn 278u off centre by design, so no single glyph
    # is held to a bound; the MEAN over all of them is, and it sits
    # within 2u of the advance centre for kanji and 8u for kana (spacing
    # glyphs; +5.6 Bold to +7.3 Light). A pass that shifts the layer
    # moves the mean with it
    def mean_off_centre(lo, hi):
        # spacing glyphs only: a combining mark (゛゜ U+3099/309A) has no
        # advance to be centred in, and its −360u would pull the mean
        offs = [(box[0] + box[2]) / 2 - hmtx[name][0] / 2
                for cp, name in cmap.items() if lo <= cp <= hi and hmtx[name][0] > 0
                for box in (bounds.get(name),) if box is not None]
        return sum(offs) / len(offs) if offs else 0.0

    centred = {"kanji": mean_off_centre(0x4E00, 0x9FFF),
               "kana": mean_off_centre(0x3041, 0x30FF)}
    check(all(abs(v) <= 25 for v in centred.values()),
          f"the Japanese layer is centred in its advance (mean ink-centre "
          f"offset {', '.join(f'{k} {v:+.1f}u' for k, v in centred.items())}; "
          f"bound 25u)")

    # the repertoire, and DRAWN, not merely mapped: nothing here counted
    # what the face covers, so one that lost 25,000 cmap entries — or
    # kept every one of them and emptied the outlines — was a
    # well-formed, correctly named, correctly sized asset that rendered
    # all Japanese as whitespace and passed every gate. `bounds` holds
    # the glyphs that draw (hmtx_mismatches skips a blank one), so this
    # counts ink. The face maps 17,355 codepoints — Source Han Sans
    # JP's 16,742 and Gengou's 1,335 — 12,746 of them kanji in the
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

    sub = subfamily_name(tf)
    check_style_bits(tf, check, sub, italic)
    check_gdi_family_name(tf, check)

    shape_infos = make_shaper(FONT)
    # the exact-attachment half of the mark gates (the anchor half runs
    # above, before a shaper exists): the moved anchor and the moved
    # mark still meet
    check_marks(tf, check, shape_infos, tf.getGlyphSet())

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
    if hasattr(hint_td, "FDArray") and ord("H") in cmap:
        fd = hint_td.FDSelect[tf.getGlyphID(cmap[ord("H")])]
        private = hint_td.FDArray[fd].Private
        blues = list(getattr(private, "BlueValues", ()) or ())
        os2m = tf["OS/2"]
        wanted = [os2m.sxHeight, os2m.sCapHeight]
        near = [any(abs(b - v) <= 14 for b in blues) for v in wanted]
        check(all(near) and getattr(private, "StdHW", 0),
              f"the Latin FontDict's zones are this face's "
              f"(BlueValues {blues}, x-height {os2m.sxHeight}, "
              f"cap {os2m.sCapHeight}, StdHW {getattr(private, 'StdHW', None)})")


    # the two-cell forms under fwid: the arrow redrawn from the ligature,
    # ≠ and ─ from Source Han Sans, Ａ through Source Han Sans's own fwid
    # form of the proportional A the one-cell A replaced
    fwid_probes = "\u2192\u2260\u2500A"
    off_fwid = {}
    for ch in fwid_probes:
        _infos, positions = shape_infos(ch, {"fwid": True})
        got = positions[0].x_advance if positions else None
        if got != exp_full:
            off_fwid[ch] = got
    check(not off_fwid, f"fwid restores the full-width forms "
                        f"({len(fwid_probes)} probes; off: {off_fwid})")


    def shape_len(text, feats):
        return len(shape_infos(text, feats)[0])

    for text, nglyphs in CASES:
        got = shape_len(text, {"calt": True, "liga": True})
        ok = got == nglyphs
        check(ok, f"{text!r}: {got} glyphs (want {nglyphs})")

    check_features_work(shape_infos, check, cmap)
    # a combining mark's variant (cv11: the Cyrillic breve for U+0306, in
    # the upright faces) must stay a 0-advance mark, not become a spacing
    # glyph that takes a cell when selected
    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}

    # a CID-keyed font's CIDCount must cover every CID it uses: cffsubr
    # takes it from the last charset entry, and Source Han Sans's space
    # is sparse (build.restore_cid_count)
    cff = tf["CFF "].cff
    td = cff[cff.fontNames[0]]
    if hasattr(td, "ROS"):      # ROS is what makes a CFF CID-keyed
        from build import highest_cid
        top = highest_cid(td)
        check(td.CIDCount > top,
              f"CFF CIDCount {td.CIDCount} covers every CID (highest {top})")

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
    for tag in ("fwid", "hwid", "aalt", "dlig", "ruby",
                "jp78", "jp83", "jp90", "nlck", "locl", "ccmp"):
        check(tag in tags, f"GSUB carries {tag}")
    for tag in ("vkrn", "vhal", "vpal"):
        check(tag in gpos, f"GPOS carries {tag} ({sorted(gpos)})")
    for text, want in (("あて", exp_full), ("いて", exp_full)):
        _infos, positions = shape_infos(text, {})
        check(positions[0].x_advance == want,
              f"{text!r} shapes on the grid ({positions[0].x_advance}u, want {want})")

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

    # 4-cell ligature: any spec whose "cells" == 4 must shape to a single
    # glyph whose advance is exactly 4x the half-width cell
    wide_seqs = [seq for seq, spec in LIGATURES.items() if spec["cells"] == 4]
    for seq in wide_seqs:
        infos, positions = shape_infos(seq, {"calt": True, "liga": True})
        ok = len(infos) == 1 and positions[0].x_advance == 4 * a_adv
        got_adv = positions[0].x_advance if positions else None
        got_n = len(infos)
        check(ok, f"{seq!r} 4-cell ligature: "
                  f"{got_n} glyph(s), advance={got_adv} (want 1 glyph, {4 * a_adv})")

    # every declared ligature must actually fire, at its declared cell width.
    # Sequences are embedded as "a <seq> b" (the same robust padding used by
    # CASES above) so calt's contextual rules see real neighbors/boundaries.
    # "a" and " " never participate in these ligature rules, so the shaped
    # output is: [a][space][<ligature glyph(s)>][space][b]. Most entries
    # collapse the whole sequence into a single ligature glyph (5 glyphs
    # total, ligature at index 2), but a few (":=", "::") are declared as
    # multi-glyph substitutions ("glyphs" lists more than one component) and
    # may shape to more than one output glyph in that middle span. Rather
    # than hard-coding "exactly 5", sum the advances of whatever sits
    # between the fixed 2-glyph prefix ("a ") and 2-glyph suffix (" b") and
    # compare that to cells * half_width_cell -- this covers both the
    # single-glyph and multi-glyph-component cases without special-casing.
    lig_failed = 0
    lig_fail_lines = []
    lig_order = tf.getGlyphOrder()
    for seq, spec in LIGATURES.items():
        text = f"a {seq} b"
        infos, positions = shape_infos(text, {"calt": True, "liga": True})
        want_adv = spec["cells"] * a_adv
        n = len(infos)
        mid = positions[2:-2] if n > 4 else []
        got_adv = sum(p.x_advance for p in mid) if mid else None
        # and it has to DRAW: nothing here read the outline, so a build
        # that emptied 50 of the 61 set '!=' as whitespace and passed
        blank = [lig_order[i.codepoint] for i in infos[2:-2]
                 if lig_order[i.codepoint] not in bounds]
        ok = n > 4 and got_adv == want_adv and not blank
        if not ok:
            lig_failed += 1
            lig_fail_lines.append(
                f"FAIL ligature {seq!r} ({spec['cells']} cells): "
                f"{n} glyphs total, mid_advance={got_adv} (want {want_adv})"
                + (f", blank: {blank}" if blank else ""))
    if lig_failed:
        for line in lig_fail_lines:
            print(line)
        check.failed = True
    else:
        print(f"ok   all {len(LIGATURES)} ligatures shape at declared "
              f"widths and draw")

    # standalone operators redrawn from Monaspace must match the ligatures
    # cut from the same instance: every contour of the lone glyph has a
    # counterpart in the ligature at the same y extent (ligatures span
    # more cells, so only y is comparable). '==' '<<' '>>' '||' '..' '!!'
    # ';;' repeat the glyph outright; '~' ('~>' is a fused wave-arrow),
    # ':' ('::' is the raised colon.case) and '&' (no '&&' ligature) have
    # no such ligature and are not checked.
    from build import (
        MONA_STANDALONE,
        WEIGHT_CLASS,
        _contour_bounds,
        _record_contours,
        bar_thickness,
        panose_weight,
    )
    glyph_order = tf.getGlyphOrder()

    def y_rows(gname):
        return sorted((round(b[1]), round(b[3])) for b in
                      _contour_bounds(_record_contours(tf, gname)))

    def lig_glyph(text):
        infos, _ = shape_infos(text, {"calt": True, "liga": True})
        return glyph_order[infos[2].codepoint]

    pairs = {"=": "a == b", "<": "a << b", ">": "a >> b", "|": "a || b",
             ".": "a .. b", "!": "a !! b", ";": "a ;; b"}
    for ch in MONA_STANDALONE:
        if ch not in pairs:
            continue
        rows_ch, rows_lig = y_rows(cmap[ord(ch)]), y_rows(lig_glyph(pairs[ch]))
        ok = bool(rows_ch) and all(
            any(abs(a - c) <= 2 and abs(b - d) <= 2 for c, d in rows_lig)
            for a, b in rows_ch)
        check(ok, f"{ch!r} rows {rows_ch} "
                  f"found in {pairs[ch].split()[1]!r} {rows_lig}")

    # the ligature-paired symbols (← → ≠ … etc.): one cell by default in
    # both families, the full-width form under fwid; the full-width
    # horizontal arrows are cut from the ligature they pair with
    # (ARROW_SOURCE): same vertical extent, within 2u
    from build import ARROW_SOURCE, ARROWS_H, ARROWS_V, MONA_AMBIGUOUS

    def advance_of(text, feats):
        _, positions = shape_infos(text, feats)
        return positions[0].x_advance

    full_adv = expected_metrics(tf)[1]
    for ch in MONA_AMBIGUOUS:
        got_default, got_alt = advance_of(ch, {}), advance_of(ch, {"fwid": True})
        check(got_default == a_adv and got_alt == full_adv,
              f"{ch!r} default {got_default} (want {a_adv}), "
              f"fwid {got_alt} (want {full_adv})")

    def extent(rows):
        # a blank glyph has no rows: report it, do not abort the rest
        if not rows:
            return None, None
        return min(a for a, _ in rows), max(b for _, b in rows)
    for ch in ARROWS_H:
        seq = ARROW_SOURCE[ch][0]
        lig_ymin, lig_ymax = extent(y_rows(lig_glyph(f"a {seq} b")))
        infos, _ = shape_infos(ch, {"fwid": True})
        ymin, ymax = extent(y_rows(glyph_order[infos[0].codepoint]))
        ok = (None not in (ymin, lig_ymin)
              and abs(ymin - lig_ymin) <= 2 and abs(ymax - lig_ymax) <= 2)
        check(ok, f"{ch!r} (fwid) y extent {ymin}..{ymax} "
                  f"vs {seq!r} {lig_ymin}..{lig_ymax}")

    # ... and each one sits centred in that advance with its ink inside
    # it. stretch_arrows used to centre the DE-SLANTED outline, and the
    # box of a sheared shape is not the shear of its box: in the italic
    # faces every arrow came out tan(11°) of its own height to the right
    # — 67u off centre, ⇐ 56u into the next cell, ↑ 72u away from ↓
    from fontTools.pens.boundsPen import BoundsPen
    arrow_gs = tf.getGlyphSet()
    off_centre = {}
    for ch in ARROWS_H + ARROWS_V:
        infos, _ = shape_infos(ch, {"fwid": True})
        name = glyph_order[infos[0].codepoint]
        adv = tf["hmtx"][name][0]
        pen = BoundsPen(arrow_gs)
        arrow_gs[name].draw(pen)
        box = pen.bounds
        if box is None:
            off_centre[ch] = "blank"
        elif (abs((box[0] + box[2]) / 2 - adv / 2) > 2
              or box[0] < -1 or box[2] > adv + 1):
            off_centre[ch] = (round(box[0]), round(box[2]), adv)
    check(not off_centre, f"every fwid arrow is centred inside its advance "
                          f"({len(ARROWS_H + ARROWS_V)} probes; off: {off_centre})")

    # characters drawn to TILE: a run of them must show no seam, in
    # either family and at either width. Term widens a full width from
    # 1000 to 1200, and centring the outline there left 100u of white at
    # every cell join — a rule of ＿ came out dashed and █ striped
    # (build.widen_fullwidth lengthens them instead)
    seam = {}
    for ch in TILING:
        for feats in ({}, {"fwid": True}):
            infos, _ = shape_infos(ch, feats)
            name = glyph_order[infos[0].codepoint]
            adv = tf["hmtx"][name][0]
            pen = BoundsPen(arrow_gs)
            arrow_gs[name].draw(pen)
            box = pen.bounds
            if box is None or box[0] > 2 or box[2] < adv - 2:
                seam[ch, bool(feats)] = None if box is None else (
                    round(box[0]), round(box[2]), adv)
    check(not seam, f"every tiling character spans its whole advance "
                    f"({2 * len(TILING)} probes; off: {seam})")

    # every box-drawing and block character draws: the probes below
    # name fourteen of them, and a build that emptied any of the other
    # 146 — or their full-width forms — shipped a font that set a
    # terminal frame as whitespace and passed every gate
    blank = []
    for cp in range(0x2500, 0x25A0):
        if cp not in cmap:
            continue
        infos, _p = shape_infos(chr(cp), {"fwid": True})
        for name in (cmap[cp], glyph_order[infos[0].codepoint]):
            if name not in bounds and name not in blank:
                blank.append(name)
    check(not blank, f"every box-drawing and block glyph draws "
                     f"({2 * 160} probes; blank: {blank[:6]})")

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
        arrow_gs[name].draw(path.getPen())
        return sorted((c.bounds[axis], c.bounds[axis + 2])
                      for c in path.contours)

    line_pitch = hhea.ascent - hhea.descent + hhea.lineGap
    pattern = {}
    for block, axis in (((0x2504, 0x2505, 0x2508, 0x2509, 0x254C, 0x254D), 0),
                        ((0x2506, 0x2507, 0x250A, 0x250B, 0x254E, 0x254F), 1)):
        for cp in block:
            if cp not in cmap:
                continue
            # down the page, only the full-width forms: the one-cell
            # defaults are Source Code Pro's own drawing, and its
            # vertical dashes do not repeat at this line pitch either
            # (┆ measures 134 inside against 191 across, in the donor
            # and here alike) — that is the donor's design, not ours
            for feats in (({"fwid": True},) if axis else ({}, {"fwid": True})):
                infos, _ = shape_infos(chr(cp), feats)
                name = glyph_order[infos[0].codepoint]
                pieces = dashes(name, axis)
                if len(pieces) < 2:
                    continue
                pitch = hmtx[name][0] if axis == 0 else line_pitch
                inside = [pieces[i + 1][0] - pieces[i][1]
                          for i in range(len(pieces) - 1)]
                join = pieces[0][0] + pitch - pieces[-1][1]
                if max(abs(g - join) for g in inside) > 3:
                    pattern[chr(cp), bool(feats)] = (
                        [round(g) for g in inside], round(join))
    check(not pattern, f"a dashed rule keeps its pattern across the join "
                       f"(inside vs across: {pattern})")

    # and the same thing DOWN the page. A line is 1257 units tall here
    # (Source Code Pro's metrics on a face whose Japanese is drawn to a
    # 1000-unit em), so a full-width rule that stops at its own em
    # leaves 257 units of white at every line: a column of fwid │ broke
    # at each one and a run of fwid █ came out striped, while the
    # one-cell defaults — which the Latin donor draws -400..1000 — did
    # not (build.tile_vertically)
    def spans_line(box):
        return box is not None and box[1] <= hhea.descent and box[3] >= hhea.ascent

    vseam = {}
    for ch in VTILING:
        for feats in ({}, {"fwid": True}):
            infos, _ = shape_infos(ch, feats)
            pen = BoundsPen(arrow_gs)
            arrow_gs[glyph_order[infos[0].codepoint]].draw(pen)
            if not spans_line(pen.bounds):
                vseam[ch, bool(feats)] = None if pen.bounds is None else (
                    round(pen.bounds[1]), round(pen.bounds[3]))
    check(not vseam, f"every vertical rule spans the whole line "
                     f"({hhea.ascent}..{hhea.descent}; "
                     f"{2 * len(VTILING)} probes; off: {vseam})")

    # not only those four, and edge by edge: over the whole box-drawing
    # and block range, a character whose one-cell default reaches the
    # top or the bottom of the line must have a full-width form that
    # reaches it too. Whole-span probes miss the corners — ╭ runs down
    # and right, so only its foot is at the line's floor, and the four
    # arcs ╭ ╮ ╯ ╰ were the ones left 137 units short at every line
    # while ┌ ┐ ┘ └ joined
    short, pairs = {}, 0
    for cp in range(0x2500, 0x25A0):
        if cp not in cmap:
            continue
        one = BoundsPen(arrow_gs)
        arrow_gs[cmap[cp]].draw(one)
        infos, _ = shape_infos(chr(cp), {"fwid": True})
        full = glyph_order[infos[0].codepoint]
        if one.bounds is None or full == cmap[cp]:
            continue          # blank, or no separate full-width form
        wide = BoundsPen(arrow_gs)
        arrow_gs[full].draw(wide)
        pairs += 1
        if wide.bounds is None or (
                one.bounds[1] <= hhea.descent < wide.bounds[1]
                or one.bounds[3] >= hhea.ascent > wide.bounds[3]):
            short[chr(cp)] = None if wide.bounds is None else (
                round(wide.bounds[1]), round(wide.bounds[3]))
    check(not short, f"a full-width form reaches the line's edge "
                     f"wherever its one-cell default does ({pairs} pairs; "
                     f"off: {short})")

    # and a rounded corner is the same corner: Source Han Sans draws ╭
    # on exactly ┌'s bounding box, so the two must still agree once the
    # tiling passes are done. They did not — the arc's leg bends, which
    # read as a curve rather than a rule, so it was neither lengthened
    # down the page nor extruded sideways in Term, where it came out
    # stretched instead and its stem stood 48 units against every other
    # fwid vertical's 40
    corners = {}
    for arc, corner in zip("\u256d\u256e\u256f\u2570", "\u250c\u2510\u2518\u2514"):
        boxes = []
        for ch in (arc, corner):
            if ord(ch) not in cmap:
                break
            infos, _ = shape_infos(ch, {"fwid": True})
            pen = BoundsPen(arrow_gs)
            arrow_gs[glyph_order[infos[0].codepoint]].draw(pen)
            boxes.append(pen.bounds)
        if len(boxes) == 2 and (None in boxes or max(
                abs(a - b) for a, b in zip(*boxes)) > 2):
            corners[arc + corner] = [None if b is None else
                                     tuple(round(v) for v in b) for b in boxes]
    check(not corners, f"a rounded corner keeps its corner's box "
                       f"(off: {corners})")

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
        pen = BoundsPen(arrow_gs)
        arrow_gs[name].draw(pen)
        box = pen.bounds
        joint = None if box is None else box[0] + adv - box[2]
        if joint is None or joint > adv // 16:
            joints[ch] = joint if joint is None else round(joint)
    check(not joints, f"the two-em and three-em dashes butt together "
                      f"(joint over a sixteenth of the advance: {joints})")

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
                pen = BoundsPen(arrow_gs)
                arrow_gs[name].draw(pen)
                boxes.append(pen.bounds)
            if boxes[0] and boxes[1] and boxes[0][3] > boxes[1][1]:
                ccmp[base + mark] = (round(boxes[0][3]), round(boxes[1][1]))
    check(not ccmp, f"the donor's ccmp composes ({probes} probes; "
                    f"off: {ccmp})")

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
                    pen = BoundsPen(gs)
                    gs[order[info.codepoint]].draw(pen)
                    feet.append(None if pen.bounds is None
                                else pen.bounds[1] + pos.y_offset)
                above += None not in feet and feet[2] >= feet[1]
        return above, probes, lifted

    above, probes, lifted = stacked(shape_infos, arrow_gs, glyph_order, cmap)
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

    # the lift is read through GDEF: 'mkmk' asks which marks it may
    # stack on by the mark attachment class in its lookup flag, and a
    # font that carries the lookup without the classes stacks nothing
    classes = getattr(getattr(tf.get("GDEF"), "table", None),
                      "MarkAttachClassDef", None)
    filtered = [lk.LookupFlag >> 8 for lk in tf["GPOS"].table.LookupList.Lookup
                if lk.LookupFlag >> 8]
    named = sorted(set(classes.classDefs.values())) if classes else []
    check(filtered and classes is not None and set(filtered) <= set(named),
          f"GDEF names the mark classes GPOS filters on "
          f"({sorted(set(filtered))}; GDEF has {named})")

    # a voicing mark over a HALF-width kana must not be drawn into it.
    # The mark is registered to the cell before it, and Term widens the
    # full-width cell only — moving the mark with it put 100 units of ｶ
    # ﾈ ｳ under the dakuten (build.realign_halfwidth_marks)

    def ink_overlap(text):
        paths, pen_x = [], 0
        infos, positions = shape_infos(text, {})
        if len(infos) != 2:
            return 0
        for info, pos in zip(infos, positions):
            path = pathops.Path()
            arrow_gs[glyph_order[info.codepoint]].draw(path.getPen())
            moved = pathops.Path()
            path.draw(TransformPen(moved.getPen(),
                                   (1, 0, 0, 1, pen_x + pos.x_offset, pos.y_offset)))
            paths.append(moved)
            pen_x += pos.x_advance
        return abs(pathops.op(paths[0], paths[1],
                              pathops.PathOp.INTERSECTION).area)

    # a bold stroke touches on its own: Source Han Sans Bold shares
    # 2,844 square units between ﾈ and its dakuten and 4,647 with the
    # handakuten, where Normal shares 1,077 and 1,569 — so "no ink at
    # all" is a Regular-only bound, and it failed every weight from
    # Medium up. Ours share at most 176 (the half-width kana is a whole
    # cell here, not Source Han Sans's 500), and the regression this
    # catches shared up to 4,651
    budget = build.CELL * build.CELL // 400
    voiced = {}
    for kana in "\uff76\uff88\uff73":
        for mark in "\u3099\u309a":
            if ord(kana) not in cmap or ord(mark) not in cmap:
                continue
            area = ink_overlap(kana + mark)
            if area > budget:
                voiced[kana + mark] = round(area)
    check(not voiced, f"a voicing mark clears the half-width kana it "
                      f"marks (over {budget} square units of shared ink: "
                      f"{voiced})")

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

    # the two double-span marks straddle the pair they join: Source
    # Code Pro pulls them half a cell left in GPOS, and dropping that
    # with the advance beside it centred the tie on the first letter —
    # or, with no placement at all, 154 units left of where the line
    # starts
    def placed(text, feats=None):
        """[(xMin, xMax), ...] where a run's ink actually lands: the
        pen's own advance, plus what GPOS moves each glyph by."""
        infos, positions = shape_infos(text, feats or {})
        out, pen_x = [], 0
        for info, pos in zip(infos, positions):
            pen = BoundsPen(arrow_gs)
            arrow_gs[glyph_order[info.codepoint]].draw(pen)
            out.append(None if pen.bounds is None else
                       (pen.bounds[0] + pen_x + pos.x_offset,
                        pen.bounds[2] + pen_x + pos.x_offset))
            pen_x += pos.x_advance
        return out


    # and an enclosing mark stays around the character it encloses: it
    # hangs a full width LEFT of the origin, so the Term widening has to
    # take it further left, not leave it on the 1000-unit cell
    around = {}
    for base in "\u56fd\u4e00":
        if ord(base) not in cmap or 0x20DD not in cmap:
            continue
        boxes = placed(base + "\u20dd")
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
        pen = BoundsPen(arrow_gs)
        arrow_gs[glyph_order[infos[-1].codepoint]].draw(pen)
        if pen.bounds is None or positions[-1].x_advance:
            return None
        return round((pen.bounds[0] + pen.bounds[2]) / 2
                     + positions[-1].x_offset)

    after_lig = {}
    for mark in ("\u20dd", "\u3099"):
        if ord(mark[0]) not in cmap:
            continue
        want = mark_offset("A" + mark)     # one cell, the settled case
        # U+F120 is a Nerd Fonts icon: one cell, and appended to the
        # face AFTER the widening, so it was in no backtrack coverage
        # and every one of the 10,402 icons kept the -100 in the Term
        # NFM faces (U+F120 + U+20DD drew the ring at -465..465 where
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
            pen = BoundsPen(arrow_gs)
            arrow_gs[glyph_order[info.codepoint]].draw(pen)
            boxes.append(None if pen.bounds is None else
                         (pen.bounds[0] + pos.x_offset,
                          pen.bounds[2] + pos.x_offset))
        if None in boxes:
            column[base] = None
            continue
        off = (boxes[1][0] + boxes[1][1]) / 2 - (boxes[0][0] + boxes[0][1]) / 2
        if abs(off) > 5:      # as above: upstream's own 一 is 2.5 off
            column[base] = (round(off, 1), tuple(round(v) for v in boxes[1]))
    check(not column, f"an enclosing mark stays around its character "
                      f"down a column (off centre: {column})")

    # and where it lands must not depend on how many marks come
    # before it: the rule that gives Term's shift back over a
    # half-width base reads the glyph in front, and a mark is 0 wide,
    # so with one backtrack only the FIRST mark of a stack was put back
    stacked_marks = {}
    for base in "\uff76\uff88AB":
        for between in ("\u3099", "\u0301", "\u3099\u0301", "\u0300\u0301"):
            if any(ord(c) not in cmap for c in base + between + "\u20dd"):
                continue
            alone = placed(base + "\u20dd")
            after = placed(base + between + "\u20dd")
            if len(alone) != 2 or None in alone or None in after:
                continue
            if max(abs(a - b) for a, b in zip(alone[1], after[-1])) > 2:
                stacked_marks[base + between] = (
                    tuple(round(v) for v in alone[1]),
                    tuple(round(v) for v in after[-1]))
    check(not stacked_marks, f"a mark lands the same behind other marks as "
                             f"behind none (off: {stacked_marks})")

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
            pen = BoundsPen(arrow_gs)
            arrow_gs[glyph_order[infos[1].codepoint]].draw(pen)
            if pen.bounds is None:
                continue
            # the vertical column is ±500, and Source Han Sans's own
            # tone marks sit right against its edge: at Bold U+302C
            # reaches 513 and the dakuten 505 upstream, identically, so
            # the bound is the stroke's own growth and not zero. The
            # regression it catches is 100 units
            column = FULLWIDTH / 2
            slack = FULLWIDTH // 20
            lo = pen.bounds[0] + positions[1].x_offset
            hi = pen.bounds[2] + positions[1].x_offset
            if lo < -column - slack or hi > column + slack:
                outside[base + mark] = (round(lo), round(hi))
    check(not outside, f"a mark stays on the column after a half-width "
                       f"base (outside ±{FULLWIDTH // 2 + FULLWIDTH // 20}: "
                       f"{outside})")

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

    # a full-width base carries its own anchors: Source Han Sans hangs
    # the Bopomofo tone marks off ㄓ, and widening it to two cells moves
    # its ink 100u right — leave the anchor behind (shift_anchors) and
    # the mark stands over the letter instead of after it
    tone = {}
    for base, mark in (("\u3113", "\u02ea"), ("\u3113", "\u02eb")):
        if ord(base) not in cmap or ord(mark) not in cmap:
            continue
        boxes = placed(base + mark)
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
        area = ink_overlap(base + mark)
        boxes = placed(base + mark)
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

    # the two imports need each other: SCP's variant features have rules
    # on what ccmp composes (cv02's single-storey g̃) and ccmp has rules
    # on what the variants draw (the ogonek under cv04's serifed i). A
    # variant that cannot reach a composed glyph leaves the default
    # design on the page with the feature on
    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
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

    # ＿ and ￣ are full width in the default too, so there is no
    # one-cell form for a full-width one to match: lengthening them down
    # the page drew the 41-unit rule as a 320-unit slab (Source Han Sans
    # draws it 36 to 50 units through the weights)
    slabs = {}
    for ch in "\uFF3F\uFFE3":
        if ord(ch) not in cmap:
            continue
        pen = BoundsPen(arrow_gs)
        arrow_gs[cmap[ord(ch)]].draw(pen)
        box = pen.bounds
        if box is None or box[3] - box[1] > 100:
            slabs[ch] = None if box is None else round(box[3] - box[1])
    check(not slabs, f"the full-width low line and macron are rules, not "
                     f"slabs (over 100u tall: {slabs})")

    # the block elements are fractions of the line, and under fwid they
    # are Source Han Sans's, drawn to a 1000-unit em: mapped onto the
    # 1400-unit band they keep their eighths, but EXTRUDED to it they
    # all gained the same 280 units and ▁ drew 29% of the cell where it
    # means an eighth
    def fwid_box(ch):
        infos, _ = shape_infos(ch, {"fwid": True})
        pen = BoundsPen(arrow_gs)
        arrow_gs[glyph_order[infos[0].codepoint]].draw(pen)
        return pen.bounds

    ramp = {}
    full = fwid_box("\u2588")
    if full is not None:
        lo, hi = full[1], full[3]
        band = hi - lo
        # ▁ through █ grow UP from the floor an eighth at a time; ▔ and
        # ▀ hang from the ceiling. Height alone is not the character: a
        # ▀ drawn at the floor is a ▄, and measured by height only it
        # passed
        for ch, want, anchor in (
                *((chr(0x2580 + k), band * k / 8, "bottom") for k in range(1, 9)),
                ("\u2594", band / 8, "top"),     # ▔, an eighth from the top
                ("\u2580", band / 2, "top")):    # ▀, the other half of ▄
            box = fwid_box(ch)
            edge = None if box is None else (box[1] - lo if anchor == "bottom"
                                             else hi - box[3])
            if box is None or abs((box[3] - box[1]) - want) > 2 or abs(edge) > 2:
                ramp[ch] = None if box is None else (round(box[1]), round(box[3]))
        # the same series across the cell: ▏ through ▉ grow right from
        # x = 0 an eighth at a time, ▐ and ▕ hang off the right edge
        def fwid_adv(ch):
            infos, _ = shape_infos(ch, {"fwid": True})
            return hmtx[glyph_order[infos[0].codepoint]][0]

        for k in range(1, 8):
            ch = chr(0x2590 - k)       # ▏ (U+258F) through ▉ (U+2589)
            box, adv = fwid_box(ch), fwid_adv(ch)
            if box is None or abs((box[2] - box[0]) - adv * k / 8) > 2 \
                    or abs(box[0]) > 2:
                ramp[ch] = None if box is None else (round(box[0]), round(box[2]))
        for ch, part in (("\u2590", 1 / 2), ("\u2595", 1 / 8)):
            box, adv = fwid_box(ch), fwid_adv(ch)
            if box is None or abs((box[2] - box[0]) - adv * part) > 2 \
                    or abs(box[2] - adv) > 2:
                ramp[ch] = None if box is None else (round(box[0]), round(box[2]))
        # and the quadrants sit in their own quarter of the cell
        for ch, top, left in (("\u2598", True, True), ("\u259D", True, False),
                              ("\u2596", False, True), ("\u2597", False, False)):
            box = fwid_box(ch)
            adv = hmtx[glyph_order[shape_infos(ch, {"fwid": True})[0][0].codepoint]][0]
            want = ((lo + hi) / 2 if top else lo, hi if top else (lo + hi) / 2,
                    0 if left else adv / 2, adv / 2 if left else adv)
            got = None if box is None else (box[1], box[3], box[0], box[2])
            if got is None or max(abs(a - b) for a, b in zip(got, want)) > 2:
                ramp[ch] = None if got is None else tuple(round(v) for v in got)
    check(not ramp, f"the fwid block elements step an eighth of the line "
                    f"at a time, from the right edge (off: {ramp})")

    # ... and nothing ELSE grew with the advance. A Source Han Sans glyph
    # is drawn inside its 1000 em, so in Term, where the advance is 1200,
    # any of them outside the tiling blocks with more than 1000 of ink
    # was stretched — which is how Ⅷ, ㌄ and a Bold 孰 shipped 20% wide
    # for two rounds while the ten tiling probes above stayed green. The
    # glyphs examined are the ones a reader can reach: the cmap, closed
    # over every one-to-one and alternate substitution in the font. A
    # single fwid hop is not enough — the vertical forms ｜ and ⎰ take
    # under vert, the old shapes under jp78/jp83, and every aalt
    # alternate are 1200 wide too, and a pre-round-33 Term Bold stretched
    # six of them where the check saw four. The closure leaves out the
    # Latin donor's two-cell ligatures, which are 1200 wide in both
    # families and reached only through ligature lookups. (A CID
    # threshold cannot do any of this: Source Han Sans's own CIDs are
    # sparse and run to 65497, and a first cut that used one never
    # looked at 60% of the kanji.)
    if exp_full > 1000:
        from build import tiling_glyphs
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

    # stroke weight: the Latin is Source Code Pro's named instance for
    # this weight, so its '=' bar must measure the VF's at that wght
    # (SCP_VF_U / SCP_VF_I when set), and the Japanese face is the Source
    # Han Sans weight whose '＝' bar matches it (build.FACES: within 4u)
    weight = sub[:-len(" Italic")] if sub.endswith(" Italic") else sub
    if weight == "Italic":   # "Regular Italic" collapses to "Italic"
        weight = "Regular"
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

    # imported outlines must be overlap-free (VF instancing leaves seams)
    gs = tf.getGlyphSet()
    glyph_order = tf.getGlyphOrder()

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

    # width metadata: declared monospaced (set_monospace_metadata — what
    # Windows Terminal's picker and GDI's FIXED_PITCH filter read; Source
    # Han Sans's own 0/0 hid it there), xAvgCharWidth per OS/2 v3+ (mean of every
    # non-zero advance), x/cap height measured on the face's own glyphs.
    fixed = tf["post"].isFixedPitch
    ok = fixed == 1
    check(ok, f"post.isFixedPitch == 1, got {fixed}")

    panose = tf["OS/2"].panose
    check(panose.bProportion == 9,
          f"OS/2 PANOSE proportion == 9 (monospaced), got {panose.bProportion}")
    want_pw = panose_weight(tf["OS/2"].usWeightClass)
    check(panose.bWeight == want_pw,
          f"OS/2 PANOSE weight {panose.bWeight} matches usWeightClass "
          f"{tf['OS/2'].usWeightClass} (want {want_pw})")

    from fontTools.misc.roundTools import otRound
    widths = [adv for adv, _ in tf["hmtx"].metrics.values() if adv > 0]
    avg_w = tf["OS/2"].xAvgCharWidth
    want_avg = otRound(sum(widths) / len(widths))
    ok = avg_w == want_avg
    check(ok, f"OS/2.xAvgCharWidth is the mean non-zero advance ({avg_w} vs {want_avg})")

    from fontTools.pens.boundsPen import BoundsPen
    gs = tf.getGlyphSet()
    for attr, ch in (("sxHeight", "x"), ("sCapHeight", "H")):
        pen = BoundsPen(gs)
        gs[cmap[ord(ch)]].draw(pen)
        got, want = getattr(tf["OS/2"], attr), round(pen.bounds[3])
        ok = got == want
        check(ok, f"OS/2.{attr} == top of {ch!r} ({got} vs {want})")

    # line-metrics sanity: hhea and OS/2 vertical metrics must be nonzero
    # and internally consistent
    hhea = tf["hhea"]
    os2 = tf["OS/2"]
    ok = hhea.ascent > 0 and hhea.descent < 0
    check(ok, f"hhea ascent/descent sane "
              f"(ascent={hhea.ascent}, descent={hhea.descent})")

    ok = os2.sTypoAscender > 0 and os2.sTypoDescender < 0
    check(ok, f"OS/2 typo metrics sane "
              f"(typoAsc={os2.sTypoAscender}, typoDesc={os2.sTypoDescender})")
    # pinned, not merely positive (copy_line_metrics, README 行の高さ).
    # They are the GDI line height as much as a clipping bound, and this
    # family's ink reaches 1808/-1048 — covering it would give a 2856u
    # line, more than twice the 1257u every renderer that honours
    # USE_TYPO_METRICS uses. The descent does cover the Latin layer's
    # box drawing (-400) and shade blocks (-454); docs/gengou-plan.md
    # carries the measurement and the two codepoints left outside
    check((os2.usWinAscent, os2.usWinDescent) == WIN_METRICS,
          f"win metrics are the pinned {WIN_METRICS}, got "
          f"({os2.usWinAscent}, {os2.usWinDescent})")
    # a terminal gives a codepoint no font in the fallback chain covers
    # one column, and Source Han Sans's .notdef is full width -- 1000
    # here, 1200 in Term -- so one such character moved the rest of the
    # line. build.notdef_to_cell replaces it with the Latin donor's.
    # Both Latin verifiers ask this; the JP faces are the only place the
    # defect ever existed, and the generic grid check cannot see it (a
    # full width is a whole number of cells)
    notdef = tf.getGlyphOrder()[0]
    half, _ = expected_metrics(tf)
    check(tf["hmtx"].metrics[notdef][0] == half,
          f".notdef is one cell ({half}), got "
          f"{tf['hmtx'].metrics[notdef][0]}")

    if "Nerd Font" in fam:
        import nerdpatch
        for ok, msg in nerdpatch.icon_checks(tf, nerdpatch.symbols_for_checks()):
            check(ok, msg)

    print("FAILED" if check.failed else "all checks passed")
    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
