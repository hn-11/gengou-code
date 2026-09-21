"""Shared pieces of the verification scripts (verify.py, verify_latin.py,
verify_latin_vf.py, golden.py): a HarfBuzz shaper, the ok/FAIL check
tally, the CFF hint probe, and the static-face listing nerdpatch.py and
harmonize_latin.py share.
"""

import math
import sys
import unicodedata
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

# every Type 2 hint operator; a glyph carrying any of them counts as hinted
HINT_OPS = frozenset({"hstem", "vstem", "hstemhm", "vstemhm", "hintmask", "cntrmask"})


def make_shaper(source, variations=None):
    """shape(text, feats, script=None, language=None, direction=None)
    -> (glyph infos,
    glyph positions) for a font
    given as a path or as the font's bytes; `variations` ({axis tag:
    user value}) sets a variable font's location — HarfBuzz shapes the
    VF itself there, no instancing needed."""
    blob = (hb.Blob(source) if isinstance(source, (bytes, bytearray))
            else hb.Blob.from_file_path(str(source)))
    font = hb.Font(hb.Face(blob))
    if variations:
        font.set_variations(variations)

    def shape(text, feats, script=None, language=None, direction=None):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        if direction:
            buf.direction = direction
        # a language form is only reachable through its own tag, so the
        # caller can name the script and language HarfBuzz should ask
        # for instead of the ones it guessed from the text
        if script:
            buf.script = script
        if language:
            buf.language = language
        hb.shape(font, buf, feats)
        return list(buf.glyph_infos), list(buf.glyph_positions)
    return shape


class Checker:
    """Prints 'ok  ' / 'FAIL' lines and remembers whether anything failed."""

    def __init__(self):
        self.failed = False

    def __call__(self, ok, msg):
        # None is "not checked": nerdpatch.icon_checks reports its
        # symbols-font checks that way when NF_SYMBOLS is unset, where
        # it used to report them as passing
        if ok is None:
            print(f"skip {msg}")
            return None
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")
        self.failed |= not ok
        return ok

    def exit_code(self):
        return 1 if self.failed else 0


def _bias(n):
    return 107 if n < 1240 else 1131 if n < 33900 else 32768


def glyph_has_hint(cs, local_subrs=None, global_subrs=None, seen=None):
    """Does this charstring carry a hint op, following callsubr/callgsubr
    (cffsubr moves hints into subroutines)? Each subroutine is visited
    once, so a recursive or shared subroutine cannot loop."""
    cs.decompile()
    if seen is None:
        local_subrs = list(getattr(cs.private, "Subrs", []) or [])
        global_subrs = cs.globalSubrs
        seen = set()
    stack = []
    for tok in cs.program:
        if isinstance(tok, str):
            if tok in HINT_OPS:
                return True
            if tok in ("callsubr", "callgsubr") and stack:
                subrs = local_subrs if tok == "callsubr" else global_subrs
                n = len(subrs)
                idx = int(stack[-1]) + _bias(n)
                key = (tok, idx)
                if 0 <= idx < n and key not in seen:
                    seen.add(key)
                    if glyph_has_hint(subrs[idx], local_subrs, global_subrs, seen):
                        return True
            stack = []
        elif isinstance(tok, (int, float)):
            stack.append(tok)
    return False


def hmtx_mismatches(font):
    """Glyphs whose hmtx disagrees with their CFF charstring: (name,
    charstring width, hmtx advance) where the advances differ, and
    (name, xMin, hmtx lsb) where the bearing is two units or more off
    the outline's xMin. Less is rounding: Source Han Sans sets a few
    bearings from the on-curve points, up to a unit right of a curve's
    true extreme (the stale Gengou bearings this catches were tens of
    units off). A blank glyph has no xMin and is left alone. Every glyph
    is drawn once, and its box comes back third, so a caller that needs
    the bounds does not draw them all over again."""
    cff = font["CFF "].cff
    charstrings = cff[cff.fontNames[0]].CharStrings
    hmtx = font["hmtx"].metrics
    widths, bearings, bounds = [], [], {}
    for name in font.getGlyphOrder():
        cs = charstrings[name]
        pen = BoundsPen(None)
        cs.draw(pen)
        adv, lsb = hmtx[name]
        if cs.width != adv:
            widths.append((name, cs.width, adv))
        if pen.bounds:
            bounds[name] = pen.bounds
            if abs(pen.bounds[0] - lsb) >= 2:
                bearings.append((name, pen.bounds[0], lsb))
    return widths, bearings, bounds


def static_faces(src_dir, family):
    """The static faces of `family` in `src_dir`, sorted by name: the
    `Family-Style.otf` files, never the variable fonts that share the
    directory (`Family[wght].otf`, `Family-Italic[wght].otf` — the second
    also matches a naive `Family-*.otf` glob)."""
    return sorted(p for p in Path(src_dir).glob(f"{family}-*.otf") if "[" not in p.name)


def check_style_bits(tf, check, subfamily, italic):
    """fsSelection / macStyle / post.italicAngle against the face's own
    subfamily name. The Windows family model keys off these bits, not
    the name text — clear the italic ones and Word offers the italic
    face as a separate family. Only verify.py checked them; the Latin
    faces and the variable fonts, which are half of what ships, did
    not."""
    angle = tf["post"].italicAngle
    if italic:
        check(angle != 0, "italic face, post.italicAngle non-zero")
        rise = tf["hhea"].caretSlopeRise
        run = tf["hhea"].caretSlopeRun
        want = -rise * math.tan(math.radians(angle))
        check(run != 0 and abs(run - want) <= 2,
              f"caret slope follows the outlines ({rise}/{run}, "
              f"want {rise}/{round(want)} at {angle}°)")
    else:
        check(angle == 0, f"upright face, post.italicAngle == 0 (got {angle})")
        check(tf["hhea"].caretSlopeRun == 0,
              f"upright face, caret is vertical ({tf['hhea'].caretSlopeRun})")
    fsel = tf["OS/2"].fsSelection
    mac = tf["head"].macStyle
    want_bold = "Bold" in subfamily.split()   # SemiBold is not bold
    want_italic = "Italic" in subfamily
    check(bool(fsel & 0x20) == want_bold,
          f"fsSelection BOLD bit matches subfamily {subfamily!r} "
          f"(fsSelection={fsel:#06x})")
    check(bool(fsel & 0x1) == want_italic,
          f"fsSelection ITALIC bit matches subfamily {subfamily!r} "
          f"(fsSelection={fsel:#06x})")
    check(bool(mac & 0x1) == want_bold,
          f"macStyle Bold bit matches subfamily {subfamily!r} "
          f"(macStyle={mac:#06x})")
    check(bool(mac & 0x2) == want_italic,
          f"macStyle Italic bit matches subfamily {subfamily!r} "
          f"(macStyle={mac:#06x})")
    if not want_bold and not want_italic:   # Light/Medium/SemiBold too
        check(bool(fsel & 0x40) and not (fsel & 0x61 & ~0x40),
              f"fsSelection REGULAR bit set, BOLD/ITALIC clear "
              f"(fsSelection={fsel:#06x})")


# GDI resolves a family through LOGFONT.lfFaceName, 32 bytes including
# the terminator. A family whose nameID 1 is longer cannot be selected
# there at all -- not a degraded rendering, an absent font -- in the old
# conhost, Notepad, or Office's GDI text path. nameID 16 carries the
# name spelled out for everything that reads it (DirectWrite, CoreText,
# fontconfig all prefer 16), so holding 1 to this bound costs nothing.
# It is the Nerd Fonts marker that pushes against it: nerdpatch splices
# the abbreviation into 1 and the full words into 16.
LFFACENAME_MAX = 31


def check_gdi_family_name(tf, check):
    """nameID 1 fits GDI's LOGFONT.lfFaceName."""
    fam = tf["name"].getDebugName(1) or ""
    check(len(fam) <= LFFACENAME_MAX,
          f"nameID 1 fits GDI's {LFFACENAME_MAX} characters "
          f"({len(fam)}: {fam!r})")


def check_tables(tf, check, bounds, hmtx, cmap, codepages=False):
    """The numbers a rasterizer clips and lays out by, read back from
    the outlines: head's bounding box, hhea's four extents, OS/2's
    embedding permission, version and family bits, vendor id,
    character-index range and range bits, post's underline, and every
    Unicode cmap subtable.

    The build turns fontTools' own recalculation off (recalcBBoxes =
    False) and works these out in one pass, so they are only as right
    as that pass — and nothing read them: zeroing head's box, hhea's
    extents or the range bits all passed, on the JP faces until round
    42 and on the Latin ones until this round, where the 4-cell
    ligatures then lay outside the declared box.

    `bounds`/`hmtx` are None for a variable font, whose box is the union
    over its masters rather than one location's ink: that file checks
    its own box against every instance, and everything else here is the
    same for it."""
    head, os2 = tf["head"], tf["OS/2"]
    check(head.unitsPerEm == 1000,
          f"head unitsPerEm {head.unitsPerEm} (want 1000)")
    # version 4 is what makes fsSelection bits 7-9 (USE_TYPO_METRICS,
    # WWS, OBLIQUE) readable at all, and WWS is what tells Windows the
    # family/subfamily names already are the WWS pair — without it a
    # weight lands in its own family menu entry
    check(os2.version >= 4, f"OS/2 version {os2.version} (want >= 4)")
    check(os2.fsSelection & 0x100,
          f"OS/2 WWS bit set (fsSelection={os2.fsSelection:#06x})")
    check(os2.usWidthClass == 5,
          f"OS/2 usWidthClass {os2.usWidthClass} (want 5, medium)")
    if bounds is not None and hmtx is not None:
        _check_outline_metrics(tf, check, bounds, hmtx)
    _check_os2_cmap(tf, check, cmap, codepages)


def _check_outline_metrics(tf, check, bounds, hmtx):
    """head's bounding box and hhea's four extents against the ink."""
    head, hhea = tf["head"], tf["hhea"]
    inked = list(bounds.values())
    want_box = (min(b[0] for b in inked), min(b[1] for b in inked),
                max(b[2] for b in inked), max(b[3] for b in inked))
    got_box = (head.xMin, head.yMin, head.xMax, head.yMax)
    check(all(abs(a - b) <= 1 for a, b in zip(got_box, want_box)),
          f"head's bounding box is the ink's ({got_box} vs "
          f"{tuple(round(v) for v in want_box)})")
    widths = [hmtx[n][0] for n in tf.getGlyphOrder()]
    extents = [hmtx[n][1] + (b[2] - b[0]) for n, b in bounds.items()]
    right = [hmtx[n][0] - hmtx[n][1] - (b[2] - b[0]) for n, b in bounds.items()]
    for label, got, want in (
            ("advanceWidthMax", hhea.advanceWidthMax, max(widths)),
            ("minLeftSideBearing", hhea.minLeftSideBearing,
             min(hmtx[n][1] for n in bounds)),
            ("minRightSideBearing", hhea.minRightSideBearing, min(right)),
            ("xMaxExtent", hhea.xMaxExtent, max(extents))):
        check(abs(got - want) <= 1,
              f"hhea {label} is the outlines' ({got} vs {round(want)})")


def _check_os2_cmap(tf, check, cmap, codepages):
    """OS/2's permission, identity and repertoire bits, post's underline,
    and every Unicode cmap subtable."""
    os2 = tf["OS/2"]
    check(os2.fsType == 0, f"OS/2 fsType is installable ({os2.fsType})")
    check(os2.achVendID == "GNGO", f"OS/2 vendor id ({os2.achVendID!r})")
    check(tf["post"].underlinePosition and tf["post"].underlineThickness,
          f"post underline ({tf['post'].underlinePosition}, "
          f"{tf['post'].underlineThickness})")
    check(os2.usFirstCharIndex == min(cmap)
          and os2.usLastCharIndex == min(max(cmap), 0xFFFF),
          f"OS/2 first/last char index are the cmap's "
          f"({os2.usFirstCharIndex:#x}, {os2.usLastCharIndex:#x})")
    stored = tuple(getattr(os2, f"ulUnicodeRange{i}") for i in range(1, 5))
    os2.recalcUnicodeRanges(tf)
    again = tuple(getattr(os2, f"ulUnicodeRange{i}") for i in range(1, 5))
    check(stored == again, f"OS/2 Unicode ranges match the cmap "
                           f"({[hex(v) for v in stored]} vs "
                           f"{[hex(v) for v in again]})")
    if codepages:
        # a face that declares no 932/JIS disappears from GDI's font
        # list for Japanese
        pages = (os2.ulCodePageRange1, os2.ulCodePageRange2)
        build.recalc_codepage_range(tf)
        check(pages == (os2.ulCodePageRange1, os2.ulCodePageRange2),
              f"OS/2 code page ranges match the cmap "
              f"({[hex(v) for v in pages]} vs "
              f"{[hex(os2.ulCodePageRange1), hex(os2.ulCodePageRange2)]})")
    # every Unicode cmap subtable agrees, not just the one HarfBuzz
    # picks: build.set_cmap writes them all, and the format 4 tables
    # the GDI paths read went unchecked — repointing every entry below
    # U+2000, or dropping both subtables, passed
    subtables = [t for t in tf["cmap"].tables
                 if t.isUnicode() and t.format != 14]   # 14 is IVS
    check(any(t.platformID == 3 and t.format in (0, 4, 6) for t in subtables),
          f"a BMP cmap subtable is there "
          f"({[(t.platformID, t.platEncID, t.format) for t in subtables]})")
    disagree = {}
    for table in subtables:
        for cp, name in cmap.items():
            if cp > 0xFFFF and table.format in (0, 4, 6):
                continue
            got = table.cmap.get(cp)
            if got != name:
                disagree.setdefault((table.platformID, table.platEncID), []) \
                    .append((hex(cp), got, name))
    check(not disagree, f"every Unicode cmap subtable maps the same "
                        f"({len(subtables)} subtables; off: "
                        f"{[(k, v[:2], len(v)) for k, v in disagree.items()]})")


def _axis_values(tf, tag):
    """A STAT table's AxisValue records for one design axis tag."""
    stat = tf["STAT"].table
    idx = next((i for i, a in enumerate(stat.DesignAxisRecord.Axis)
                if a.AxisTag == tag), None)
    array = getattr(stat, "AxisValueArray", None)
    values = getattr(array, "AxisValue", None) or []
    return idx, [av for av in values if getattr(av, "AxisIndex", None) == idx]


def weight_name(subfamily):
    """The weight a face's subfamily names. build.set_names writes the
    WWS pair, so the upright Regular is "Regular" and its italic is
    plain "Italic" — a bare `.replace(" Italic", "")` leaves that one as
    "Italic", which is in no weight table, and every check keyed on the
    weight silently skipped every italic face."""
    return (subfamily.replace(" Italic", "").replace("Italic", "Regular")
            or "Regular")


def check_stat(tf, check, weight, italic):
    """A STATIC face's STAT: its OWN wght value and nothing else, and the
    ital value for its own slope.

    build.add_stat takes one weight name per static face for a reason
    (its docstring: a static font listing the whole family's values
    confuses Windows' family model) — but nothing read the result.
    Rewriting Regular's value to 900, or dropping the ital value
    altogether, passed every verifier: the JP files checked that the
    wght axis was NAMED, the Latin ones that a STAT was present."""
    if "STAT" not in tf:
        return
    name = tf["name"]
    wght_axis, wght_values = _axis_values(tf, "wght")
    ital_axis, ital_values = _axis_values(tf, "ital")
    check(wght_axis is not None and ital_axis is not None,
          "STAT declares the wght and ital design axes")
    want = build.WEIGHT_CLASS[weight]
    got = [(av.Value, name.getDebugName(av.ValueNameID)) for av in wght_values]
    check(got == [(want, weight)],
          f"STAT names this face's weight and no other ({got}, want "
          f"[({want}, {weight!r})])")
    # Format 3 on the upright: elidable, and linked to the italic face
    # so a word processor's I button finds it
    want_ital = [(1, "Italic")] if italic else [(0, "Regular")]
    got_ital = [(av.Value, name.getDebugName(av.ValueNameID))
                for av in ital_values]
    check(got_ital == want_ital,
          f"STAT ital value is this face's slope ({got_ital}, want {want_ital})")
    if not italic and ital_values:
        av = ital_values[0]
        check(av.Flags & 0x2 and getattr(av, "LinkedValue", None) == 1,
              f"STAT upright ital value is elidable and links to Italic "
              f"(Flags={av.Flags:#04x}, LinkedValue="
              f"{getattr(av, 'LinkedValue', None)})")


def check_gdef_marks(tf, check, cmap):
    """GDEF is there and every combining mark in the cmap is class 3.

    build.classify_unicode_marks exists because the donor leaves two of
    them (U+035F, U+0361 — the double tie bars) unclassed, and a mark a
    shaper reads as a base glyph positions as one. verify.py required
    GDEF on the JP faces; the Latin faces and the variable fonts, where
    the same call was one line in the build, required nothing — deleting
    it rebuilt, verified and unit-tested clean.

    The JP faces are not held to this: Source Han Sans leaves nine of
    its own marks unclassed (U+0304, U+20DD, U+20DE, U+302A-U+302D,
    U+3099, U+309A), and classing them changes nothing there — no
    lookup in those faces sets IgnoreMarks or a mark filter the class
    would reach, and every sequence measured shapes identically either
    way. Their GDEF presence is checked in verify.py."""
    check("GDEF" in tf, "GDEF present")
    gdef = getattr(tf.get("GDEF"), "table", None)
    classes = getattr(getattr(gdef, "GlyphClassDef", None), "classDefs", None) or {}
    unclassed = sorted(f"U+{cp:04X}" for cp, g in cmap.items()
                       if unicodedata.category(chr(cp)) in ("Mn", "Me")
                       and classes.get(g) != 3)
    check(not unclassed, f"every combining mark is GDEF class 3 "
                         f"({len(unclassed)} are not: {unclassed[:5]})")


def check_coverage_order(tf, check):
    """Every GSUB/GPOS coverage is in glyph-id order.

    A coverage table is searched by glyph id, so its list has to be in
    that order — and a mark coverage is parallel to its anchor array,
    so a copy that sorts one without the other puts every accent on the
    wrong letter (build._remap_mark_subtable). Only the JP faces asked:
    reversing the seven MarkCoverage lists in a Latin face draws the
    ring of ẘ through the letter (k + U+0308 falls from y=229 to y=60)
    and both Latin verifiers said "all checks passed"."""
    unsorted, covs = [], 0

    def walk(obj, tag, seen):
        nonlocal covs
        if id(obj) in seen:
            return
        seen.add(id(obj))
        if isinstance(obj, (list, tuple)):
            for item in obj:
                walk(item, tag, seen)
            return
        if not hasattr(obj, "__dict__"):
            return
        for attr, value in vars(obj).items():
            if attr.endswith("Coverage") or attr == "Coverage":
                for cov in (value if isinstance(value, list) else [value]):
                    names = getattr(cov, "glyphs", None) or []
                    covs += 1
                    ids = [tf.getGlyphID(n) for n in names]
                    if ids != sorted(ids):
                        unsorted.append((tag, attr, len(names)))
            elif isinstance(value, (list, tuple)) or hasattr(value, "__dict__"):
                walk(value, tag, seen)

    for tag in ("GSUB", "GPOS"):
        if tag in tf:
            walk(tf[tag].table.LookupList.Lookup, tag, set())
    check(not unsorted, f"every coverage is in glyph-id order "
                        f"({covs} coverages; off: {unsorted[:4]})")


# the Private-dict entries the CFF spec stores as integer deltas (an
# array) or as an integer number (a scalar); BlueScale is the one real
# number in the group and is not here
_ZONE_KEYS = ("BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues")
_ARRAY_PRIVATE = _ZONE_KEYS + ("StemSnapH", "StemSnapV")
_SCALAR_PRIVATE = ("StdHW", "StdVW", "BlueShift", "BlueFuzz")


def _private_values(private, key):
    """A Private entry's values at the DEFAULT location. A CFF2 entry is
    blended — [default, delta per region] for a scalar, a list of those
    for an array — and only the default has to be a whole unit: varLib
    works the deltas out from the masters with the region scalars, so
    they come out fractional for a master at an intermediate weight and
    are meant to."""
    value = getattr(private, key, None)
    if value is None:
        return []
    if key in _SCALAR_PRIVATE:
        return [value[0] if isinstance(value, (list, tuple)) else value]
    return [v[0] if isinstance(v, (list, tuple)) else v for v in value]


def check_private(tf, check):
    """The CFF Private dicts: alignment zones in pairs and in order, and
    every entry the spec stores as an integer delta stored as one.

    Instancing Source Code Pro's CFF2 blends each zone edge on its own,
    which leaves both: an inverted pair at some weights (otfautohint
    refuses those, so the build has always sorted them) and fractional
    values at every weight off the donor's default master. Eight of the
    ten static faces shipped blues like 733.9999999, which a reader
    that truncates takes a unit low — and nothing anywhere read a
    Private dict but verify.py, on the JP faces' Latin FontDict, and
    only for how near a zone sits to sxHeight."""
    tag = "CFF " if "CFF " in tf else "CFF2"
    cff = tf[tag].cff
    td = cff[cff.fontNames[0]]
    fds = getattr(td, "FDArray", None) or [td]
    bad_order, bad_int = [], []
    for i, fd in enumerate(fds):
        private = getattr(fd, "Private", None)
        if private is None:
            continue
        for key in _ZONE_KEYS:
            values = _private_values(private, key)
            if values != sorted(values) or len(values) % 2:
                bad_order.append((i, key, values[:4]))
        for key in _ARRAY_PRIVATE + _SCALAR_PRIVATE:
            for v in _private_values(private, key):
                if v != int(v):
                    bad_int.append((i, key, v))
    check(not bad_order, f"CFF alignment zones are in pairs, in order "
                         f"({len(fds)} FontDicts; off: {bad_order[:3]})")
    check(not bad_int, f"CFF zone and stem values are whole units at the "
                       f"default location ({len(bad_int)} are not, e.g. "
                       f"{bad_int[:3]})")


# how far past the LETTER'S OWN INK an accent may reach. Measured
# from the ink, not as a fixed distance from its centre: an italic
# ascender leans right, so at Light Italic the dot over d sits 299
# units right of d's centre against a half-cell allowance of 300 --
# one unit from failing on a face that is drawn exactly as its donor
# drew it. What this catches is a whole cell, 600.
_LEAN = build.CELL // 4
# one base per script and per shape the face carries, not seven Latin
# letters the donor happens to anchor natively. Every one of b d f h k l
# t is in Source Code Pro's own mark coverage, so this pass could not
# see a letter with NO anchor at all -- which is the state the two
# variable fonts shipped in, about 550 letters each putting the accent
# in the next cell, while both Latin verifiers said all checks passed.
# Ascender, x-height, capital, Greek lower and upper, Cyrillic lower and
# upper, and Latin letters that already carry a diacritic or a dot.
ACCENT_BASES = "bdfhkltoOaAzZαωβΑΩвжшВЖШçñı"
ACCENTS = "̀́̂̃̄̆̇̈̌̊"


def check_accents_clear(shape, gs, order, cmap, check, label=""):
    """An accent sits ON the letter, not through it.

    Source Code Pro places its combining marks entirely in GPOS — an
    ascender's top anchor is 229 units above an x-height letter's — so
    every one of these pairs depends on a mark anchor being where the
    donor put it. verify.py has asked this of the JP faces, which only
    IMPORT that GPOS, since the graft first drew 58 of 84 pairs through
    the stem. The Latin faces and the variable fonts, where the donor's
    mark positioning lives natively and the two variable fonts are the
    whole of Gengou.zip, asked nothing: zeroing all 502 base anchors
    dropped every accent into the letter and both said "all checks
    passed".

    The bases are one per script and per shape (see ACCENT_BASES). With
    only the seven Latin ones this pass was still blind to a letter the
    donors never anchored AT ALL: deleting every base anchor above
    U+0250 -- the state the two variable fonts actually shipped in --
    left both Latin verifiers reporting nothing."""
    through, pairs = {}, 0
    for base in ACCENT_BASES:
        for mark in ACCENTS:
            if ord(base) not in cmap or ord(mark) not in cmap:
                continue
            infos, positions = shape(base + mark, {})
            if len(infos) != 2:
                continue        # composed into one glyph: nothing to clear
            boxes, across = [], []
            pen_x = 0
            spans = []
            for info, pos in zip(infos, positions):
                pen = BoundsPen(gs)
                gs[order[info.codepoint]].draw(pen)
                boxes.append(None if pen.bounds is None else
                             (pen.bounds[1] + pos.y_offset,
                              pen.bounds[3] + pos.y_offset))
                spans.append(None if pen.bounds is None else
                             (pen.bounds[0] + pen_x + pos.x_offset,
                              pen.bounds[2] + pen_x + pos.x_offset))
                across.append(None if spans[-1] is None else
                              sum(spans[-1]) / 2)
                pen_x += pos.x_advance
            pairs += 1
            # sideways as well as up: an accent parked a whole cell
            # right sits above nothing and cleared the letter by this
            # test alone (+600 on every base anchor passed both Latin
            # verifiers, with b's acute drawing in the next column).
            # The allowance is measured from the LETTER'S ink, not from
            # its centre: the accent goes over whatever part of the
            # letter it belongs over, which on a leaning italic
            # ascender is nowhere near the middle
            lean = None
            if None not in spans:
                lean = max(spans[0][0] - across[1], across[1] - spans[0][1], 0)
            if (None in boxes or boxes[1][0] < boxes[0][1]
                    or lean is None or lean > _LEAN):
                off = None if None in across else across[1] - across[0]
                through[base + mark] = (None if None in boxes else
                                        (round(boxes[0][1]), round(boxes[1][0]),
                                         None if off is None else round(off)))
    check(not through, f"an accent clears the letter it sits on{label} "
                       f"({pairs} pairs; through: {through})")


def check_heights(tf, check, gs, cmap):
    """OS/2's sxHeight, sCapHeight and xAvgCharWidth against the
    outlines.

    build.set_latin_heights exists so a 486/656 face does not carry
    Source Han Sans's 543/733 — CSS font-size-adjust, and a terminal
    sizing its icons to the cap height, are 12% out on the wrong
    numbers. verify.py reads all three back on the JP faces; neither
    Latin verifier did, and 543/733/1000 passed both."""
    os2 = tf["OS/2"]
    for ch, attr in (("x", "sxHeight"), ("H", "sCapHeight")):
        if ord(ch) not in cmap:
            continue
        pen = BoundsPen(gs)
        gs[cmap[ord(ch)]].draw(pen)
        got = getattr(os2, attr, None)
        check(pen.bounds is not None and got is not None
              and abs(got - pen.bounds[3]) <= 1,
              f"OS/2.{attr} is the top of {ch!r} ({got} vs "
              f"{None if pen.bounds is None else round(pen.bounds[3])})")
    widths = [w for w, _lsb in tf["hmtx"].metrics.values() if w]
    want = round(sum(widths) / len(widths)) if widths else 0
    check(abs(os2.xAvgCharWidth - want) <= 1,
          f"OS/2.xAvgCharWidth is the mean non-zero advance "
          f"({os2.xAvgCharWidth} vs {want})")


def check_zones(tf, check, cmap):
    """The alignment zones are THIS face's x-height and cap height.

    latin_blue_zones / the donor's own zones are measured on the face's
    outlines; Source Han Sans's 540/733 against an actual 486/656 snaps
    every stem to the wrong place at small sizes. verify.py asks this of
    the JP faces' Latin FontDict — the Latin faces and the variable
    fonts, where those zones are produced, passed with Source Han Sans's
    values planted in, and with every zone array emptied."""
    tag = "CFF " if "CFF " in tf else "CFF2"
    cff = tf[tag].cff
    td = cff[cff.fontNames[0]]
    fds = getattr(td, "FDArray", None)
    if fds is None or ord("H") not in cmap:
        return
    private = fds[td.FDSelect[tf.getGlyphID(cmap[ord("H")])]].Private \
        if getattr(td, "FDSelect", None) is not None else fds[0].Private
    blues = _private_values(private, "BlueValues")
    os2 = tf["OS/2"]
    wanted = [os2.sxHeight, os2.sCapHeight]
    near = [any(abs(b - v) <= 14 for b in blues) for v in wanted]
    stems = _private_values(private, "StdHW")
    check(all(near) and stems and stems[0],
          f"the alignment zones are this face's (BlueValues {blues}, "
          f"x-height {os2.sxHeight}, cap {os2.sCapHeight}, "
          f"StdHW {stems[0] if stems else None})")


def check_mark_class_closure(tf, check):
    """Everything a feature substitutes for a GDEF mark is a GDEF mark.

    Once a font has a GlyphClassDef, HarfBuzz takes a substituted
    glyph's class from it alone — there is no Unicode-category fallback
    — so a variant left unclassified becomes a BASE. Source Code Pro
    Italic leaves the `.cap` design its ccmp swaps U+0310 for after a
    capital unclassified, and the mark-to-base search for the NEXT mark
    then stopped on it: 23 of the 53 combining marks lost their
    attachment after U+0310 in all five italic Latin faces and the
    italic variable font, `E` + U+0310 + U+0301 putting both accents on
    the character after them."""
    gdef = getattr(tf.get("GDEF"), "table", None)
    defs = getattr(getattr(gdef, "GlyphClassDef", None), "classDefs", None)
    if not defs or "GSUB" not in tf:
        return
    adrift = []
    for lookup in tf["GSUB"].table.LookupList.Lookup:
        kind, subtables = build._unwrap(lookup)
        for sub in subtables:
            pairs = []
            if kind in (1, 2):
                pairs = [([src], dst if isinstance(dst, (list, tuple)) else [dst])
                         for src, dst in (getattr(sub, "mapping", None) or {}).items()]
            elif kind == 3:
                pairs = [([src], list(dsts)) for src, dsts in
                         (getattr(sub, "alternates", None) or {}).items()]
            elif kind == 4:
                # a ligature of marks is a mark: Source Code Pro's ccmp
                # stacks 30 pairs of combining marks into one glyph, 21
                # of which no codepoint reaches — so nothing else here
                # can see them, and declassing them turns a stacked
                # accent into a 600-unit spacing glyph of its own
                pairs = [([first, *lig.Component], [lig.LigGlyph])
                         for first, ligs in
                         (getattr(sub, "ligatures", None) or {}).items()
                         for lig in ligs]
            for srcs, dsts in pairs:
                if any(defs.get(src) != 3 for src in srcs):
                    continue
                adrift += [(srcs[0], dst, defs.get(dst)) for dst in dsts
                           if defs.get(dst) != 3]
    check(not adrift, f"a mark's substitute is a mark in GDEF too "
                      f"({len(adrift)} are not, e.g. {sorted(set(adrift))[:3]})")


def check_mark_features(tf, check, shape, gs, order, cmap):
    """The three GPOS features that put a mark where it belongs, the
    GDEF classes their lookups filter on, and that a second accent is
    actually lifted off the first.

    The Latin faces inherit Source Code Pro's GPOS whole and the
    variable fonts get theirs from a varLib merge, and both asked only
    that 'mark' was there and 'kern' was not. Dropping 'mkmk' — or
    clearing GDEF's MarkAttachClassDef, which is what its lookups
    filter on — draws the two accents of x + U+0300 + U+0301 on top of
    one another, and dropping GPOS 'ccmp' drops the tie bar's lift over
    an ascender back to 0. All three passed both verifiers."""
    gpos = {fr.FeatureTag for fr in tf["GPOS"].table.FeatureList.FeatureRecord} \
        if "GPOS" in tf else set()
    for tag in ("mark", "mkmk", "ccmp"):
        check(tag in gpos, f"GPOS has {tag} ({sorted(gpos)})")
    gdef = getattr(tf.get("GDEF"), "table", None)
    named = set((getattr(getattr(gdef, "MarkAttachClassDef", None),
                         "classDefs", None) or {}).values())
    filtered = {lookup.LookupFlag >> 8
                for lookup in (tf["GPOS"].table.LookupList.Lookup
                               if "GPOS" in tf else [])} - {0}
    check(filtered <= named,
          f"GDEF names the mark classes GPOS filters on "
          f"({sorted(filtered)}; GDEF has {sorted(named)})")
    lifted = probes = 0
    for base in "xz":
        for first, second in zip(ACCENTS, ACCENTS[1:] + ACCENTS[:1]):
            text = base + first + second
            if any(ord(c) not in cmap for c in text):
                continue
            infos, positions = shape(text, {})
            if len(infos) != 3:
                continue          # composed: nothing left to stack
            probes += 1
            lifted += positions[2].y_offset > 0
    check(probes and lifted, f"a second accent is lifted off the first "
                             f"({lifted} of {probes} probes; 'mkmk')")


# the combining marks Source Code Pro anchors only to the letters they
# belong on (U+25CC, and L l for the overlay, O U o for the horn), so
# over any other base the shaper leaves them at the pen — and SCP draws
# its marks to the RIGHT of the origin, which puts them in the next
# character's cell. The JP faces do not have this: graft_halfwidth
# draws every mark one cell left, so an unanchored one lands over the
# base instead. The donor's own faces measure identically, so this is
# Source Code Pro's design and not the graft's — what the check below
# holds is that the set does not GROW
STRAY_MARKS = {"U+031A", "U+031B", "U+0334", "U+0344"}
STRAY_MARKS_ITALIC = STRAY_MARKS | {"U+0310"}


def check_stray_marks(shape, gs, order, cmap, check, italic):
    """The combining marks that land in the next character's cell.

    Over ACCENT_BASES, not over "E" alone. These marks are drawn as
    spacing glyphs and the shaper zeroes their advance, so a mark the
    face cannot place lands a whole cell right -- and with one base,
    one the donor happens to anchor, this pass could not see a LETTER
    the donors never anchored. That is the state the two variable fonts
    shipped in, about 550 letters each, while every verifier passed."""
    stray = []
    for cp in sorted(cmap):
        if unicodedata.category(chr(cp)) not in ("Mn", "Me", "Mc"):
            continue
        for base in ACCENT_BASES:
            if ord(base) not in cmap:
                continue
            infos, positions = shape(base + chr(cp), {})
            if len(infos) != 2:
                continue             # composed: nothing loose to place
            base_pen = BoundsPen(gs)
            gs[order[infos[0].codepoint]].draw(base_pen)
            pen = BoundsPen(gs)
            gs[order[infos[1].codepoint]].draw(pen)
            if pen.bounds is None:
                continue
            left = pen.bounds[0] + build.CELL + positions[1].x_offset
            # past the LETTER'S own ink, not past nine tenths of the
            # cell: a mark that starts at 549 over Light Italic d, whose
            # ink runs to 591, is on the letter. One that starts at 959
            # is in the next character.
            edge = base_pen.bounds[2] if base_pen.bounds else build.CELL
            if left > edge:
                stray.append(f"U+{cp:04X}")
                break
    want = STRAY_MARKS_ITALIC if italic else STRAY_MARKS
    check(set(stray) <= want,
          f"no combining mark falls into the next cell but the ones "
          f"Source Code Pro anchors only to their own letters "
          f"({stray}; known {sorted(want)})")


# one ligature from each stylistic-set group (build.LIGATURES' `group`),
# and the glyph-swapping features README documents. Every one is
# advertised, and until now only the JP faces were asked whether any of
# it still WORKS: the Latin faces and the variable fonts checked that
# the tag was in the FeatureList, which a feature whose lookup list is
# empty passes. The two variable fonts are the whole of Gengou.zip,
# and their GSUB is a varLib merge of the masters' — a failure mode no
# other face shares
SS_PROBES = (("ss01", "=="), ("ss02", "->"), ("ss03", "<>"), ("ss04", "|>"),
             ("ss05", "::"), ("ss06", ".."), ("ss07", "//"), ("ss08", "||"))
VARIANT_PROBES = (("0", "zero"), ("a", "cv01"), ("g", "cv02"), ("a", "salt"))


def check_features_work(shape, check, cmap):
    """Each advertised feature still changes what is drawn."""
    off = {"calt": False, "liga": False}

    def count(text, feats):
        return len(shape(text, feats)[0])

    check(count("a != b", dict(off)) == 6, "calt/liga off leaves '!=' plain")
    check(count("a == b", dict(off, liga=True)) == 5,
          "liga alone ligates '==' with calt off")
    # each ss group fires for its OWN ligatures and not the others'
    dead = []
    for tag, seq in SS_PROBES:
        if any(ord(c) not in cmap for c in seq):
            continue
        if count(f"a {seq} b", dict(off, **{tag: True})) != 5:
            dead.append(tag)
    check(not dead, f"every stylistic set still ligates its own group "
                    f"({len(SS_PROBES)} probes; dead: {dead})")
    check(count("a -> b", dict(off, ss01=True)) == 6,
          "ss01 leaves another group's '->' plain")

    def first(text, feats):
        return shape(text, feats)[0][0].codepoint

    inert = [tag for ch, tag in VARIANT_PROBES
             if ord(ch) in cmap and first(ch, {}) == first(ch, {tag: True})]
    check(not inert, f"every variant feature swaps its glyph "
                     f"({len(VARIANT_PROBES)} probes; inert: {inert})")
    on = {"calt": True}
    check(shape("a != b", on)[0][2].codepoint
          != shape("a != b", dict(on, cv99=True))[0][2].codepoint,
          "cv99 swaps the ligature design")
