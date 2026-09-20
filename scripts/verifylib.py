"""Shared pieces of the verification scripts (verify.py, verify_latin.py,
verify_latin_vf.py, golden.py): a HarfBuzz shaper, the ok/FAIL check
tally, the CFF hint probe, and the static-face listing nerdpatch.py and
harmonize_latin.py share.
"""

import math
import sys
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
    true extreme (the stale Sumi Moji bearings this catches were tens of
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


def check_tables(tf, check, bounds, hmtx, cmap, codepages=False):
    """The numbers a rasterizer clips and lays out by, read back from
    the outlines: head's bounding box, hhea's four extents, OS/2's
    embedding permission, vendor id, character-index range and range
    bits, post's underline, and every Unicode cmap subtable.

    The build turns fontTools' own recalculation off (recalcBBoxes =
    False) and works these out in one pass, so they are only as right
    as that pass — and nothing read them: zeroing head's box, hhea's
    extents or the range bits all passed, on the JP faces until round
    42 and on the Latin ones until this round, where the 4-cell
    ligatures then lay outside the declared box."""
    head, hhea, os2 = tf["head"], tf["hhea"], tf["OS/2"]
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
    check(os2.fsType == 0, f"OS/2 fsType is installable ({os2.fsType})")
    check(os2.achVendID == "SUMI", f"OS/2 vendor id ({os2.achVendID!r})")
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
