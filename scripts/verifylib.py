"""Shared pieces of the verification scripts (verify.py, verify_latin.py,
verify_latin_vf.py, golden.py): a HarfBuzz shaper, the ok/FAIL check
tally, the CFF hint probe, and the static-face listing nerdpatch.py and
harmonize_latin.py share.
"""

import math
import os
import statistics
import sys
import unicodedata
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.varLib.models import piecewiseLinearMap

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anchors  # noqa: E402
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


def is_italic(tf):
    """Whether the face calls itself italic, by any of the three places
    a font says so: the typographic or legacy subfamily name, the post
    table's angle, head's macStyle. check_style_bits asks that the
    three agree."""
    name = tf["name"]
    sub = name.getDebugName(17) or name.getDebugName(2) or ""
    return ("Italic" in sub or bool(tf["post"].italicAngle)
            or bool(tf["head"].macStyle & 0x2))


def check_name_ids(tf, check, ids):
    """Every nameID in `ids` is set: what a font manager, a PDF and the
    Windows family model read. Stripping all of them from a Latin face
    once passed every check here."""
    name = tf["name"]
    for nid in ids:
        check(bool(name.getDebugName(nid)), f"nameID {nid} is set")


def check_version_stamp(tf, check, unique_id=False):
    """The face carries GENGOU_VERSION in head.fontRevision and nameID 5
    (and, with `unique_id`, at the head of nameID 3). Skipped, and said
    so, when the variable is unset."""
    want = os.environ.get("GENGOU_VERSION")
    if not want:
        print("skip  version stamp (GENGOU_VERSION unset)")
        return
    major, minor = want.split(".")[:2]
    name = tf["name"]
    head5 = name.getDebugName(5) or ""
    ok = (abs(tf["head"].fontRevision - float(f"{major}.{minor}")) < 5e-4
          and head5.startswith(f"Version {want}"))
    if unique_id:
        ok = ok and (name.getDebugName(3) or "").startswith(want + ";")
    check(ok, f"stamped {want} (fontRevision {tf['head'].fontRevision:.3f}, "
              f"{head5!r})")


def check_monospace_metadata(tf, check):
    """What a font picker and GDI read to call the face monospaced, and
    the line metrics as build.set_monospace_metadata leaves them: post
    and PANOSE declare fixed pitch, PANOSE's weight follows
    usWeightClass, typo == hhea with USE_TYPO_METRICS, and the win
    metrics cover the bbox."""
    os2 = tf["OS/2"]
    check(tf["post"].isFixedPitch == 1 and os2.panose.bProportion == 9,
          "declared monospaced")
    want_pw = build.panose_weight(os2.usWeightClass)
    check(os2.panose.bWeight == want_pw,
          f"PANOSE weight {os2.panose.bWeight} matches usWeightClass "
          f"{os2.usWeightClass} (want {want_pw})")
    hhea = tf["hhea"]
    check((os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap)
          == (hhea.ascent, hhea.descent, hhea.lineGap) and os2.fsSelection & 0x80,
          "typo metrics == hhea metrics, USE_TYPO_METRICS set")
    head = tf["head"]
    check(os2.usWinAscent >= head.yMax and os2.usWinDescent >= -head.yMin,
          f"win metrics cover the bbox ({os2.usWinAscent}/{os2.usWinDescent} "
          f"vs {head.yMax}/{-head.yMin})")


def check_latin_repertoire(check, cmap):
    """A Latin face's cmap: enough of it, and none of the CJK."""
    check(len(cmap) >= 800, f"{len(cmap)} codepoints mapped")
    check(not any(0x3000 <= cp <= 0x9FFF or 0xFF00 <= cp <= 0xFFEF for cp in cmap),
          "no CJK / full-width codepoints")


def check_grid(check, metrics, cell):
    """Every advance is 0 or a whole number of cells (at most four)."""
    off = sorted({adv for adv, _ in metrics.values()}
                 - {0} - {cell * n for n in range(1, 5)})
    check(not off, f"every advance is 0 or a whole number of {cell} cells "
                   f"(offenders: {off})")


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

    anchors.classify_unicode_marks exists because the donor leaves two of
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


# the above-marks the mkmk probe stacks two at a time


# ---- combining marks ---------------------------------------------------
#
# A combining mark in these donors is a spacing glyph -- Source Code
# Pro's acute has a cell of advance with the ink inside it -- and the
# shaper zeroes that advance for a mark. So a mark the font cannot
# place does not land somewhere approximate: it lands one whole cell to
# the right, on top of the next character. Every gate below exists
# because some build shipped exactly that, or was shown it could: the
# probe-set checks this file used to run reached one lookup in seven,
# and round 7 then built twelve corrupted faces that passed the first
# rewrite of these gates -- a NULL anchor, a lookup cut below the rule
# floor, a mark dropped from a lookup's coverage, the .cap variants
# uncovered, a mark's own anchor moved off its ink, a uniform drift of
# every base anchor, mkmk anchors moved or removed, a language system
# without the mark feature, a mark lookup under another feature, ccmp
# composing to the wrong glyph, a variable-font delta at the unprobed
# master. Each is named at the gate that now catches it.

# the common above-accents the donor lets a second mark stack on (its
# mkmk Mark2 coverage; the caron is not among them)
STACKABLE_MARKS = "\u0300\u0301\u0302\u0303\u0304\u0306\u0307\u0308\u030a"
# the features a mark-to-base (4) or mark-to-mark (6) lookup may be
# reached from: a lookup under any other feature still runs in a shaper
# (HarfBuzz applies whatever GPOS names) and is outside every gate that
# walks by feature, so the walk below is by lookup type and this is
# asked of the feature instead
MARK_FEATURES = frozenset({"mark", "abvm", "blwm", "vert"})
MKMK_FEATURES = frozenset({"mkmk", "vert"})
# the combining marks the donor anchors on a handful of letters only
# (a lookup of 1-4 bases each: the left angle above, the horn, the
# tilde overlay) and no rule extends -- see anchors.anchor_loose_letters.
# Every other Latin mark must reach every letter
SPARSE_MARKS = frozenset({0x031A, 0x031B, 0x0334})
MARK_RANGES = ((0x0300, 0x036F), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF))
LETTER_RANGES = anchors.LETTER_RANGES
# from wght 300 up a second accent is lifted off the first: the donor's
# own mkmk anchors lift it 30 at Light and 111 at Regular, and only at
# its wght-200 master -- below every named instance -- do they not
LIFT_FROM_WEIGHT = 300

# Bounds for check_anchor_placement, from the anchors the ten statics
# and the two variable fonts actually carry -- 36,269 of them. An
# anchor sits at most 70 units outside its own glyph's ink and at most
# 254 from the ink's centre; a top lookup's sits between 184 below the
# ink top and 40 above it, a below lookup's between 197 above the ink
# bottom and 48 below. Each bound below is well clear of its measured
# extreme, because a gate that runs close to legitimate data is a gate
# that fails on the next weight (this file has done that twice).
# both x bounds scale with the glyph's own advance, because a
# full-width glyph legitimately spreads its anchors further than a
# one-cell one. One cell: 100 and 360. Full width: 167 and 600.
_ANCHOR_X_SLACK = 0.167      # measured 70 of 600
_ANCHOR_X_FROM_CENTRE = 0.60  # measured 0.42 Latin, 0.51 JP
_ANCHOR_Y_PAST_EDGE = 150    # measured 40 / 48
_ANCHOR_Y_INTO_INK = 350     # measured 184 / 197
# the rule a lookup's anchors follow (anchors._anchor_rule: a median
# offset from the ink centre and from the ink edge) is itself bounded:
# a uniform drift of every anchor passes each anchor's own band and
# moves the fit instead. Measured over every face: dx 0..58 above and
# -55..106 below (of a 600 or 1000 advance), dy 14..20 above and
# -18..12 below
_RULE_DX = {True: 0.15, False: 0.25}   # measured 0.097 above, 0.177 below
_RULE_DY = 60                          # measured 20
# a mark's own anchor (MarkArray / Mark1Array), against the mark's ink:
# measured -190..65 from the ink centre, and within 130 of the ink
# vertically. A mark anchor moved off its ink moves every accent the
# same way, and the attach gate cannot see it because it derives its
# expectation from the same anchor
_MARK_X_FROM_CENTRE = 0.40   # measured 190 of 600
_MARK_Y_PAST_INK = 250       # measured 130
# where a second accent stacks (Mark2Array): measured from 86 below the
# ink bottom to 2 short of the ink top
_MARK2_BELOW_INK = 150       # measured 86
# a mark's anchor against the ink edge its lookup attaches by: an
# above-mark's sits a little below its ink bottom (the donor's 500
# against ink from 570, its .cap forms' 680 against ink from 700), a
# below-mark's a little above its ink top. Measured -104..-4 above and
# -11..130 below. A mark given another's anchor (the caron with the
# .cap form's, 169 up, when a build paired a stale record list with a
# fresh coverage) sits on its own ink still and the attach gate uses
# whatever anchor it finds; this is what says so
_MARK_Y_FROM_EDGE = {True: (-150, 40), False: (-60, 180)}
# where a mark's ink lands against its letter's, shaped -- an
# expectation independent of the anchors, which every other gate reads
# and the attach gate is an equality against. Measured over every
# letter x mark of the 30 statics: an above-mark's ink begins 92 below
# to 118 above the letter's top (median 71-82), a below-mark's ends 156
# below to 150 above the letter's bottom (median -23..52), and the
# mark's ink centre sits 285 left to 299 right of the letter's (the
# italic's slant, the ogonek's right-hand seat; medians -73..114). The
# per-pair bands are set clear of those; the medians are held tighter,
# since a whole lookup's marks moved 200 units sideways stay inside
# every pair's band and move only the median
_SEAT_DY = {True: (-150, 180), False: (-200, 200)}
_SEAT_DX = 330
_SEAT_MEDIAN_DX = 160
_SEAT_MEDIAN_DY = (-60, 130)
# the ascender letters and the above-accents an accent must clear: with
# the anchors right, the mark's ink starts above the letter's; drawn
# through the stem of b d f h k l (58 of 84 pairs, on the first graft)
# it is a rendering defect no table check sees, and the one the JP
# verifier caught when the caron took the .cap anchor
CLEAR_BASES = "bdfhklt"
CLEAR_MARKS = STACKABLE_MARKS + "\u030c"
# a letter's mark sits within _SEAT_SPREAD of where the rest of its
# lookup and category (Lu, Ll ...) put theirs -- what a whole lookup's
# median cannot see, one letter's anchors moved 140 units (round 9,
# mutant L12b: 6,142 square units of B under the acute). Measured: the
# letters of a category take the accent within about 45 units of one
# another, except where the letter's outer ink is not its body -- the
# horn of ơ ư, the hook of ɠ, the descender of η ɥ ɻ ɕ ʇ ɖ y ỵ ỷ ỹ under a
# below-mark -- which sit up to 200 off and are held to the absolute
# bands only
_SEAT_SPREAD = 60
# (sideways, one letter's anchors are held to the absolute _SEAT_DX
# only: a per-kind or overlap rule was tried in round 9 and every
# version needed a list of the designs it fails -- the cedilla under
# F's stem, the ogonek at A's foot, a wide mark over Light l -- so an
# anchor 250 to the right on ONE letter is a known blind spot)
# and each MARK sideways: within a lookup every mark sits at the same
# offset from the letter's centre, so one mark's own median dx is held
# to the lookup's -- a mark's outline moved 220 with its anchor left
# behind passed (round 9, mutant L13). Measured 45 upright, 74 at Bold
# Italic (the double grave)
_MARK_DX_SPREAD = 110
_SEAT_KIND = 5               # letters a kind needs before it has a median to hold to
SEAT_EDGE_LETTERS = frozenset("\u01a1\u01b0\u01a0\u01af\u0260\u03b7\u0265\u027b\u0255"
                              "\u0287\u0256y\u1ef5\u1ef7\u1ef9")
# a second accent's sideways step from the first, beyond where each
# sits alone: mkmk's Mark2 anchors read exactly (check_marks_stack),
# and the ink then held to what an exact anchor 200 units off would
# fail (mutant L18). The step is 0 by design, and the slant of an
# italic leans a stacked mark about 40 units
_STACK_DX = 80

# ---- one glyph in its cell (check_cells) ----
# an advance follows the character's East Asian Width: Na and H a cell,
# W and F the full width, A and N either (or none, for a mark). No
# other bound sees ONE glyph's advance: a whole number of cells passes
# check_grid, xAvgCharWidth absorbs it, and 'e' at two cells moved the
# rest of the line a cell (round 9, mutant L1)
WIDE_IN_ONE_CELL = frozenset({0x2615, 0x26A1, 0x1F3B5, 0x1F3B6, 0x1F4A9, 0x1F512, 0x1F916,
                              0x302E, 0x302F, 0x31B4, 0x31B5, 0x31B6, 0x31B7, 0x31BB})
# ... the East Asian Wide characters the donors draw in one cell: the
# five Monaspace emoji, the Nerd Fonts ⚡, and Source Han Sans's own
# half-width Hangul tone marks and Bopomofo extensions
# what a shaper gives no advance whatever the font says: the
# default-ignorable code points among the repertoire (soft hyphen, the
# zero-width and joiner controls, the byte order mark)
DEFAULT_IGNORABLE = (frozenset({0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5,
                                0x180E, 0x3164, 0xFEFF, 0xFFA0})
                     | frozenset(range(0x200B, 0x2010)) | frozenset(range(0x2060, 0x2070))
                     | frozenset(range(0xFE00, 0xFE10)) | frozenset(range(0x1D173, 0x1D17B)))
# the two-em and three-em dashes: that many full widths, by policy
MULTI_EM = {0x2E3A: 2, 0x2E3B: 3}
# the features a shaper applies without being asked (check_substitution_identity)
DEFAULT_FEATURES = frozenset({"ccmp", "locl", "liga", "clig", "calt", "rlig", "rclt",
                              "curs", "kern", "dist", "mark", "mkmk", "abvm", "blwm"})
# the default rules that do turn one character into another, by design:
# i and j to the encoded dotless letters (the accent then sits on a
# bare stem), and Source Han Sans composing the vertical repeat marks
SUBSTITUTED_CHARACTERS = frozenset({("i", "\u0131"), ("j", "\u0237"),
                                    ("\u3033\u3035", "\u3031"), ("\u3034\u3035", "\u3032")})
_CENTRE_BAND = 120           # a narrow letter's or digit's ink centre from the cell's; measured 77 (V, Bold Italic)
_BASELINE = (-20, 10)        # a digit's or capital's ink bottom; measured -12 (round overshoot) .. 0
_IDEOGRAPH_Y = (-130, 890)   # an ideograph's or kana's ink, in Source Han Sans's em box -120..880; measured -104..872
_EDGE = 12                   # a full-width glyph's ink past its cell
_ZERO_ADVANCE_X = (-120, 300)  # a zero-advance mark's ink: x0 >= -(full width) + this[0], x1 <= this[1]; measured -1000..214
_BOPOMOFO = anchors.BOPOMOFO
DOUBLE_SPAN = anchors.DOUBLE_SPAN


# how far a glyph's ink may reach past its advance: the widest italic
# lean is 224 (the deferred `#(` at Bold Italic 20 past its cells). Half
# a cell let a two-cell ligature drawn 300 to the right pass (round 9,
# mutant L4: 236 into the next cell)
_LEAN = 230
# every face's line metrics (Source Code Pro's), hhea and typo alike:
# verify.py pinned them and the Latin faces only asked typo == hhea,
# so a 1400/-600 line passed there (round 10, mutants G7, G33, V11)
LINE_METRICS = (984, -273, 0)
# a ligature glyph is unencoded, so nothing held its ink: one drawn
# 250 up floated over the x-height (round 10, mutants G1, G1b, V10).
# Its ink stays in its cells to _EDGE and within the union of its
# components' ink heights, below by this[0] and above by this[1];
# measured 58 (~-) and 100 (::)
_LIG_Y = (70, 120)
_LIG_EDGE = 40               # a ligature's ink past its cells; the deferred `#(` reaches 20 at Bold Italic


def ink_spill(bounds, advance, cmap, cell):
    """The glyphs whose ink reaches past their advance by more than the
    lean allowed (_LEAN): [(name, advance, xMin, xMax)]. `bounds` maps a drawn
    glyph to its box, `advance` a glyph to its advance width.

    WHERE the ink lands, not just how wide it is: every width check
    holds on a face whose glyphs are all drawn one cell to the right,
    so 'e' would sit wholly in its neighbour's column. The bound is
    half a cell either side, of which the widest italic lean uses 224;
    a double diacritic gets a whole cell, since half of it is meant
    to hang over the character before -- U+035F draws from -300 at
    Bold Italic (-300.135 before the static rounds it), and a half-cell
    bound held it with no margin at all."""
    double = {cmap[cp] for cp in DOUBLE_SPAN if cp in cmap}
    spill = []
    for name, box in bounds.items():
        adv = advance(name)
        lean = cell if name in double else _LEAN
        if adv > 0 and (round(box[0]) < -lean or round(box[2]) > adv + lean):
            spill.append((name, adv, round(box[0]), round(box[2])))
    return spill


def _pos_lookups(tf):
    """[(index, LookupType, [subtables], {feature tags})] over every
    GPOS lookup, Extension unwrapped -- by type, not by feature, so a
    lookup registered under the wrong feature is still walked."""
    if "GPOS" not in tf:
        return []
    table = tf["GPOS"].table
    tags = {}
    for fr in table.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            tags.setdefault(li, set()).add(fr.FeatureTag)
    out = []
    for i, lookup in enumerate(table.LookupList.Lookup):
        kind, subs = build._unwrap_pos(lookup)
        out.append((i, kind, subs, tags.get(i, set())))
    return out


def _tone_subtable(sub, rev):
    """Whether a mark-to-base subtable is one of Source Han Sans's
    Bopomofo tone-mark ones, which set the mark beside the syllable:
    the one rule anchors._mark_base_lookups(on_letter=True) reads."""
    return any(rev.get(g) in _BOPOMOFO for g in sub.BaseCoverage.glyphs)


def _mark_base_subtables(tf):
    """[(lookup index, subtable)] for every mark-to-base subtable that
    places a mark ON the letter -- the Bopomofo tone-mark subtables,
    which go beside the syllable, are left out (_tone_subtable)."""
    rev = {g: cp for cp, g in tf.getBestCmap().items()}
    return [(i, sub) for i, kind, subs, _ in _pos_lookups(tf) if kind == 4
            for sub in subs if not _tone_subtable(sub, rev)]


def check_tone_lookups(tf, check, label=""):
    """A tone-mark subtable covers no letter. The subtables the mark
    gates leave out are the one place a letter's anchor is not read,
    so a letter in one is an anchor no gate sees: the JP build's
    anchor_loose_letters once fitted the tone lookups to every letter,
    and A + U+02EA set the tone mark on the A while keeping its cell."""
    cmap = tf.getBestCmap()
    rev = {g: cp for cp, g in cmap.items()}
    letters = {g for cp, g in cmap.items()
               if any(lo <= cp <= hi for lo, hi in LETTER_RANGES)
               and unicodedata.category(chr(cp)).startswith("L")}
    off = {}
    for i, kind, subs, _ in _pos_lookups(tf):
        if kind != 4:
            continue
        for sub in subs:
            if _tone_subtable(sub, rev):
                hit = sorted(letters.intersection(sub.BaseCoverage.glyphs))
                if hit:
                    off[i] = (len(hit), hit[:3])
    check(not off, f"a tone-mark lookup covers no letter{label} (off: {off})")


def _mark_mark_subtables(tf):
    return [(i, sub) for i, kind, subs, _ in _pos_lookups(tf) if kind == 6
            for sub in subs]


def _letters(tf, gs):
    """The glyphs that take an accent (anchors.accent_bases) that draw,
    and what GSUB turns one into (the Serbian locl б, a cvNN variant),
    since the shaper substitutes before it positions."""
    cmap = tf.getBestCmap()
    letters = anchors.accent_bases(cmap)
    letters |= anchors._letter_variants(tf, letters)
    return {g for g in letters if build._bounds(gs, g)}


def _latin_marks(tf, gs):
    """{codepoint: glyph} for the combining marks the Latin layer
    encodes and GDEF files as marks, less the double diacritics."""
    gdef = getattr(tf.get("GDEF"), "table", None)
    classes = getattr(getattr(gdef, "GlyphClassDef", None), "classDefs", None) or {}
    return {cp: g for cp, g in tf.getBestCmap().items()
            if any(lo <= cp <= hi for lo, hi in MARK_RANGES)
            and classes.get(g) == 3 and cp not in DOUBLE_SPAN and build._bounds(gs, g)}


def check_mark_features(tf, check, label=""):
    """The GPOS features that put a mark where it belongs, and the GDEF
    classes their lookups filter on.

    Dropping 'mkmk' -- or clearing GDEF's MarkAttachClassDef, which is
    what its lookups filter on -- draws the two accents of x + U+0300 +
    U+0301 on top of one another, and dropping GPOS 'ccmp' drops the
    tie bar's lift over an ascender back to 0."""
    gpos = {fr.FeatureTag for fr in tf["GPOS"].table.FeatureList.FeatureRecord} \
        if "GPOS" in tf else set()
    for tag in ("mark", "mkmk", "ccmp"):
        check(tag in gpos, f"GPOS has {tag}{label} ({sorted(gpos)})")
    gdef = getattr(tf.get("GDEF"), "table", None)
    named = set((getattr(getattr(gdef, "MarkAttachClassDef", None),
                         "classDefs", None) or {}).values())
    filtered = {lookup.LookupFlag >> 8
                for lookup in (tf["GPOS"].table.LookupList.Lookup
                               if "GPOS" in tf else [])} - {0}
    check(filtered <= named,
          f"GDEF names the mark classes GPOS filters on{label} "
          f"({sorted(filtered)}; GDEF has {sorted(named)})")


def check_mark_reachability(tf, check, label=""):
    """Every mark-to-base lookup is reached from a mark feature and
    every mark-to-mark lookup from mkmk (or vert, for the vertical
    forms).

    A lookup moved under GPOS 'ccmp' still runs -- HarfBuzz applies
    what the feature names -- but was outside every gate that walked
    the 'mark' feature, so its base anchors moved a cell left passed
    (round 7, mutant 13). The gates below walk by lookup type; this is
    what keeps the feature honest."""
    off = [(i, kind, sorted(tags)) for i, kind, _, tags in _pos_lookups(tf)
           if (kind == 4 and not tags & MARK_FEATURES)
           or (kind == 6 and not tags & MKMK_FEATURES)]
    check(not off, f"every mark lookup is reached from a mark feature{label} "
                   f"(off: {off})")
    # and the other way about: a mark feature reaches mark lookups only
    # (a contextual or pair lookup under 'mark' is outside every gate
    # here), and nothing in this family attaches marks to ligatures --
    # a mark-to-ligature lookup would be walked by the shaper and by no
    # gate
    odd = [(i, kind, sorted(tags)) for i, kind, _, tags in _pos_lookups(tf)
           if kind == 5 or (tags & {"mark", "mkmk"} and kind not in (1, 4, 6))]
    check(not odd, f"the mark features reach mark lookups (and the donor's single "
                   f"adjustment) only, and there is no mark-to-ligature lookup{label} "
                   f"(off: {odd})")
    # and its flag lets it see its own marks: IgnoreMarks on a mark
    # lookup, or a MarkAttachmentType class its marks are not in, is a
    # lookup that never applies (the model mirrors the class filter for
    # the marks it does admit; this is what says the rest is a defect)
    gdef = getattr(tf.get("GDEF"), "table", None)
    attach = getattr(getattr(gdef, "MarkAttachClassDef", None), "classDefs", None) or {}
    silent = []
    for i, kind, subs, _ in _pos_lookups(tf):
        if kind not in (4, 6):
            continue
        flag = tf["GPOS"].table.LookupList.Lookup[i].LookupFlag
        if flag & 0x8:
            silent.append((i, "IgnoreMarks"))
            continue
        cls = flag >> 8
        if not cls:
            continue
        marks = set()
        for sub in subs:
            marks |= set(sub.MarkCoverage.glyphs if kind == 4 else
                         sub.Mark1Coverage.glyphs + sub.Mark2Coverage.glyphs)
        out = sorted(g for g in marks if attach.get(g, 0) != cls)
        if out:
            silent.append((i, f"filters out {len(out)} of its own marks, e.g. {out[:3]}"))
    check(not silent, f"every mark lookup admits its own marks{label} (off: {silent})")


def check_langsys_parity(tf, check, label=""):
    """Every language system reaches the same mark features as every
    other.

    A shaper applies the features of the LangSys it resolves the run
    to, and a LangSys that lost 'mark' loses every accent under that
    language alone: cyrl/SRB without mark+mkmk put а+U+0301's accent
    a cell right under lang=sr and nowhere else (round 7, mutant 7).
    Every gate here shapes with the script and language HarfBuzz
    guesses, so this reads the table instead."""
    if "GPOS" not in tf:
        return
    table = tf["GPOS"].table
    tags = [fr.FeatureTag for fr in table.FeatureList.FeatureRecord]
    reach = {}
    for sr in table.ScriptList.ScriptRecord:
        systems = [("dflt", sr.Script.DefaultLangSys)]
        systems += [(lr.LangSysTag, lr.LangSys) for lr in sr.Script.LangSysRecord]
        for lang, ls in systems:
            if ls is None:
                continue
            reach[(sr.ScriptTag, lang)] = frozenset(
                tags[i] for i in ls.FeatureIndex) & {"mark", "mkmk"}
    every = frozenset().union(*reach.values()) if reach else frozenset()
    short = {k: sorted(every - v) for k, v in reach.items() if v != every}
    check(not short, f"every language system reaches the same mark features{label} "
                     f"({len(reach)} systems; short: {short})")


def check_anchor_placement(tf, check, gs, label=""):
    """Every anchor sits on the glyph it belongs to: a base anchor on
    its letter, in the band its lookup's rule puts it; a mark anchor on
    the mark's own ink; a stacking anchor on the mark it stacks on.

    Structural -- no shaper, no probe set to miss: it reads the anchors
    themselves. A base anchor must lie inside the letter's ink plus a
    sixth of the advance, within 0.6 of the advance from the ink's
    centre, and on the right side of whichever ink edge its lookup's
    own anchors track (anchors._anchor_rule); a NULL anchor in a one-
    class lookup is an anchor that places nothing (mutant 5). The
    fitted rule's own offsets are bounded too, since a uniform drift of
    every anchor moves the fit rather than any anchor's residual
    (mutant 4). A mark's anchor must sit on the mark's ink (mutant 2)
    -- and, where the lookup's rule says which edge it attaches by,
    within the donor's distance of that edge, which is what tells a
    mark given another mark's anchor from one given its own -- which
    the attach gate cannot ask, deriving its expectation from that
    same anchor; and a Mark2 anchor between the ink bottom and the
    ink top of the mark another stacks on (mutant 1), lifting it by
    something from wght 300 up (the italic donor's grave, acute, breve
    and ring did not, and drew x̀́ as one accent on the other)."""
    off = {}
    hmtx = tf["hmtx"].metrics
    cmap = tf.getBestCmap()

    def mark_off(gn, anchor, top=None):
        box = build._bounds(gs, gn)
        if anchor is None or not box:
            return None
        x, y = anchor.XCoordinate, anchor.YCoordinate
        if top is None:
            lo, hi = box[1] - _MARK_Y_PAST_INK, box[3] + _MARK_Y_PAST_INK
        else:
            near, far = _MARK_Y_FROM_EDGE[top]
            edge = box[1] if top else box[3]
            lo, hi = edge + near, edge + far
        if (abs(x - (box[0] + box[2]) / 2) > _MARK_X_FROM_CENTRE * build.CELL
                or not lo <= y <= hi):
            return (gn, x, y, tuple(round(v) for v in box))
        return None

    for i, sub in _mark_base_subtables(tf):
        rule = anchors._anchor_rule(gs, sub)
        top = rule[0] if rule else None
        if rule and (abs(rule[1]) > _RULE_DX[rule[0]] * max(hmtx[g][0] for g in sub.BaseCoverage.glyphs)
                     or abs(rule[2]) > _RULE_DY):
            off.setdefault(i, []).append(("rule", rule))
        for gn, rec in zip(sub.BaseCoverage.glyphs, sub.BaseArray.BaseRecord):
          box = build._bounds(gs, gn)
          # every class's anchor: the shaper reads BaseAnchor[the mark's
          # class], and the .cap forms of the marks are a class of their
          # own in a two-class lookup
          for cls, anchor in enumerate(rec.BaseAnchor or []):
            if anchor is None:
                if sub.ClassCount == 1 and box:
                    off.setdefault(i, []).append((gn, None))
                continue
            if not box:
                continue
            x, y = anchor.XCoordinate, anchor.YCoordinate
            centre = (box[0] + box[2]) / 2
            cell = max(hmtx[gn][0], build.CELL)
            spread = _ANCHOR_X_FROM_CENTRE * cell
            slack = _ANCHOR_X_SLACK * cell
            if top is True:
                lo, hi = box[3] - _ANCHOR_Y_INTO_INK, box[3] + _ANCHOR_Y_PAST_EDGE
            elif top is False:
                lo, hi = box[1] - _ANCHOR_Y_PAST_EDGE, box[1] + _ANCHOR_Y_INTO_INK
            else:
                lo, hi = box[1] - _ANCHOR_Y_INTO_INK, box[3] + _ANCHOR_Y_INTO_INK
            if (not box[0] - slack <= x <= box[2] + slack
                    or abs(x - centre) > spread
                    or not lo <= y <= hi):
                off.setdefault(i, []).append(
                    (gn, cls, x, y, tuple(round(v) for v in box)))
        for gn, rec in zip(sub.MarkCoverage.glyphs, sub.MarkArray.MarkRecord):
            bad = mark_off(gn, rec.MarkAnchor, top)
            if bad:
                off.setdefault(i, []).append(bad)
    lift_due = tf["OS/2"].usWeightClass >= LIFT_FROM_WEIGHT if "OS/2" in tf else True
    reachable = set(cmap.values()) | anchors.gsub_outputs(tf)
    for i, sub in _mark_mark_subtables(tf):
        ones = {}
        for gn, rec in zip(sub.Mark1Coverage.glyphs, sub.Mark1Array.MarkRecord):
            ones[gn] = rec.MarkAnchor
            bad = mark_off(gn, rec.MarkAnchor)
            if bad:
                off.setdefault(i, []).append(bad)
        for gn, rec in zip(sub.Mark2Coverage.glyphs, sub.Mark2Array.Mark2Record):
            box = build._bounds(gs, gn)
            if not box:
                continue
            for anchor in rec.Mark2Anchor:
                if anchor is None:
                    continue
                y = anchor.YCoordinate
                own = ones.get(gn)
                # at the height its own Mark1 attaches at: the second
                # mark lands ON the first (the italic donor's grave,
                # acute, breve and ring). A glyph no cmap or GSUB
                # reaches cannot be shaped and is not asked
                collapsed = (lift_due and own is not None
                             and abs(y - own.YCoordinate) <= 2 and gn in reachable)
                if (not box[1] - _MARK2_BELOW_INK <= y <= box[3]
                        or abs(anchor.XCoordinate - (box[0] + box[2]) / 2)
                        > _MARK_X_FROM_CENTRE * build.CELL or collapsed):
                    off.setdefault(i, []).append(
                        (gn, anchor.XCoordinate, y, tuple(round(v) for v in box),
                         "stacks on itself" if collapsed else "off the mark"))
    worst = {i: (len(v), v[:2]) for i, v in off.items()}
    check(not off, f"every anchor sits on its own glyph{label} "
                   f"(off, by lookup: {worst})")


def check_anchor_coverage(tf, check, gs, label=""):
    """Every combining mark of the Latin layer can be placed on every
    letter: the lookups covering the mark cover, between them, every
    letter and every variant GSUB makes of one.

    anchors.anchor_loose_letters' own invariant, read back by mark rather
    than by lookup. Read by lookup, "a lookup with fewer bases than the
    rule needs is the donor's own and asks nothing" excused a lookup
    cut from 833 bases to 15 (mutant 12): the fewer bases survived,
    the less was asked. By mark there is no floor to fall under: the
    acute must reach every letter, whatever lookup it is in, and the
    three marks the donor anchors on a handful of letters only are
    named (SPARSE_MARKS). The two variable fonts once shipped with 502
    base anchors against the statics' 3,313 while every probe passed;
    this is what would have said so."""
    letters = _letters(tf, gs)
    marks = _latin_marks(tf, gs)
    subtables = _mark_base_subtables(tf)
    missing = {}
    for cp, g in sorted(marks.items()):
        if cp in SPARSE_MARKS:
            continue
        covered = set()
        for _, sub in subtables:
            if g in sub.MarkCoverage.glyphs:
                covered |= set(sub.BaseCoverage.glyphs)
        gap = letters - covered
        if gap:
            missing[f"U+{cp:04X}"] = (len(gap), sorted(gap)[:3])
    check(not missing, f"every mark reaches every letter{label} "
                       f"({len(marks)} marks, {len(letters)} letters; short, by "
                       f"mark: {missing})")


class _MarkModel:
    """What GPOS says a run of one base and its marks is positioned
    as, read off the tables so the shaper can be held to it exactly.

    A mark attaches to the base through the LAST lookup covering the
    pair (a shaper applies the lookups in order and each attachment
    overwrites the one before; within a lookup the first subtable that
    covers the pair is the one applied): its anchor laid on the
    base's, the base's advance already taken by the pen, so x_offset =
    base.x - mark.x - advance, y_offset = base.y - mark.y, x_advance =
    0. It stacks instead when a mark-to-mark lookup covers it as Mark1
    and, as Mark2, the nearest mark before it that the lookup's flag
    admits -- a MarkAttachmentType class or a mark filtering set skips
    the marks of other classes when looking back, and never applies to
    a Mark1 of another class -- at the previous mark's offset plus
    (Mark2 anchor - Mark1 anchor). A NULL anchor places nothing, and a
    mark nothing covers is placed nowhere: both are None.

    IgnoreMarks on a mark lookup is not modelled: a mark lookup that
    ignores marks never applies, which check_mark_reachability reports
    as the defect it is rather than this predicting the mark's
    absence."""

    def __init__(self, tf):
        self.hmtx = tf["hmtx"].metrics
        table = tf["GPOS"].table if "GPOS" in tf else None
        gdef = getattr(tf.get("GDEF"), "table", None)
        self.attach_class = (getattr(getattr(gdef, "MarkAttachClassDef", None),
                                     "classDefs", None) or {})
        sets = getattr(getattr(gdef, "MarkGlyphSetsDef", None), "Coverage", None) or []
        self.filter_sets = [set(c.glyphs) for c in sets]
        self.bases = _mark_base_subtables(tf)
        self.stacks = _mark_mark_subtables(tf)
        self.flags = {i: (table.LookupList.Lookup[i].LookupFlag,
                          getattr(table.LookupList.Lookup[i], "MarkFilteringSet", None))
                      for i in {i for i, _ in self.bases} | {i for i, _ in self.stacks}}

    @staticmethod
    def _by_lookup(pairs):
        """[(lookup index, [subtables])] in lookup order."""
        out = []
        for i, sub in pairs:
            if out and out[-1][0] == i:
                out[-1][1].append(sub)
            else:
                out.append((i, [sub]))
        return out

    def _admits(self, i, glyph):
        """Whether lookup `i`'s flag lets it see `glyph` as a mark."""
        flag, filter_set = self.flags[i]
        cls = flag >> 8
        if cls and self.attach_class.get(glyph, 0) != cls:
            return False
        if flag & 0x10 and filter_set is not None:
            return glyph in self.filter_sets[filter_set]
        return True

    def on_base(self, base_g, mark_g):
        for i, subs in reversed(self._by_lookup(self.bases)):
            for sub in subs:
                if base_g not in sub.BaseCoverage.glyphs or mark_g not in sub.MarkCoverage.glyphs:
                    continue
                rec = sub.MarkArray.MarkRecord[sub.MarkCoverage.glyphs.index(mark_g)]
                base = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index(base_g)]
                ba, ma = base.BaseAnchor[rec.Class], rec.MarkAnchor
                if ba is None or ma is None:
                    return None
                return (ba.XCoordinate - ma.XCoordinate - self.hmtx[base_g][0],
                        ba.YCoordinate - ma.YCoordinate, 0)
        return None

    def stack(self, glyphs, j):
        """(index of the mark glyphs[j] stacks on, (Mark2 anchor - Mark1
        anchor)) through the last mark-to-mark lookup that applies, or
        None if none does."""
        mark_g = glyphs[j]
        for i, subs in reversed(self._by_lookup(self.stacks)):
            if not self._admits(i, mark_g):
                continue
            k = j - 1
            while k >= 1 and not self._admits(i, glyphs[k]):
                k -= 1
            if k < 1:
                continue
            below_g = glyphs[k]
            for sub in subs:
                if below_g not in sub.Mark2Coverage.glyphs or mark_g not in sub.Mark1Coverage.glyphs:
                    continue
                rec = sub.Mark1Array.MarkRecord[sub.Mark1Coverage.glyphs.index(mark_g)]
                a2 = sub.Mark2Array.Mark2Record[sub.Mark2Coverage.glyphs.index(below_g)].Mark2Anchor[rec.Class]
                a1 = rec.MarkAnchor
                if a2 is None or a1 is None:
                    break
                return k, (a2.XCoordinate - a1.XCoordinate, a2.YCoordinate - a1.YCoordinate)
        return None

    def on_mark(self, below_g, mark_g):
        """(Mark2 anchor - Mark1 anchor) for a mark stacked directly on
        another, or None if the pair does not stack."""
        got = self.stack([None, below_g, mark_g], 2)
        return got[1] if got else None

    def run(self, glyphs):
        """The expected (x_offset, y_offset, x_advance) of each mark in
        a shaped run [base, mark, mark, ...], None where nothing
        places it."""
        out = [None]
        for j, g in enumerate(glyphs[1:], 1):
            stacked = self.stack(glyphs, j) if j > 1 else None
            if stacked is not None and out[stacked[0]] is not None:
                k, lift = stacked
                pos = (out[k][0] + lift[0], out[k][1] + lift[1], 0)
            else:
                pos = self.on_base(glyphs[0], g)
            out.append(pos)
        return out[1:]


def _hold_run(model, shape, order, rev, text, wrong, key):
    """Shape `text` and hold every mark in the result to the model.
    Returns the count of marks placed exactly; a run composed into one
    glyph counts as one when that glyph is the composed character's.
    A sparse mark (SPARSE_MARKS) the model places nowhere is the
    donor's own handful of letters, not a finding."""
    infos, positions = shape(text, {})
    got = [order[info.codepoint] for info in infos]
    if len(got) == 1:
        whole = unicodedata.normalize("NFC", text)
        if len(whole) == 1 and rev.get(got[0]) == ord(whole):
            return 1
        wrong.setdefault(key, []).append((text, "composed to", got[0]))
        return 0
    n = 0
    for j, expect in enumerate(model.run(got), 1):
        pos = (positions[j].x_offset, positions[j].y_offset, positions[j].x_advance)
        if expect is None:
            if rev.get(got[j]) in SPARSE_MARKS:
                continue
            wrong.setdefault(key, []).append((text, got, "unanchored", got[j]))
        elif pos == expect:
            n += 1
        else:
            wrong.setdefault(key, []).append((text, got, got[j], pos, expect))
    return n


def check_marks_attach(tf, shape, check, label=""):
    """The shaper puts each mark exactly where its anchors say.

    check_anchor_placement asks whether the anchors are right; this
    asks whether they are USED. A right anchor is applied only if the
    mark is a mark in GDEF, the lookup is reached, its flag does not
    filter the mark out, and nothing earlier in the run composed or
    substituted the pair away. When it is applied the mark's position
    is fully determined, so the check is an equality, not a threshold
    (_MarkModel says which): x_offset == base.x - mark.x - the base's
    advance, y_offset == base.y - mark.y, and x_advance == 0. The
    advance is part of it because the shaper positions a glyph it
    finds in MarkCoverage whether or not GDEF calls it a mark; what
    GDEF decides is whether its spacing advance is zeroed, and a mark
    that keeps one pushes the next character along by a cell.

    Coverage-driven: every base in each subtable against one of its
    marks, and every mark against one of its bases. Nothing is skipped
    (the first rewrite skipped 38% of its pairs as "composed or
    substituted", which hid a mark dropped from the coverage and the
    .cap variants uncovered, mutants 10 and 6): whatever the shaper
    makes of the pair -- the acute swapped for acute.cap after a
    capital, a precomposed base decomposed and its marks reordered --
    is held to the model glyph by glyph, and a pair composed into one
    glyph must compose to the cmap's glyph for that character
    (mutant 9). The three sparse marks may fall off a letter their
    lookup does not cover (SPARSE_MARKS); nothing else may."""
    rev = {g: cp for cp, g in tf.getBestCmap().items()}
    order = tf.getGlyphOrder()
    model = _MarkModel(tf)
    exact = 0
    wrong = {}
    seen = set()
    for i, sub in model.bases:
        marks = [g for g in sub.MarkCoverage.glyphs if g in rev]
        bases = [g for g in sub.BaseCoverage.glyphs if g in rev]
        if not marks or not bases:
            continue
        pairs = [(b, marks[0]) for b in bases] + [(bases[0], m) for m in marks]
        for base_g, mark_g in pairs:
            if (base_g, mark_g) in seen:
                continue
            seen.add((base_g, mark_g))
            exact += _hold_run(model, shape, order, rev,
                               chr(rev[base_g]) + chr(rev[mark_g]), wrong, i)
    worst = {i: (len(v), v[:2]) for i, v in wrong.items()}
    check(exact and not wrong,
          f"the shaper lays every mark on its anchor{label} "
          f"({exact} marks exact; off, by lookup: {worst})")


def _centres(shape, gs, order, text):
    """The ink centre of each shaped glyph of `text`, or None if one
    glyph has no ink or the run is not one glyph per character."""
    infos, positions = shape(text, {})
    if len(infos) != len(text):
        return None
    centres, x = [], 0
    for info, pos in zip(infos, positions):
        box = build._bounds(gs, order[info.codepoint])
        if box is None:
            return None
        centres.append(x + pos.x_offset + (box[0] + box[2]) / 2)
        x += pos.x_advance
    return centres


def check_marks_stack(tf, shape, check, label=""):
    """A second accent stacks exactly where the first one's Mark2
    anchor says, and the common above-accents can all be stacked on.

    The mark-to-mark half of check_marks_attach, through the same
    model: the second mark's offset is the first's plus (Mark2 anchor
    - its own Mark1 anchor). Every Mark2 mark against one Mark1 and
    one Mark2 against every Mark1, each on a letter the first mark
    attaches to that no precomposed character absorbs. Asking only
    that SOME probe was lifted passed a face where four of the ten
    stacked on themselves (mutant 8); asking every pair does not, and
    a mark removed from Mark2Coverage is a mark nothing can stack on."""
    cmap = tf.getBestCmap()
    rev = {g: cp for cp, g in cmap.items()}
    order = tf.getGlyphOrder()
    gs = tf.getGlyphSet()
    model = _MarkModel(tf)
    stackable = set()
    for _, sub in model.stacks:
        for g, rec in zip(sub.Mark2Coverage.glyphs, sub.Mark2Array.Mark2Record):
            if g in rev and any(a is not None for a in rec.Mark2Anchor):
                stackable.add(rev[g])
    cannot = [f"U+{ord(c):04X}" for c in STACKABLE_MARKS
              if ord(c) in cmap and ord(c) not in stackable]
    check(not cannot, f"every common accent can take a second one{label} "
                      f"(no Mark2 anchor: {cannot})")

    seats = {}

    def seat(mark_g):
        """A letter the mark attaches to as [letter, mark], exactly."""
        if mark_g in seats:
            return seats[mark_g]
        seats[mark_g] = None
        for _, sub in model.bases:
            if mark_g not in sub.MarkCoverage.glyphs:
                continue
            for base_g in sub.BaseCoverage.glyphs:
                if base_g not in rev or not build._bounds(gs, base_g):
                    continue
                text = chr(rev[base_g]) + chr(rev[mark_g])
                if len(unicodedata.normalize("NFC", text)) != 2:
                    continue
                infos, positions = shape(text, {})
                if [order[i.codepoint] for i in infos] != [base_g, mark_g]:
                    continue
                if model.on_base(base_g, mark_g) == (
                        positions[1].x_offset, positions[1].y_offset,
                        positions[1].x_advance):
                    seats[mark_g] = base_g
                    return base_g
        return None

    exact = 0
    wrong = {}
    for i, sub in model.stacks:
        ones = [g for g in sub.Mark1Coverage.glyphs if g in rev]
        twos = [g for g in sub.Mark2Coverage.glyphs if g in rev]
        if not ones or not twos:
            continue
        pairs = {(m2, ones[0]) for m2 in twos} | {(twos[0], m1) for m1 in ones}
        for m2, m1 in sorted(pairs, key=lambda p: (order.index(p[0]), order.index(p[1]))):
            if model.on_mark(m2, m1) is None:
                continue          # this class does not stack here
            base_g = seat(m2)
            if base_g is None:
                wrong.setdefault(i, []).append((m2, "attaches to no letter"))
                continue
            text = chr(rev[base_g]) + chr(rev[m2]) + chr(rev[m1])
            if len(unicodedata.normalize("NFC", text)) != 3:
                continue
            exact += _hold_run(model, shape, order, rev, text, wrong, i)
            # and the ink: the second mark's centre over the first's,
            # less where each sits on the letter alone (the marks'
            # own drawings differ), which leaves the Mark2 anchor's
            # sideways step
            stacked = _centres(shape, gs, order, text)
            alone = [_centres(shape, gs, order, chr(rev[base_g]) + chr(rev[m]))
                     for m in (m2, m1)]
            if stacked and all(alone):
                step = (stacked[2] - stacked[1]) - (alone[1][1] - alone[0][1])
                if abs(step) > _STACK_DX:
                    wrong.setdefault(i, []).append((m2, m1, "ink", round(step)))
    worst = {i: (len(v), v[:2]) for i, v in wrong.items()}
    check(exact and not wrong,
          f"the shaper stacks every second mark on the first{label} "
          f"({exact} marks exact; off, by lookup: {worst})")


def check_marks_clear(tf, shape, check, gs, label=""):
    """An accent sits ON an ascender letter, not through it: for each
    of CLEAR_BASES and CLEAR_MARKS, the mark's ink begins above the
    letter's.

    Source Code Pro places its marks entirely in GPOS -- the top anchor
    of an ascender is 229 units above an x-height letter's -- and a
    wrong anchor on either side is a mark drawn through the stem. A
    probe set, kept because it asks something no table bound can: the
    letters it names are exactly the ones whose ink reaches the mark."""
    cmap = tf.getBestCmap()
    order = tf.getGlyphOrder()
    through, pairs = {}, 0
    for base in CLEAR_BASES:
        for mark in CLEAR_MARKS:
            if ord(base) not in cmap or ord(mark) not in cmap:
                continue
            infos, positions = shape(base + mark, {})
            if len(infos) != 2:
                continue        # composed into one glyph: nothing to clear
            boxes = [build._bounds(gs, order[info.codepoint]) for info in infos]
            pairs += 1
            if None in boxes:
                through[base + mark] = None
            elif boxes[1][1] + positions[1].y_offset < boxes[0][3]:
                through[base + mark] = (round(boxes[0][3]),
                                        round(boxes[1][1] + positions[1].y_offset))
    check(not through, f"an accent clears the letter it sits on{label} "
                       f"({pairs} pairs; through: {through})")


def check_marks_seat(tf, shape, check, gs, label=""):
    """Every mark's ink lands on its letter's: shaped, and measured
    against the letter's ink rather than against the anchors.

    Every other gate reads the anchors, and check_marks_attach holds
    the shaper to those same anchors -- so an anchor wrong on ONE
    letter by less than a placement band (350 units into the ink, a
    third of a cell sideways; 5 px at 14 px) passed them all, as did a
    second anchor class the placement gate did not read, a
    mark-to-ligature lookup nothing walked, and every mark's outline
    moved 200 units with its anchor left behind (round 8, mutants 1,
    2, 3, 8, 10, 11). This asks the drawing: for every letter with two
    marks of each rule-following lookup and every mark with three
    letters, the first mark's ink begins within _SEAT_DY of the edge
    the lookup attaches by and its centre within _SEAT_DX of the
    letter's; and, per lookup, the medians are held to
    _SEAT_MEDIAN_DX / _SEAT_MEDIAN_DY, which a whole lookup's marks
    moved together cannot pass. A pair the shaper composes is the
    donor's own drawing and is not asked."""
    cmap = tf.getBestCmap()
    rev = {g: cp for cp, g in cmap.items()}
    order = tf.getGlyphOrder()
    hmtx = tf["hmtx"].metrics
    off = {}
    medians = {}
    for i, sub in _mark_base_subtables(tf):
        rule = anchors._anchor_rule(gs, sub)
        if rule is None:
            continue            # the donor's sparse lookups: no edge to hold to
        top = rule[0]
        marks = [g for g in sub.MarkCoverage.glyphs
                 if g in rev and rev[g] not in SPARSE_MARKS]
        bases = [g for g in sub.BaseCoverage.glyphs if g in rev]
        # every letter with the first mark it does not compose with,
        # and every mark on a few letters. A pair the shaper
        # composes used to be skipped, which left 50 letters of the top
        # lookup (E I N O U a e ... and every Greek vowel) never
        # measured (round 9, mutants L8, L9, L14)
        dxs, dys, rows = [], [], []

        def measure(base_g, mark_g):
            infos, positions = shape(chr(rev[base_g]) + chr(rev[mark_g]), {})
            got = [order[info.codepoint] for info in infos]
            if len(got) < 2:
                return False
            letter = build._bounds(gs, got[0])
            if not letter:
                return True
            for j in range(1, len(got)):
                mark = build._bounds(gs, got[j])
                if not mark or got[j] not in sub.MarkCoverage.glyphs:
                    continue
                x0 = hmtx[got[0]][0] + positions[j].x_offset
                dx = x0 + (mark[0] + mark[2]) / 2 - (letter[0] + letter[2]) / 2
                dy = ((positions[j].y_offset + mark[1] - letter[3]) if top
                      else (letter[1] - positions[j].y_offset - mark[3]))
                dxs.append(dx)
                dys.append(dy)
                rows.append((got[0], got[j], dx, dy, chr(rev[base_g])))
                lo, hi = _SEAT_DY[top]
                # and the mark's ink over the letter's: a fraction of
                # the mark's width, since a below-mark under one stem of
                # m or the ogonek at the foot of A are half off by design
                if not lo <= dy <= hi or abs(dx) > _SEAT_DX:
                    off.setdefault(i, []).append((got[0], got[j], round(dx), round(dy)))
                return True
            return True

        seen = set()
        for base_g in bases:
            for mark_g in marks:
                if measure(base_g, mark_g):
                    seen.add((base_g, mark_g))
                    break
        # every mark on the first three letters of each case: after a
        # capital the shaper swaps the mark for its raised form, so the
        # lowercase letters are where the mark itself is measured
        firsts = bases[:3] + [b for b in bases
                              if unicodedata.category(chr(rev[b])) == "Ll"][:6]
        for base_g in firsts:
            for mark_g in marks:
                if (base_g, mark_g) not in seen:
                    measure(base_g, mark_g)
        if dxs:
            mdx, mdy = statistics.median(dxs), statistics.median(dys)
            medians[i] = (round(mdx), round(mdy))
            if abs(mdx) > _SEAT_MEDIAN_DX or not _SEAT_MEDIAN_DY[0] <= mdy <= _SEAT_MEDIAN_DY[1]:
                off.setdefault(i, []).append(("median", round(mdx), round(mdy)))
            # and each letter against its kind's median: the letters of
            # a category, under one mark, the full-width ones (Source
            # Han Sans's drawings, at another size) apart -- where the
            # kind has enough letters to have a median
            by_kind = {}
            for base_g, mark_g, dx, dy, ch in rows:
                kind = (unicodedata.category(ch), mark_g,
                        unicodedata.east_asian_width(ch) in ("W", "F"))
                by_kind.setdefault(kind, []).append(dy)
            kind_median = {kind: statistics.median(v) for kind, v in by_kind.items()
                           if len(v) >= _SEAT_KIND}
            by_mark = {}
            for base_g, mark_g, dx, dy, ch in rows:
                by_mark.setdefault(mark_g, []).append(dx)
            for mark_g, v in by_mark.items():
                # a median of one letter is that letter's own offset
                # (b sets every accent over its stem, 180 left)
                if len(v) >= 3 and abs(statistics.median(v) - mdx) > _MARK_DX_SPREAD:
                    off.setdefault(i, []).append((mark_g, "dx", round(statistics.median(v)),
                                                  "lookup", round(mdx)))
            for base_g, mark_g, dx, dy, ch in rows:
                kind = (unicodedata.category(ch), mark_g,
                        unicodedata.east_asian_width(ch) in ("W", "F"))
                if ch in SEAT_EDGE_LETTERS or kind not in kind_median:
                    continue
                if abs(dy - kind_median[kind]) > _SEAT_SPREAD:
                    off.setdefault(i, []).append((base_g, mark_g, "dy", round(dy),
                                                  "kind", round(kind_median[kind])))
    worst = {i: (len(v), v[:2]) for i, v in off.items()}
    check(medians and not off,
          f"every mark's ink sits on its letter's{label} (medians dx, dy by lookup: "
          f"{medians}; off: {worst})")


def check_letter_glyphs(tf, check, gs, label=""):
    """The ASCII letters and digits each map to a glyph of their own
    that draws, and .notdef draws: a cmap that sends 'e' to the space
    or to 'o' passed every gate that reads the cmap by glyph, and a
    blank .notdef renders an unknown character as nothing rather than
    a box."""
    cmap = tf.getBestCmap()
    letters = [chr(c) for c in (*range(0x30, 0x3A), *range(0x41, 0x5B), *range(0x61, 0x7B))]
    seen = {}
    blank, shared = [], []
    for ch in letters:
        g = cmap.get(ord(ch))
        if g is None:
            blank.append(ch)
            continue
        if not build._bounds(gs, g):
            blank.append(ch)
        if g in seen:
            shared.append((ch, seen[g]))
        seen[g] = ch
    check(not blank and not shared,
          f"every ASCII letter and digit has an inked glyph of its own{label} "
          f"(blank: {blank}; shared: {shared})")
    check(bool(build._bounds(gs, tf.getGlyphOrder()[0])), f".notdef draws{label}")


def check_cap_forms(tf, shape, check, label=""):
    """After every capital, an above-mark is swapped for a raised form:
    the acute after a capital is never the plain acute.

    Source Code Pro's ccmp names the capitals that raise an accent, and
    named the Latin ones only in the italic, the Latin and Cyrillic in
    the upright: Α+U+0301 set the lowercase acute 80-96 units above the
    capital, taller than the line at Bold
    (anchors.raise_marks_after_capitals). Asked of every cmapped
    uppercase letter of the Latin and Cyrillic scripts that no
    precomposed character absorbs, on a face that raises at all. The
    Greek capitals are the donor's own case: after them the acute is
    the tonos form, set at the letter's shoulder, and the raised form
    is not what Greek asks for."""
    cmap = tf.getBestCmap()
    order = tf.getGlyphOrder()
    if ord("B") not in cmap or 0x0301 not in cmap:
        return
    infos, _ = shape("B\u0301", {})
    if len(infos) == 2 and order[infos[1].codepoint] == cmap[0x0301]:
        # this used to return here, "this face does not raise: nothing
        # to hold" -- and a face whose raising chain was deleted passed
        # every gate (round 9, mutant L10)
        check(False, f"B raises the accent after it{label} (the plain acute)")
        return
    if len(infos) != 2:
        return
    low, probed = [], 0
    for cp, g in sorted(cmap.items()):
        ch = chr(cp)
        if not any(lo <= cp <= hi for lo, hi in LETTER_RANGES) or 0x0370 <= cp <= 0x03FF \
                or 0x1F00 <= cp <= 0x1FFF:
            continue
        if unicodedata.category(ch) != "Lu" or len(unicodedata.normalize("NFC", ch + "\u0301")) == 1:
            continue
        infos, _ = shape(ch + "\u0301", {})
        if len(infos) != 2:
            continue
        probed += 1
        if order[infos[1].codepoint] == cmap[0x0301]:
            low.append(ch)
    check(probed and not low, f"every capital raises the accent after it{label} "
                              f"({probed} capitals; low: {''.join(low)})")


def check_tie_bars(tf, shape, check, gs, label=""):
    """A double diacritic straddles the pair it joins: a+U+0361+b draws
    the tie from inside a's cell to inside b's, g+U+035F+j the same
    below. Unanchored by design (DOUBLE_SPAN), so the ink is what says
    it is drawn where it should be."""
    cmap = tf.getBestCmap()
    order = tf.getGlyphOrder()
    hmtx = tf["hmtx"].metrics
    ties = {}
    for base, mark, after in (("a", "\u0361", "b"), ("g", "\u035f", "j")):
        if any(ord(c) not in cmap for c in (base, mark, after)):
            continue
        infos, positions = shape(base + mark + after, {})
        if len(infos) != 3:
            continue
        box = build._bounds(gs, order[infos[1].codepoint])
        pen_x = positions[0].x_advance
        adv = hmtx[cmap[ord(base)]][0]
        span = None if box is None else (box[0] + pen_x + positions[1].x_offset,
                                          box[2] + pen_x + positions[1].x_offset)
        # to the unit: Source Code Pro Italic sets the below tie's left
        # end on the cell edge at Bold, and the variable font interpolates
        # it 0.14 units past (the donor's own instance draws the same)
        if span is not None:
            span = tuple(round(v) for v in span)
        if span is None or not 0 <= span[0] < adv < span[1]:
            ties[base + mark + after] = span
    check(not ties, f"the tie bar straddles the pair it joins{label} (off: {ties})")


# What the italic faces cannot do for Greek, keyed by what is MEASURED
# (see check_greek_accents), so a NEW gap fails and these stay listed:
# the italic's Greek letters come from Source Sans 3 Italic, whose
# accents and breathing marks are not imported (only its outlines and
# base anchors are, build_latin.graft), and Source Code Pro Italic has
# no Greek 'locl' of its own. So the italic sets the Latin accent on a
# Greek capital -- raised, as after every capital -- and composes no
# breathing mark. docs/gengou-plan.md carries the measurements.
GREEK_ITALIC_GAP = {"\u0392": "the Latin accent",
                    "\u03c1\u0313\u0301": 3, "\u03b1\u0313\u0300": 3}


def check_dotless(tf, shape, check, label=""):
    """i and j lose their dot under an above-mark: Source Code Pro's
    ccmp swaps them for the dotless forms before a combining mark of
    the above class, and a face whose rule is gone draws the mark on
    the dot (round 9, mutant L7). Every above-mark the face has is
    asked, except the two comma-aboves U+0312 and U+0313, which the
    donor itself leaves out of the class."""
    cmap = tf.getBestCmap()
    order = tf.getGlyphOrder()
    if not any(ord(base) in cmap for base in "ij"):
        return
    dotted, probed = {}, 0
    for base in "ij":
        if ord(base) not in cmap:
            continue
        for cp in range(0x0300, 0x0315):
            if cp not in cmap or cp in (0x0312, 0x0313):
                continue
            infos, _ = shape(base + chr(cp), {})
            if len(infos) != 2:
                continue
            probed += 1
            if order[infos[0].codepoint] == cmap[ord(base)]:
                dotted.setdefault(base, []).append(f"U+{cp:04X}")
    check(probed and not dotted, f"i and j lose the dot under an accent{label} "
                                 f"({probed} probed; dotted: {dotted})")


def check_greek_accents(tf, shape, check, label=""):
    """Greek gets the Greek accents. Source Code Pro maps them under
    'locl' for script grek -- the tonos is 132 units wide where the
    Latin cap acute is 188 and sits 138 units lower -- and its own ccmp
    composes the breathing marks from those locl forms, so without the
    feature rho + U+0313 + U+0301 never composed and drew the psili
    inside the acute (build.import_scp_locl).

    Measured as the shaper sees it: the accent after a Greek capital is
    not the one after the Latin capital (B and Beta are what NFC leaves
    decomposed), and a breathing mark plus accent composes into one
    mark glyph. An italic face is held to GREEK_ITALIC_GAP instead of
    exempted: this used to skip every italic face, and passed the
    capital probe by accident once the italic stopped raising the
    accent after a Greek capital only."""
    cmap = tf.getBestCmap()
    greek = {}
    for latin_base, greek_base in (("B", "\u0392"), ("A", "\u0391")):
        if any(ord(c) not in cmap for c in (latin_base, greek_base, "\u0301")):
            continue
        pair = [shape(b + "\u0301", {})[0] for b in (latin_base, greek_base)]
        if any(len(infos) != 2 for infos in pair):
            continue
        if pair[0][1].codepoint == pair[1][1].codepoint:
            greek[greek_base] = "the Latin accent"
    for text in ("\u03c1\u0313\u0301", "\u03b1\u0313\u0300"):
        if any(ord(c) not in cmap for c in text):
            continue
        got = len(shape(text, {})[0])
        if got != 2:
            greek[text] = got
    known = GREEK_ITALIC_GAP if is_italic(tf) else {}
    off = {k: v for k, v in greek.items() if known.get(k) != v}
    check(not off, f"Greek takes the Greek accents and composes its "
                   f"breathing marks{label} (off: {off}"
                   + (f"; known italic gaps: {sorted(known)}" if known else "")
                   + ")")


def check_widths_by_class(tf, shape, check, cell, full, label=""):
    """Every character's advance follows its East Asian Width, and the
    shaper gives it that advance alone under the default features.

    Na and H are a cell, W and F the full width (or a cell, for the
    few in WIDE_IN_ONE_CELL), A and N either, but Monaspace's ambiguous
    symbols and .notdef a cell by policy; a mark is that or 0. A face
    with no full width (`full` None) has no W or F but those. The
    shaped advance is the hmtx one, so a stray placement under any
    feature -- a SinglePos advance under ccmp moved the column after
    '0' 200 units (round 9, mutants L5b, J8) -- fails here."""
    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"].metrics
    gdef = getattr(tf.get("GDEF"), "table", None)
    classes = getattr(getattr(gdef, "GlyphClassDef", None), "classDefs", None) or {}
    off, shaped, probed = {}, {}, 0
    for cp, g in sorted(cmap.items()):
        ch = chr(cp)
        eaw = unicodedata.east_asian_width(ch)
        adv = hmtx[g][0]
        if cp in MULTI_EM:
            allowed = {MULTI_EM[cp] * (full or 2 * cell)}
        elif eaw in ("Na", "H") or ch in build.MONA_AMBIGUOUS:
            # (Monaspace's ambiguous-width symbols are a cell by policy)
            allowed = {cell}
        elif eaw in ("W", "F"):
            allowed = {cell} if cp in WIDE_IN_ONE_CELL else {full}
        else:
            allowed = {cell, full}
        if classes.get(g) == 3 or unicodedata.category(ch).startswith("M"):
            allowed = allowed | {0}
        if adv not in allowed:
            off[ch] = (eaw, adv)
            continue
        if cp in DEFAULT_IGNORABLE:
            continue
        infos, positions = shape(ch, {})
        if len(infos) != 1:
            continue
        probed += 1
        got = positions[0].x_advance
        # a shaper zeroes a mark's advance whatever the lookups say
        if got != adv and not (classes.get(g) == 3 and got == 0):
            shaped[ch] = (adv, got)
    # and .notdef: a terminal gives an unknown character one column,
    # and a wide box pushes the line
    if hmtx[tf.getGlyphOrder()[0]][0] != cell:
        off[".notdef"] = ("policy", hmtx[tf.getGlyphOrder()[0]][0])
    check(probed and not off and not shaped,
          f"every advance follows the character's width{label} "
          f"({probed} shaped; off by class: {dict(list(off.items())[:4])}; "
          f"shaped otherwise: {dict(list(shaped.items())[:4])})")


def check_glyph_placement(tf, check, gs, cell, full, label=""):
    """Each glyph's ink sits in its own cell where its kind belongs:
    a narrow letter, digit or half-width kana centred within
    _CENTRE_BAND, a digit or capital on the baseline within _BASELINE,
    an ideograph or kana inside the em box (_IDEOGRAPH_Y) and, like
    every full-width glyph, inside its cell to _EDGE, and a
    zero-advance mark drawn in the cell before (_ZERO_ADVANCE_X).

    ink_spill allows half a cell, centring was a mean, and there was
    no bound on a glyph's height at all: one glyph moved 250 units
    sideways or 200 up passed every gate (round 9, mutants L2, L3,
    J2, J13, V3b). Per glyph, against its own cell, no donor needed."""
    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"].metrics
    off = {}
    n = 0
    for cp, g in sorted(cmap.items()):
        ch = chr(cp)
        box = build._bounds(gs, g)
        if box is None:
            continue
        adv = hmtx[g][0]
        eaw = unicodedata.east_asian_width(ch)
        cat = unicodedata.category(ch)
        n += 1
        if adv == cell and ((eaw == "Na" and cat in ("Lu", "Ll", "Nd"))
                            or (eaw == "H" and cat == "Lo")):
            centre = (box[0] + box[2]) / 2 - cell / 2
            if abs(centre) > _CENTRE_BAND:
                off[ch] = ("centre", round(centre))
            if (cat == "Nd" or (cat == "Lu" and ch not in "JQ")) \
                    and not _BASELINE[0] <= box[1] <= _BASELINE[1]:
                off[ch] = ("baseline", round(box[1]))
        elif full and adv == full and eaw in ("W", "F"):
            if box[0] < -_EDGE or box[2] > full + _EDGE:
                off[ch] = ("cell", round(box[0]), round(box[2]))
            elif (0x4E00 <= cp <= 0x9FFF or 0x3041 <= cp <= 0x30FF) \
                    and not _IDEOGRAPH_Y[0] <= box[1] <= box[3] <= _IDEOGRAPH_Y[1]:
                # no centre band for an ideograph: 亻丬亅 sit at one
                # side of the cell by design (verify.py holds the Term
                # face's widening against its JP sibling instead)
                off[ch] = ("em box", round(box[1]), round(box[3]))
        elif adv == 0 and cp not in DOUBLE_SPAN and full:
            if box[0] < -full + _ZERO_ADVANCE_X[0] or box[2] > _ZERO_ADVANCE_X[1]:
                off[ch] = ("before", round(box[0]), round(box[2]))
    check(n and not off, f"every glyph's ink sits in its cell{label} "
                         f"({n} drawn; off: {dict(list(off.items())[:5])})")


def check_cells(tf, check, shape, gs, cell, full=None, label=""):
    """One glyph in one cell: its advance by its width class, as
    shaped, and its ink where that class sits."""
    check_widths_by_class(tf, shape, check, cell, full, label)
    check_glyph_placement(tf, check, gs, cell, full, label)


def check_marks(tf, check, shape, gs, label=""):
    """Every mark gate, in the order they build on each other: the
    features and classes, the lookups' reachability, the language
    systems, the anchors themselves, the coverage, then what the
    shaper makes of them -- exactly, clear of the letter, and in the
    forms each script asks for."""
    check_mark_features(tf, check, label)
    check_mark_reachability(tf, check, label)
    check_tone_lookups(tf, check, label)
    check_langsys_parity(tf, check, label)
    check_anchor_placement(tf, check, gs, label)
    check_anchor_coverage(tf, check, gs, label)
    check_marks_attach(tf, shape, check, label)
    check_marks_stack(tf, shape, check, label)
    check_marks_seat(tf, shape, check, gs, label)
    check_marks_clear(tf, shape, check, gs, label)
    check_cap_forms(tf, shape, check, label)
    check_dotless(tf, shape, check, label)
    check_greek_accents(tf, shape, check, label)
    check_tie_bars(tf, shape, check, gs, label)


def vf_region_peaks(tf, axis_tag="wght"):
    """The user-space locations of every variation region's peak on
    `axis_tag`, from the CFF2 and GDEF variation stores -- the masters.

    A delta scoped to the region that peaks at an intermediate master
    is zero at the default and at the axis ends, and a fraction of
    itself at the named instances between: verify_latin_vf.py probing
    the default, the ends and the instances passed a font whose base
    anchors dropped 400 units at the wght-365 master (mutant 11). The
    peaks are read through avar back to user space."""
    fvar = tf["fvar"]
    index = next(i for i, a in enumerate(fvar.axes) if a.axisTag == axis_tag)
    axis = fvar.axes[index]
    peaks = set()
    stores = []
    if "GDEF" in tf and getattr(tf["GDEF"].table, "VarStore", None) is not None:
        stores.append(tf["GDEF"].table.VarStore)
    if "CFF2" in tf:
        vs = getattr(tf["CFF2"].cff.topDictIndex[0], "VarStore", None)
        if vs is not None:
            stores.append(vs.otVarStore)
    for store in stores:
        for region in store.VarRegionList.Region:
            peaks.add(region.VarRegionAxis[index].PeakCoord)
    segments = tf["avar"].segments.get(axis_tag, {}) if "avar" in tf else {}
    # a strictly increasing map inverts by swapping; the F2Dot14 flat
    # step SCP's avar carries (two inputs a unit apart, one output) loses
    # one key here, which puts the inverse a few 1e-5 off across it
    inverse = {v: k for k, v in segments.items()}

    def user(n):
        if inverse:
            n = piecewiseLinearMap(n, inverse)
        span = (axis.defaultValue - axis.minValue) if n < 0 else (axis.maxValue - axis.defaultValue)
        return axis.defaultValue + n * span
    return sorted(user(n) for n in peaks if n != 0)


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


def check_font_matrix(tf, check):
    """The top DICT and every FontDict draw at 1/1000: fontTools reads
    outlines through neither, so a FontMatrix of 0.0007 drew every
    glyph at 70% in FreeType while every gate here read them whole
    (round 10, mutants G8, J29)."""
    unit = [0.001, 0, 0, 0.001, 0, 0]
    cff = tf["CFF2" if "CFF2" in tf else "CFF "].cff
    td = cff.topDictIndex[0]
    dicts = [("top", td)] + [(f"FD {i}", fd) for i, fd in enumerate(getattr(td, "FDArray", None) or [])]
    off = [name for name, d in dicts
           if list(getattr(d, "FontMatrix", unit)) != unit]
    check(not off, f"every FontMatrix is 1/1000 (off: {off})")


def check_line_metrics(tf, check):
    """hhea and typo are LINE_METRICS, with USE_TYPO_METRICS."""
    hhea, os2 = tf["hhea"], tf["OS/2"]
    got = ((hhea.ascent, hhea.descent, hhea.lineGap),
           (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap))
    check(got == (LINE_METRICS, LINE_METRICS),
          f"line metrics {LINE_METRICS} (hhea = typo), got {got}")
    check(bool(os2.fsSelection & (1 << 7)), "USE_TYPO_METRICS set")


def check_gdef_classes(tf, check):
    """No spacing character is a GDEF mark: a shaper zeroes the advance
    of every class-3 glyph, so '?' classed as a mark drew over the k
    before it (round 10, mutants G3, J27). check_gdef_marks asks the
    converse of the combining marks."""
    cmap = tf.getBestCmap()
    gdef = getattr(tf.get("GDEF"), "table", None)
    classes = getattr(getattr(gdef, "GlyphClassDef", None), "classDefs", None) or {}
    hmtx = tf["hmtx"].metrics
    off = [f"U+{cp:04X}" for cp, g in sorted(cmap.items())
           if classes.get(g) == 3 and hmtx[g][0] > 0
           and not unicodedata.category(chr(cp)).startswith("M")]
    check(not off, f"no spacing character is a GDEF mark ({len(off)}: {off[:5]})")


def check_pair_positioning(tf, check, allowed=("vkrn",)):
    """GPOS pair positioning only under `allowed`: the build drops kern,
    palt and halt because the grid is the spacing, and a PairPos under
    ccmp moved the letter after 'a' 300 units (round 10, mutants G4,
    J28b, J46). Source Han Sans's vertical kerning stays, opt-in."""
    off = []
    for i, kind, _subs, tags in _pos_lookups(tf):
        if kind == 2 and not tags <= set(allowed):
            off.append((i, sorted(tags)))
    check(not off, f"pair positioning only under {list(allowed)} (off: {off})")


def check_substitution_identity(tf, check):
    """A substitution never turns a character into another character:
    where a GSUB rule's input and output are both encoded, the two are
    compatibility-equivalent (NFKD) -- か + U+3099 to が, ( to its
    vertical form, A to full-width Ａ -- and never rn to m, 0 to O, or
    ａ to ｂ's half-width form (round 10, mutants G5, G37, J51). The
    unencoded outputs (the .cap accents, the dotless i, the variants)
    are what the other gates measure. Asked of the lookups a shaper
    runs by default (DEFAULT_FEATURES, and what those call): an opt-in
    feature is allowed to change the character -- jp78 gives another
    kanji, vert the vertical form of a different dash -- and the two
    default rules that do (i and j to the encoded dotless letters, the
    vertical repeat marks 〳〵 composed into 〱) are named."""
    cmap = tf.getBestCmap()
    rev = {g: cp for cp, g in cmap.items()}
    table = tf["GSUB"].table
    live = set()
    for fr in table.FeatureList.FeatureRecord:
        if fr.FeatureTag in DEFAULT_FEATURES:
            live.update(fr.Feature.LookupListIndex)
    stack = list(live)
    while stack:
        i = stack.pop()
        for sub in build._unwrap(table.LookupList.Lookup[i])[1]:
            for rec in build._lookup_records(sub):
                if rec.LookupListIndex not in live:
                    live.add(rec.LookupListIndex)
                    stack.append(rec.LookupListIndex)

    def same(inputs, output):
        if output not in rev or any(g not in rev for g in inputs):
            return True
        want = unicodedata.normalize("NFKD", "".join(chr(rev[g]) for g in inputs))
        got = unicodedata.normalize("NFKD", chr(rev[output]))
        return got == want or (want, got) in SUBSTITUTED_CHARACTERS

    off, rules = {}, 0
    for i, lookup in enumerate(table.LookupList.Lookup):
        if i not in live:
            continue
        kind, subs = build._unwrap(lookup)
        for sub in subs:
            if kind == 1:
                for g, out in sub.mapping.items():
                    rules += 1
                    if not same([g], out):
                        off.setdefault(i, []).append((g, out))
            elif kind == 4:
                for first, ligs in sub.ligatures.items():
                    for lig in ligs:
                        rules += 1
                        if not same([first, *lig.Component], lig.LigGlyph):
                            off.setdefault(i, []).append((first, lig.LigGlyph))
    worst = {i: (len(v), v[:2]) for i, v in off.items()}
    check(rules and not off, f"no substitution turns a character into another "
                             f"({rules} rules; off by lookup: {worst})")


def check_ligature_cells(tf, shape, check, gs, cell, label=""):
    """Every declared ligature's glyph sits in its cells: ink inside
    [0, cells x cell] to _LIG_EDGE, and no lower or higher than the
    characters it is cut from by _LIG_Y (an unencoded glyph, so
    check_glyph_placement never sees it; round 10, mutants G1, G1b,
    G1c, V10)."""
    cmap = tf.getBestCmap()
    order = tf.getGlyphOrder()
    off, n = {}, 0
    for seq, spec in build.LIGATURES.items():
        if any(ord(c) not in cmap for c in seq):
            continue
        infos, positions = shape(seq, {"calt": True, "liga": True})
        if len(infos) != 1:
            continue                # the multi-glyph ones: their parts are cmapped
        n += 1
        box = build._bounds(gs, order[infos[0].codepoint])
        parts = [build._bounds(gs, cmap[ord(c)]) for c in seq]
        if box is None or any(p is None for p in parts):
            off[seq] = "blank"
            continue
        lo, hi = min(p[1] for p in parts), max(p[3] for p in parts)
        width = spec["cells"] * cell
        if box[0] < -_LIG_EDGE or box[2] > width + _LIG_EDGE:
            off[seq] = ("cells", round(box[0]), round(box[2]))
        elif box[1] < lo - _LIG_Y[0] or box[3] > hi + _LIG_Y[1]:
            off[seq] = ("height", round(box[1]), round(box[3]), "parts", round(lo), round(hi))
    check(n and not off, f"every ligature sits in its cells at its parts' height{label} "
                         f"({n} ligatures; off: {off})")


def check_blank_glyphs(tf, check, gs):
    """.notdef draws (an unknown character shows a box, not nothing),
    and the spaces and the default-ignorable characters draw nothing
    (round 10, mutants G25, G26)."""
    cmap = tf.getBestCmap()
    notdef = build._bounds(gs, tf.getGlyphOrder()[0])
    check(notdef is not None and notdef[2] - notdef[0] > 100 and notdef[3] - notdef[1] > 100,
          f".notdef draws a box ({notdef})")
    # (the soft hyphen is drawn, as Source Code Pro draws it: a hyphen
    # for the renderer that shows one at a break; a shaper hides it)
    inked = [f"U+{cp:04X}" for cp, g in sorted(cmap.items())
             if (unicodedata.category(chr(cp)) in ("Zs", "Cf") or cp in DEFAULT_IGNORABLE)
             and cp != 0x00AD and build._bounds(gs, g) is not None]
    check(not inked, f"every space and ignorable is blank (inked: {inked})")


def check_name_composition(tf, check):
    """nameID 4 is the family and subfamily, 6 the PostScript pair: a
    Regular calling itself 'Gengou Bold' in 4 and 6 passed (round 10,
    mutant G13)."""
    name = tf["name"]
    fam = name.getDebugName(16) or name.getDebugName(1)
    sub = name.getDebugName(17) or name.getDebugName(2)
    full, ps = name.getDebugName(4), name.getDebugName(6)
    want_full = fam if sub == "Regular" else f"{fam} {sub}"
    check(full in (want_full, f"{fam} {sub}"), f"nameID 4 is family + subfamily ({full!r})")
    # the family half is abbreviated by design (GengouNFM for the Nerd
    # Fonts face); the style half is the subfamily, and there are no spaces
    want_style = sub.replace(" ", "")
    styles = {want_style, "Roman"} if want_style == "Regular" else {want_style}   # a variable font's upright is "Roman"
    check(" " not in ps and ps.split("-")[-1] in styles,
          f"nameID 6 ends in the subfamily ({ps!r}, want ...-{want_style})")


def check_family_cmap(tf, check, reference):
    """Every face of a family maps the same characters: the face's cmap
    equals `reference`'s (a sibling built beside it), or, for a face
    that adds to it, contains it. A codepoint dropped from one face
    passed its own repertoire floor (round 10, mutant G9)."""
    if reference is None:
        check(True, "family cmap (no sibling beside the face to compare)")
        return
    mine, theirs = set(tf.getBestCmap()), set(reference.getBestCmap())
    missing = sorted(theirs - mine)
    check(not missing, f"the face maps every character its sibling maps "
                       f"({len(missing)} missing: {[f'U+{c:04X}' for c in missing[:5]]})")


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
