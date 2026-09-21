"""Unit tests for scripts/verifylib.py (the pieces shared by the verify /
packaging scripts) that need no font files."""

import sys
from pathlib import Path

from fontTools.misc.psCharStrings import T2CharString

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import verifylib  # noqa: E402


def test_static_faces_skips_variable_fonts_and_sorts(tmp_path):
    for name in ("Gengou-Regular.otf", "Gengou-Italic[wght].otf", "Gengou[wght].otf",
                 "Gengou-Bold.otf", "GengouTerm-Regular.otf", "Other-Regular.otf"):
        (tmp_path / name).write_bytes(b"")
    got = [p.name for p in verifylib.static_faces(tmp_path, "Gengou")]
    assert got == ["Gengou-Bold.otf", "Gengou-Regular.otf"]


def test_static_faces_empty_dir(tmp_path):
    assert verifylib.static_faces(tmp_path, "Gengou") == []


def test_checker_tallies_and_prints(capsys):
    check = verifylib.Checker()
    assert check(True, "fine") is True
    assert check.failed is False and check.exit_code() == 0
    assert check(False, "broken") is False
    assert check.failed is True and check.exit_code() == 1
    assert check(True, "still fine") is True
    assert check.failed is True      # a later pass does not clear a failure
    out = capsys.readouterr().out.splitlines()
    assert out == ["ok   fine", "FAIL broken", "ok   still fine"]


# --- glyph_has_hint ----------------------------------------------------------

class _Private:
    def __init__(self, subrs):
        self.Subrs = subrs


def _cs(program, private=None, global_subrs=None):
    cs = T2CharString(program=list(program), private=private,
                      globalSubrs=global_subrs if global_subrs is not None else [])
    return cs


def test_glyph_has_hint_sees_a_direct_hint_and_a_bare_outline():
    assert verifylib.glyph_has_hint(_cs([10, 20, "hstem", 0, 0, "rmoveto", "endchar"]))
    assert not verifylib.glyph_has_hint(_cs([0, 0, "rmoveto", 100, "hlineto", "endchar"]))


def test_glyph_has_hint_follows_local_and_global_subroutines():
    # bias 107 for small subr indexes: operand -107 -> subr 0
    local = [_cs([10, 20, "vstem", "return"])]
    glob = [_cs(["hintmask", "return"])]
    via_local = _cs([-107, "callsubr", "endchar"], private=_Private(local), global_subrs=glob)
    via_global = _cs([-107, "callgsubr", "endchar"], private=_Private(local), global_subrs=glob)
    plain = _cs(["endchar"], private=_Private(local), global_subrs=glob)
    assert verifylib.glyph_has_hint(via_local)
    assert verifylib.glyph_has_hint(via_global)
    assert not verifylib.glyph_has_hint(plain)


def test_glyph_has_hint_does_not_loop_on_a_recursive_subroutine():
    local = [_cs([-107, "callsubr", "return"])]      # subr 0 calls itself
    cs = _cs([-107, "callsubr", "endchar"], private=_Private(local))
    assert not verifylib.glyph_has_hint(cs)


def test_hmtx_mismatches_reports_widths_and_bearings():
    from test_build import _extents_font
    font, _ = _extents_font()
    assert verifylib.hmtx_mismatches(font)[:2] == ([], [])
    font["hmtx"].metrics["A"] = (650, 0)       # width off by 50, lsb off by 20
    font["hmtx"].metrics["space"] = (600, 50)  # blank: no xMin to disagree with
    widths, bearings, bounds = verifylib.hmtx_mismatches(font)
    assert widths == [("A", 600, 650)]
    assert bearings == [("A", 20, 0)]
    # the boxes come back too, so a caller need not draw them again
    assert bounds["A"] == (20, -30, 520, 700) and "space" not in bounds


def test_weight_name_reads_the_wws_subfamily():
    """build.set_names writes the WWS pair, so the Regular italic's
    subfamily is plain "Italic" — a bare replace of " Italic" leaves
    that one as "Italic", which is in no weight table, and every check
    keyed on the weight skipped every italic face."""
    assert verifylib.weight_name("Regular") == "Regular"
    assert verifylib.weight_name("Italic") == "Regular"
    assert verifylib.weight_name("Bold Italic") == "Bold"
    assert verifylib.weight_name("SemiBold") == "SemiBold"
    assert verifylib.weight_name("") == "Regular"


def _stat_font(weights, italic, *, ital_flags=0x2, linked=1):
    from conftest import make_font
    from fontTools import ttLib
    from fontTools.otlLib import builder as otl
    font = make_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600})
    values = []
    for weight in weights:
        value = {"value": {"Light": 300, "Regular": 400, "Bold": 700}[weight],
                 "name": weight}
        if weight == "Regular":
            value.update(flags=0x2, linkedValue=700)
        values.append(value)
    ital = ({"value": 1, "name": "Italic"} if italic else
            {"value": 0, "name": "Regular", "flags": ital_flags,
             "linkedValue": linked})
    otl.buildStatTable(font, [{"tag": "wght", "name": "Weight", "values": values},
                              {"tag": "ital", "name": "Italic", "values": [ital]}],
                       elidedFallbackName="Regular", macNames=False)
    assert isinstance(font, ttLib.TTFont)
    return font


def test_check_stat_wants_this_face_s_own_value(capsys):
    """A static face carries its OWN wght value: build.add_stat takes one
    weight name for a reason (a static listing the family's whole set
    confuses Windows' family model), and nothing read the result — a
    Regular whose STAT said 900, or a face listing every weight,
    passed."""
    check = verifylib.Checker()
    verifylib.check_stat(_stat_font(["Regular"], False), check, "Regular", False)
    assert not check.failed
    check = verifylib.Checker()
    verifylib.check_stat(_stat_font(["Regular"], False), check, "Bold", False)
    assert check.failed                       # the value is not this face's
    check = verifylib.Checker()
    verifylib.check_stat(_stat_font(["Light", "Regular", "Bold"], False),
                         check, "Regular", False)
    assert check.failed                       # the whole family's values
    check = verifylib.Checker()
    verifylib.check_stat(_stat_font(["Regular"], True), check, "Regular", False)
    assert check.failed                       # an upright face saying Italic
    check = verifylib.Checker()
    verifylib.check_stat(_stat_font(["Regular"], False, ital_flags=0),
                         check, "Regular", False)
    assert check.failed                       # upright ital value not elidable


def test_check_gdef_marks_wants_every_combining_mark_classed(capsys):
    """build.classify_unicode_marks exists because the donor leaves the
    double tie bars unclassed, and a mark a shaper reads as a base
    positions as one. Deleting the call rebuilt and verified clean."""
    from conftest import make_font
    from fontTools.ttLib import newTable
    from fontTools.ttLib.tables import otTables
    cmap = {ord("a"): "a", 0x0301: "acute", 0x0361: "tie"}
    font = make_font([".notdef", "a", "acute", "tie"], cmap,
                     {"a": 600, "acute": 0, "tie": 0})
    check = verifylib.Checker()
    verifylib.check_gdef_marks(font, check, cmap)
    assert check.failed                       # no GDEF at all

    gdef = newTable("GDEF")
    gdef.table = otTables.GDEF()
    gdef.table.Version = 0x00010000
    gdef.table.GlyphClassDef = otTables.GlyphClassDef()
    gdef.table.GlyphClassDef.classDefs = {"a": 1, "acute": 3, "tie": 3}
    font["GDEF"] = gdef
    check = verifylib.Checker()
    verifylib.check_gdef_marks(font, check, cmap)
    assert not check.failed

    del gdef.table.GlyphClassDef.classDefs["tie"]
    check = verifylib.Checker()
    verifylib.check_gdef_marks(font, check, cmap)
    assert check.failed


def test_checker_prints_a_skip_for_a_check_that_could_not_run(capsys):
    """nerdpatch.icon_checks reports its symbols-font checks as "not
    checked" when NF_SYMBOLS is unset; it used to report them as
    passing, which read as six more ok lines than were earned."""
    check = verifylib.Checker()
    assert check(None, "not checked") is None
    assert check.failed is False and check.exit_code() == 0
    assert capsys.readouterr().out == "skip not checked\n"


def test_private_values_takes_the_default_of_a_cff2_blend():
    """A CFF2 Private entry is blended: [default, delta per region] for a
    scalar, a list of those for an array. Only the default has to be a
    whole unit — varLib works the deltas out from the masters with the
    region scalars, so they come out fractional for a master at an
    intermediate weight and are meant to."""
    private = type("_P", (), {})()
    private.BlueValues = [[-12, 0.5], [0, -0.25], [486, 2.05]]
    private.StdHW = [67, -10.01, 48.3]
    private.StemSnapH = [67, 85]           # a plain CFF array
    private.StdVW = 85.0                   # a plain CFF scalar
    assert verifylib._private_values(private, "BlueValues") == [-12, 0, 486]
    assert verifylib._private_values(private, "StdHW") == [67]
    assert verifylib._private_values(private, "StemSnapH") == [67, 85]
    assert verifylib._private_values(private, "StdVW") == [85.0]
    assert verifylib._private_values(private, "OtherBlues") == []


def test_check_private_reads_order_and_whole_units(capsys):
    fonts = []

    class _FD:
        def __init__(self, private):
            self.Private = private

    class _Top:
        def __init__(self, fds):
            self.FDArray = fds

    def font_with(**private):
        p = type("_P", (), {})()
        for key, value in private.items():
            setattr(p, key, value)
        top = _Top([_FD(p)])
        cff = type("_C", (), {"fontNames": ["T"],
                              "__getitem__": lambda self, n: top})()
        table = type("_T", (), {"cff": cff})()
        fonts.append(table)
        return {"CFF ": table}

    ok = font_with(BlueValues=[-12, 0, 486, 490], StdHW=67)
    check = verifylib.Checker()
    verifylib.check_private(ok, check)
    assert not check.failed

    check = verifylib.Checker()
    verifylib.check_private(font_with(BlueValues=[-12, 0, 490, 486]), check)
    assert check.failed                    # a pair the wrong way round

    check = verifylib.Checker()
    verifylib.check_private(font_with(BlueValues=[-12, 0, 486]), check)
    assert check.failed                    # an odd number of edges

    check = verifylib.Checker()
    verifylib.check_private(font_with(BlueValues=[-12, 0], StdHW=67.34), check)
    assert check.failed                    # a fractional stem width

    check = verifylib.Checker()
    verifylib.check_private(font_with(BlueValues=[-12, 0, 486, 733.9999999]),
                            check)
    assert check.failed                    # the blues eight faces shipped


# --- check_gdi_family_name ---------------------------------------------------

class _Name:
    def __init__(self, family):
        self.family = family

    def getDebugName(self, nid):
        return self.family if nid == 1 else None


def test_check_gdi_family_name_bounds_nameid_1():
    at_limit = "G" * verifylib.LFFACENAME_MAX
    for family, want in ((at_limit, True), (at_limit + "G", False),
                         ("Gengou JP Term NFM SemiBold", True),
                         ("Gengou JP Term Nerd Font Mono SemiBold", False),
                         (None, True)):                      # absent reads as empty
        check = verifylib.Checker()
        verifylib.check_gdi_family_name({"name": _Name(family)}, check)
        assert (not check.failed) is want, family


# --- check_anchor_placement ---------------------------------------------------

def _anchor_font(anchors, heights=None, advance=600, cmap_extra=(), width=100):
    """A CFF font whose glyphs are boxes of the given width and heights,
    carrying one MarkBasePos with the given {glyph: (x, y)} anchors."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.ttLib.tables import otTables
    heights = heights or {}
    order = [".notdef", "mark", *anchors]
    charstrings = {}
    for g in order:
        pen = T2CharStringPen(0, None)
        pen.moveTo((0, 0))
        pen.lineTo((width, 0))
        pen.lineTo((width, heights.get(g, 500)))
        pen.closePath()
        charstrings[g] = pen.getCharString()
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x0301: "mark",
                          **{0x41 + i: g for i, g in enumerate(anchors)},
                          **dict(cmap_extra)})
    fb.setupCFF("T", {}, charstrings, {})
    fb.setupHorizontalMetrics({".notdef": (0, 0),
                               **{g: (advance, 0) for g in order[1:]}})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "T", "styleName": "R"})
    fb.setupOS2()
    fb.setupPost()
    font = fb.font

    from test_build import (
        FakeFeature,
        FakeFeatureList,
        FakeFeatureRecord,
        _FakeLookupList,
    )
    sub = otTables.MarkBasePos()
    sub.Format, sub.ClassCount = 1, 1
    sub.MarkCoverage = otTables.MarkCoverage()
    sub.MarkCoverage.glyphs = ["mark"]
    rec = otTables.MarkRecord()
    rec.Class = 0
    rec.MarkAnchor = otTables.Anchor()
    rec.MarkAnchor.Format = 1
    rec.MarkAnchor.XCoordinate = rec.MarkAnchor.YCoordinate = 0
    sub.MarkArray = otTables.MarkArray()
    sub.MarkArray.MarkRecord = [rec]
    sub.MarkArray.MarkCount = 1
    sub.BaseCoverage = otTables.BaseCoverage()
    sub.BaseCoverage.glyphs = list(anchors)
    sub.BaseArray = otTables.BaseArray()
    sub.BaseArray.BaseRecord = []
    for g, (x, y) in anchors.items():
        a = otTables.Anchor()
        a.Format, a.XCoordinate, a.YCoordinate = 1, x, y
        br = otTables.BaseRecord()
        br.BaseAnchor = [a]
        sub.BaseArray.BaseRecord.append(br)
    sub.BaseArray.BaseCount = len(anchors)
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag = 4, 0
    lk.SubTable, lk.SubTableCount = [sub], 1

    table = otTables.GPOS()
    table.LookupList = _FakeLookupList([lk])
    table.FeatureList = FakeFeatureList(
        [FakeFeatureRecord("mark", FakeFeature([0]))])

    class _Wrap:
        def __init__(self, tb): self.table = tb
    font["GPOS"] = _Wrap(table)
    return font


def _placement(font):
    out = []
    verifylib.check_anchor_placement(
        font, lambda ok, msg: None if ok else out.append(msg), font.getGlyphSet())
    return out


def _ruled(n=20, **over):
    """n bases 20 above their own ink top, centred -- the rule the real
    top-mark lookup follows."""
    heights = {f"b{i}": 400 + 20 * i for i in range(n)}
    anchors = {g: (50, h + 20) for g, h in heights.items()}
    anchors.update(over)
    return anchors, heights


def test_check_anchor_placement_passes_anchors_on_their_glyph():
    anchors, heights = _ruled()
    assert _placement(_anchor_font(anchors, heights)) == []


def test_check_anchor_placement_catches_a_whole_cell_left():
    """The escape this exists for: every below-mark anchor moved one
    cell, so a cedilla draws inside the PREVIOUS character's cell. The
    probe-set checks shape 27 letters by ten ABOVE-accents and reach one
    of seven lookups, so they saw none of it."""
    anchors, heights = _ruled()
    anchors = {g: (x - 600, y) for g, (x, y) in anchors.items()}
    assert _placement(_anchor_font(anchors, heights))


def test_check_anchor_placement_catches_a_mark_lifted_off_the_letter():
    """There was no upper bound anywhere: an anchor 2,000 units up put
    the accent three cells above its letter and every gate passed."""
    anchors, heights = _ruled()
    anchors = {g: (x, y + 2000) for g, (x, y) in anchors.items()}
    assert _placement(_anchor_font(anchors, heights))


def test_check_anchor_placement_catches_one_glyph_among_many():
    """Not an aggregate: one letter's anchor off its own glyph fails,
    though the other nineteen are right where they belong."""
    anchors, heights = _ruled(b7=(-900, 520))
    assert _placement(_anchor_font(anchors, heights))


def test_check_anchor_placement_leaves_bopomofo_alone():
    """Source Han Sans's tone marks go BESIDE the syllable -- anchor x
    960 on a 1000 cell -- which is a different attachment, and its own."""
    anchors = {f"b{i}": (960, 0) for i in range(20)}
    heights = {g: 800 for g in anchors}
    font = _anchor_font(anchors, heights, advance=1000,
                        cmap_extra={0x3105 + i: g for i, g in enumerate(anchors)})
    # the same anchors on Latin bases are a failure
    assert _placement(_anchor_font(anchors, heights, advance=1000))
    assert _placement(font) == []


def test_check_anchor_placement_catches_an_anchor_just_off_the_ink():
    """The ink bound alone: 250 is past this glyph's ink and its slack
    (0..100, plus a sixth of the cell) while still well inside the
    from-the-centre bound, so only the first clause can see it."""
    anchors, heights = _ruled()
    anchors = {g: (250, y) for g, (_x, y) in anchors.items()}
    assert _placement(_anchor_font(anchors, heights))


def test_check_anchor_placement_catches_an_anchor_far_from_a_wide_glyph():
    """The from-the-centre bound alone. A full-width glyph's slack is
    wide enough to hold an anchor 610 units from its ink centre, which
    is most of a cell away from where the mark belongs."""
    heights = {f"b{i}": 700 + 10 * i for i in range(20)}
    ok = {g: (450, h + 20) for g, h in heights.items()}
    assert _placement(_anchor_font(ok, heights, advance=1000, width=900)) == []
    far = {g: (1060, h + 20) for g, h in heights.items()}
    assert _placement(_anchor_font(far, heights, advance=1000, width=900))
