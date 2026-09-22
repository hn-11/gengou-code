"""Unit tests for scripts/verifylib.py (the pieces shared by the verify /
packaging scripts) that need no font files."""

import sys
from pathlib import Path

from fontTools.misc.psCharStrings import T2CharString

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import verifylib  # noqa: E402


def test_static_faces_skips_variable_fonts_and_sorts(tmp_path):
    for name in ("GengouCode-Regular.otf", "GengouCode-Italic[wght].otf", "GengouCode[wght].otf",
                 "GengouCode-Bold.otf", "GengouCodeTerm-Regular.otf", "Other-Regular.otf"):
        (tmp_path / name).write_bytes(b"")
    got = [p.name for p in verifylib.static_faces(tmp_path, "GengouCode")]
    assert got == ["GengouCode-Bold.otf", "GengouCode-Regular.otf"]


def test_static_faces_empty_dir(tmp_path):
    assert verifylib.static_faces(tmp_path, "GengouCode") == []


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
    """anchors.classify_unicode_marks exists because the donor leaves the
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
                         ("Gengou Code JP Term NF SemiBold", True),
                         ("Gengou Code JP Term Nerd Font Mono SemiBold", False),
                         (None, True)):                      # absent reads as empty
        check = verifylib.Checker()
        verifylib.check_gdi_family_name({"name": _Name(family)}, check)
        assert (not check.failed) is want, family


# --- the mark gates: placement, coverage, attachment ------------------------

def _mark_font(anchors, heights=None, advance=600, cmap_extra=(), width=100,
               mark_anchor=None, classify_mark=True, mark_cp=0x0301, marks=(),
               fea_extra="", mark2=None, langsys="", mark_scope="", mark_tail="",
               mkmk_tail=""):
    """A CFF font whose letters are boxes of the given width and heights,
    with a 'mark' feature compiled by feaLib from {glyph: (x, y)} base
    anchors -- a real GDEF and GPOS, so the shaper can apply it. The
    mark is 'acute' at `mark_cp`, anchored at `mark_anchor` (the ink's
    bottom centre by default); `marks` adds more, all in the one mark
    class; `mark2` gives marks a Mark2 anchor in an mkmk feature;
    `fea_extra` is appended verbatim; `langsys` is written before the
    features, `mark_scope` (script/language statements) at the top of
    the mark feature and `mark_tail` at its end."""
    from conftest import make_cff_font
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    heights = heights or {}
    marks = dict(marks)
    order = [".notdef", "acute", *dict.fromkeys([*marks, *anchors, *heights])]
    charstrings = {}
    for g in order:
        pen = T2CharStringPen(0, None)
        pen.moveTo((0, 0))
        pen.lineTo((width, 0))
        pen.lineTo((width, heights.get(g, 500)))
        pen.closePath()
        charstrings[g] = pen.getCharString()
    font = make_cff_font(order, charstrings,
                         {mark_cp: "acute",
                          **{cp: g for g, cp in marks.items() if cp is not None},
                          **{0x41 + i: g for i, g in enumerate(anchors)},
                          **dict(cmap_extra)},
                         {".notdef": (advance, 0), **{g: (advance, 0) for g in order[1:]}})
    mx, my = mark_anchor or (width // 2, 0)
    classes = "\n".join(f"markClass {g} <anchor {mx} {my}> @TOP;"
                        for g in ["acute", *marks])
    bases = "\n".join(f"    pos base {g} <anchor {x} {y}> mark @TOP;"
                      for g, (x, y) in anchors.items())
    fea = (f"{langsys}\n{classes}\nfeature mark {{\n{mark_scope}\n{bases}\n"
           f"{mark_tail}\n}} mark;\n")
    if mark2:
        stacks = "\n".join(f"    pos mark {g} <anchor {x} {y}> mark @TOP;"
                           for g, (x, y) in mark2.items())
        fea += f"feature mkmk {{\n{stacks}\n{mkmk_tail}\n}} mkmk;\n"
    addOpenTypeFeaturesFromString(font, fea + fea_extra)
    if not classify_mark:
        # feaLib derives GDEF from the markClass, so the "not a mark" case
        # is made afterwards: the accent filed as a base outright, which
        # is what a variant left unclassified becomes once a
        # GlyphClassDef exists (check_mark_class_closure says why)
        font["GDEF"].table.GlyphClassDef.classDefs["acute"] = 1
    return font


def _gate(fn, font, *args):
    out = []

    def check(ok, msg):
        # answers as Checker does: a gate may go on only if a check held
        if not ok:
            out.append(msg)
        return ok
    fn(font, *args, check)
    return out


def _shaper_for(font):
    import io
    buf = io.BytesIO()
    font.save(buf)
    return verifylib.make_shaper(buf.getvalue())


def _placement(font):
    return _gate(lambda f, chk: verifylib.check_anchor_placement(f, chk, f.getGlyphSet()),
                 font)


def _coverage(font):
    return _gate(lambda f, chk: verifylib.check_anchor_coverage(f, chk, f.getGlyphSet()),
                 font)


def _attach(font):
    return _gate(lambda f, chk: verifylib.check_marks_attach(f, _shaper_for(f), chk),
                 font)


def _stack(font):
    return _gate(lambda f, chk: verifylib.check_marks_stack(f, _shaper_for(f), chk),
                 font)


def _all_marks(font):
    return _gate(lambda f, chk: verifylib.check_marks(f, chk, _shaper_for(f), f.getGlyphSet()),
                 font)


def _ruled(n=20, **over):
    """n bases 20 above their own ink top, centred -- the rule the real
    top-mark lookup follows."""
    heights = {f"b{i}": 400 + 20 * i for i in range(n)}
    anchors = {g: (50, h + 20) for g, h in heights.items()}
    anchors.update(over)
    return anchors, heights


# placement ------------------------------------------------------------------

def test_check_anchor_placement_passes_anchors_on_their_glyph():
    anchors, heights = _ruled()
    assert _placement(_mark_font(anchors, heights)) == []


def test_check_anchor_placement_catches_a_whole_cell_left():
    """The escape this exists for: every below-mark anchor moved one
    cell, so a cedilla draws inside the PREVIOUS character's cell. The
    probe-set checks it replaced shaped 27 letters by ten ABOVE-accents
    and reached one of seven lookups, so they saw none of it."""
    anchors, heights = _ruled()
    anchors = {g: (x - 600, y) for g, (x, y) in anchors.items()}
    assert _placement(_mark_font(anchors, heights))


def test_check_anchor_placement_catches_a_mark_lifted_off_the_letter():
    """There was no upper bound anywhere: an anchor 2,000 units up put
    the accent three cells above its letter and every gate passed."""
    anchors, heights = _ruled()
    anchors = {g: (x, y + 2000) for g, (x, y) in anchors.items()}
    assert _placement(_mark_font(anchors, heights))


def test_check_anchor_placement_catches_one_glyph_among_many():
    anchors, heights = _ruled(b7=(-900, 520))
    assert _placement(_mark_font(anchors, heights))


def test_check_anchor_placement_leaves_bopomofo_alone():
    """Source Han Sans's tone marks go BESIDE the syllable -- anchor x
    960 on a 1000 cell -- which is a different attachment, and its own."""
    anchors = {f"b{i}": (960, 0) for i in range(20)}
    heights = {g: 800 for g in anchors}
    assert _placement(_mark_font(anchors, heights, advance=1000))
    bopo = _mark_font(anchors, heights, advance=1000,
                      cmap_extra={0x3105 + i: g for i, g in enumerate(anchors)})
    assert _placement(bopo) == []


def test_check_anchor_placement_catches_an_anchor_just_off_the_ink():
    """The ink bound alone: 250 is past this glyph's ink and its slack
    (0..100, plus a sixth of the cell) while still well inside the
    from-the-centre bound, so only the first clause can see it."""
    anchors, heights = _ruled()
    anchors = {g: (250, y) for g, (_x, y) in anchors.items()}
    assert _placement(_mark_font(anchors, heights))


def test_check_anchor_placement_catches_an_anchor_far_from_a_wide_glyph():
    """The from-the-centre bound alone, on a full-width glyph whose
    slack is wide enough to hold an anchor 610 from its ink centre."""
    heights = {f"b{i}": 700 + 10 * i for i in range(20)}
    ok = {g: (450, h + 20) for g, h in heights.items()}
    assert _placement(_mark_font(ok, heights, advance=1000, width=900)) == []
    far = {g: (1060, h + 20) for g, h in heights.items()}
    assert _placement(_mark_font(far, heights, advance=1000, width=900))


# coverage -------------------------------------------------------------------

def test_check_anchor_coverage_passes_when_every_letter_is_a_base():
    anchors, heights = _ruled()
    assert _coverage(_mark_font(anchors, heights)) == []


def test_check_anchor_coverage_catches_a_letter_no_lookup_covers():
    """anchor_loose_letters' invariant read back: the state the variable
    fonts shipped in for a round -- 502 anchors against the statics'
    3,313 -- while a 27-letter sample saw nothing. Here one letter of
    twenty-one has no anchor, and it is the one the sample would miss."""
    anchors, heights = _ruled()
    heights["loose"] = 500                 # drawn, cmapped, not a base
    font = _mark_font(anchors, heights, cmap_extra={0x5A: "loose"})
    assert _coverage(font)


def test_check_anchor_coverage_is_asked_by_mark_not_by_lookup():
    """A lookup cut from 833 bases to 15 fell under the rule floor and
    was excused as "the donor's own" (round 7, mutant 12): the fewer
    letters survived, the less was asked. By mark there is no floor
    -- the acute must reach every letter whatever lookup carries it."""
    font = _mark_font({"b0": (50, 420)}, {"b0": 400, "loose": 500},
                      cmap_extra={0x5A: "loose"})
    assert _coverage(font)


def test_check_anchor_coverage_excuses_the_donors_sparse_marks_by_name():
    """The horn, the left angle above and the tilde overlay are anchored
    on a handful of letters by design (SPARSE_MARKS)."""
    font = _mark_font({"b0": (50, 420)}, {"b0": 400, "loose": 500},
                      cmap_extra={0x5A: "loose"}, mark_cp=0x031B)
    assert _coverage(font) == []


def test_check_anchor_coverage_asks_for_what_gsub_makes_of_a_letter():
    """The Serbian locl б takes the accent, not б: a substitute no
    lookup covers is a letter no lookup covers."""
    anchors, heights = _ruled()
    heights["b0.srb"] = 500
    font = _mark_font(anchors, heights,
                      fea_extra="feature locl { sub b0 by b0.srb; } locl;\n")
    assert _coverage(font)
    anchors["b0.srb"] = (50, 520)
    font = _mark_font(anchors, heights,
                      fea_extra="feature locl { sub b0 by b0.srb; } locl;\n")
    assert _coverage(font) == []


# attachment -----------------------------------------------------------------

def test_check_marks_attach_passes_when_the_shaper_lays_each_mark_on_its_anchor():
    anchors, heights = _ruled()
    assert _attach(_mark_font(anchors, heights)) == []


def test_check_marks_attach_is_an_equality_not_a_threshold():
    """Every position is fully determined by the two anchors, so the
    check compares the shaped output against the tables exactly. A
    shaper whose font disagrees with the tables by ONE unit fails."""
    import io
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights)
    nudged = _mark_font(anchors, heights)
    sub = nudged["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    sub.BaseArray.BaseRecord[3].BaseAnchor[0].XCoordinate += 1
    buf = io.BytesIO()
    nudged.save(buf)
    out = []
    verifylib.check_marks_attach(font, verifylib.make_shaper(buf.getvalue()),
                                 lambda ok, msg: None if ok else out.append(msg))
    assert out and "b3" in out[0]


def test_check_marks_attach_catches_a_mark_gdef_does_not_call_a_mark():
    """A right anchor that is never applied. Without the GDEF class the
    shaper treats the accent as a base, so it advances a full cell
    instead of attaching -- the anchors are all in place and every
    structural check passes; only shaping shows it."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, classify_mark=False)
    assert _placement(font) == []
    assert _attach(font)


def test_check_marks_attach_fails_when_nothing_attaches_at_all():
    """A face where every pair is skipped is not a pass."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights)
    # drop the feature: the lookup exists, nothing reaches it
    font["GPOS"].table.FeatureList.FeatureRecord = []
    font["GPOS"].table.FeatureList.FeatureCount = 0
    assert _attach(font)


def test_check_marks_attach_catches_a_vertical_disagreement_alone():
    """Each coordinate of the equality on its own: here x and the
    advance agree and only y is off, by one unit."""
    import io
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights)
    nudged = _mark_font(anchors, heights)
    sub = nudged["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    sub.BaseArray.BaseRecord[5].BaseAnchor[0].YCoordinate += 1
    buf = io.BytesIO()
    nudged.save(buf)
    out = []
    verifylib.check_marks_attach(font, verifylib.make_shaper(buf.getvalue()),
                                 lambda ok, msg: None if ok else out.append(msg))
    assert out and "b5" in out[0]


def test_check_anchor_coverage_asks_of_what_takes_an_accent():
    """A drawn, cmapped glyph outside anchors.accent_bases (an arrow)
    takes no accent and its absence is not a gap; the middle dot
    (U+00B7) is Latin-1 punctuation, which takes one since round 10,
    and unanchored it is a gap."""
    anchors, heights = _ruled()
    heights["arrow"] = 500
    assert _coverage(_mark_font(anchors, heights, cmap_extra={0x2190: "arrow"})) == []
    heights["periodcentered"] = 500
    short = _coverage(_mark_font(anchors, heights, cmap_extra={0xB7: "periodcentered"}))
    assert short and "periodcentered" in short[0]


def test_ink_spill_allows_the_widest_lean_and_not_a_unit_more():
    """The bound is _LEAN either side of the advance: the widest italic
    lean is 224, and half a cell let a ligature drawn 300 to the right
    pass (round 9, mutant L4)."""
    cmap = {0x61: "a"}
    lean = verifylib._LEAN
    assert lean == 230
    ok = {"a": (-lean, 0, 600 + lean, 700)}
    assert verifylib.ink_spill(ok, lambda g: 600, cmap, 600) == []
    assert verifylib.ink_spill({"a": (-lean - 1, 0, 500, 700)}, lambda g: 600, cmap, 600) \
        == [("a", 600, -lean - 1, 500)]
    assert verifylib.ink_spill({"a": (0, 0, 601 + lean, 700)}, lambda g: 600, cmap, 600) \
        == [("a", 600, 0, 601 + lean)]


def test_ink_spill_gives_a_double_diacritic_a_whole_cell_and_only_it():
    """U+035F ties two characters: its ink hangs a cell over the one
    before by design (measured from -300 at Bold Italic, right on the
    half-cell bound). A letter drawn the same way is still a spill."""
    cmap = {0x35F: "dblmacronbelow", 0x61: "a"}
    box = {"dblmacronbelow": (-600, -200, 720, -100)}
    assert verifylib.ink_spill(box, lambda g: 600, cmap, 600) == []
    box = {"dblmacronbelow": (-601, -200, 720, -100)}
    assert verifylib.ink_spill(box, lambda g: 600, cmap, 600) \
        == [("dblmacronbelow", 600, -601, 720)]
    assert verifylib.ink_spill({"a": (-600, 0, 500, 700)}, lambda g: 600, cmap, 600) \
        == [("a", 600, -600, 500)]


def test_ink_spill_rounds_as_the_static_faces_store_the_outline():
    """A variable font blends to -300.135 where the static rounds to
    -300: the same outline, judged the same way."""
    assert verifylib.ink_spill({"a": (-230.135, 0, 500, 700)},
                               lambda g: 600, {0x61: "a"}, 600) == []


def test_ink_spill_skips_a_zero_advance_glyph():
    """A combining mark has no advance to be inside of."""
    assert verifylib.ink_spill({"acute": (-400, 500, -100, 700)},
                               lambda g: 0, {0x301: "acute"}, 600) == []


# the round-7 gates ----------------------------------------------------------

def test_check_anchor_placement_catches_a_null_base_anchor():
    """A NULL anchor in a one-class lookup places nothing: the mark lands
    a cell right (round 7, mutant 5), and the pair looked "skipped"."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights,
                      fea_extra="feature mark { pos base b0 <anchor NULL> mark @TOP; } mark;\n")
    assert _placement(font)


def test_check_anchor_placement_catches_a_uniform_drift_through_the_rule():
    """Every anchor 130 down still sits inside each anchor's own band;
    the fitted rule's offset is what moves (round 7, mutant 4)."""
    anchors, heights = _ruled()
    low = {g: (x, y - 150) for g, (x, y) in anchors.items()}
    assert _placement(_mark_font(low, heights))


def test_check_anchor_placement_catches_a_mark_anchor_off_the_marks_ink():
    """The attach gate derives its expectation from the mark anchor, so
    a mark anchor 350 right of its ink moved every accent 350 right and
    passed it (round 7, mutant 2)."""
    anchors, heights = _ruled()
    assert _placement(_mark_font(anchors, heights, mark_anchor=(400, 0)))


def test_check_anchor_placement_catches_a_second_mark_stacking_on_itself():
    """A Mark2 anchor at the Mark1 height draws x̀́ as one accent on the
    other -- the italic donor's grave, acute, breve and ring."""
    anchors, heights = _ruled()
    stacked = _mark_font(anchors, heights, marks={"grave": 0x0300},
                         mark2={"grave": (50, 200)})
    assert _placement(stacked) == []
    flat = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, 0)})
    assert _placement(flat)


def test_check_marks_attach_holds_a_substituted_mark_to_its_own_anchor():
    """ccmp swaps the acute for its .cap form after a capital; the pair
    then attaches through the substitute's anchor, or not at all
    (round 7, mutants 10 and 6)."""
    anchors, heights = _ruled()
    heights["acutecap"] = 500
    swapped = _mark_font(anchors, heights, marks={"acutecap": None},
                         fea_extra="feature ccmp { sub acute by acutecap; } ccmp;\n")
    assert _attach(swapped) == []
    orphan = _mark_font(anchors, heights,
                        fea_extra="feature ccmp { sub acute by acutecap; } ccmp;\n")
    assert _attach(orphan)


def test_check_marks_attach_holds_a_composed_pair_to_the_composed_character():
    """A pair the shaper composes must compose to the cmap's glyph for
    that character (round 7, mutant 9). With Á in the cmap the shaper
    composes A + U+0301 itself; without it, a ccmp ligature that
    composes the pair to some other glyph is the only composition."""
    anchors, heights = _ruled()
    heights["Aacute"] = heights["other"] = 500
    right = _mark_font(anchors, heights, cmap_extra={0xC1: "Aacute"})
    assert _attach(right) == []
    wrong = _mark_font(anchors, heights,
                       fea_extra="feature ccmp { sub b0 acute by other; } ccmp;\n")
    assert _attach(wrong)


def test_check_marks_stack_is_an_equality_on_the_second_mark():
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, 500), "acute": (50, 500)})   # the mark's own ink top
    assert _stack(font) == []


def test_check_marks_stack_wants_a_mark2_anchor_on_every_common_accent():
    """A mark removed from Mark2Coverage is a mark nothing can stack on
    (round 7, mutant 8)."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"acute": (50, 200)})
    assert any("no Mark2 anchor" in m for m in _stack(font))


def test_check_mark_reachability_wants_mark_lookups_under_a_mark_feature():
    """A lookup under GPOS 'dist' still runs, outside every gate that
    walked the 'mark' feature (round 7, mutant 13)."""
    anchors, heights = _ruled()
    stray = _mark_font(anchors, heights,
                       fea_extra="feature dist { pos base b1 <anchor 50 440> mark @TOP; } dist;\n")
    assert _gate(verifylib.check_mark_reachability, stray)
    assert _gate(verifylib.check_mark_reachability, _mark_font(anchors, heights)) == []


def test_check_langsys_parity_wants_every_language_to_reach_the_marks():
    """cyrl/SRB without 'mark' loses every accent under lang=sr alone
    (round 7, mutant 7)."""
    anchors, heights = _ruled()
    systems = ("languagesystem DFLT dflt; languagesystem latn dflt; "
               "languagesystem latn SRB;")
    # SRB has a GPOS feature of its own, so its LangSys exists there --
    # without mark (a LangSys only GSUB knows falls back to dflt in GPOS)
    short = _mark_font(anchors, heights, langsys=systems,
                       mark_tail="script latn; language SRB exclude_dflt;",
                       fea_extra="feature dist { script latn; language SRB exclude_dflt; "
                                 "pos b0 <0 10 0 0>; } dist;\n")
    assert _gate(verifylib.check_langsys_parity, short)
    whole = _mark_font(anchors, heights, langsys=systems,
                       fea_extra="feature dist { script latn; language SRB exclude_dflt; "
                                 "pos b0 <0 10 0 0>; } dist;\n")
    assert _gate(verifylib.check_langsys_parity, whole) == []


def test_check_mark_features_wants_the_gdef_classes_gpos_filters_on():
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, 200)},
                      fea_extra="feature ccmp { pos b1 <0 10 0 0>; } ccmp;\n")
    assert _gate(verifylib.check_mark_features, font) == []
    font["GPOS"].table.LookupList.Lookup[0].LookupFlag = 2 << 8
    assert _gate(verifylib.check_mark_features, font)


def test_check_marks_runs_every_gate_and_passes_a_sound_face():
    anchors, heights = _ruled()
    heights["acutecap"] = 500
    # every capital raises the acute; b5 is also 'b', where it seats
    font = _mark_font(anchors, heights, marks={"grave": 0x0300, "acutecap": None},
                      mark2={"grave": (50, 500), "acute": (50, 500)},
                      cmap_extra={0x62: "b5"},
                      fea_extra="feature ccmp { pos b1 <0 10 0 0>; } ccmp;\n"
                                "feature ccmp { sub [%s] acute' by acutecap; } ccmp;\n"
                                % " ".join(g for g in anchors if g != "b5"))
    for table in font["cmap"].tables:
        table.cmap.pop(0x46, None)        # b5 is 'b' only, not also 'F'
    assert _all_marks(font) == []


def test_check_anchor_placement_holds_a_mark_anchor_to_the_edge_its_lookup_attaches_by():
    """A mark given another mark's anchor sits on its own ink still and
    attaches exactly through it -- the italic caron with the .cap
    form's, 169 up, drew through b's ascender and passed every other
    gate but the JP clearance probe. Against the ink bottom an above-
    mark's anchor sits within the donor's few dozen units."""
    anchors, heights = _ruled()
    assert _placement(_mark_font(anchors, heights)) == []
    font = _mark_font(anchors, heights)
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    sub.MarkArray.MarkRecord[0].MarkAnchor.YCoordinate += 169
    assert _placement(font)


def test_check_marks_clear_catches_an_accent_through_an_ascender():
    """The mark's ink has to begin above the letter's."""
    anchors, heights = _ruled()
    heights["tall"] = 700
    anchors["tall"] = (50, 720)
    font = _mark_font(anchors, heights, cmap_extra={0x62: "tall"})
    clear = _gate(lambda f, chk: verifylib.check_marks_clear(f, _shaper_for(f), chk,
                                                              f.getGlyphSet()), font)
    assert clear == []
    anchors["tall"] = (50, 520)
    font = _mark_font(anchors, heights, cmap_extra={0x62: "tall"})
    through = _gate(lambda f, chk: verifylib.check_marks_clear(f, _shaper_for(f), chk,
                                                                f.getGlyphSet()), font)
    assert through and "b́" in through[0]


# the face checks the three verifiers share -------------------------------

def _metadata_font(style="Regular"):
    """A TTF with the metadata a Latin face declares: fixed pitch,
    PANOSE, typo == hhea with USE_TYPO_METRICS, win metrics over the
    box, a version stamp of 6.0.0."""
    from conftest import make_font
    font = make_font([".notdef", "a", "b"], {0x61: "a", 0x62: "b"},
                     {".notdef": 600, "a": 600, "b": 600}, style=style)
    font["post"].isFixedPitch = 1
    os2 = font["OS/2"]
    os2.panose.bProportion = 9
    os2.panose.bWeight = verifylib.build.panose_weight(os2.usWeightClass)
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = 800, -200, 0
    os2.fsSelection |= 0x80
    os2.usWinAscent, os2.usWinDescent = 800, 200
    font["head"].yMax, font["head"].yMin = 700, -100
    font["head"].fontRevision = 6.0
    font["name"].setName("Version 6.0.0", 5, 3, 1, 0x409)
    font["name"].setName("6.0.0;TEST;Test-Regular", 3, 3, 1, 0x409)
    return font


def test_is_italic_reads_the_name_the_angle_and_the_style_bits():
    assert not verifylib.is_italic(_metadata_font())
    assert verifylib.is_italic(_metadata_font(style="Italic"))
    slanted = _metadata_font()
    slanted["post"].italicAngle = -11
    assert verifylib.is_italic(slanted)


def test_check_name_ids_wants_each_one_set():
    font = _metadata_font()
    assert _gate(lambda f, chk: verifylib.check_name_ids(f, chk, (1, 2, 5)), font) == []
    assert _gate(lambda f, chk: verifylib.check_name_ids(f, chk, (1, 13)), font) \
        == ["nameID 13 is set"]


def test_check_version_stamp_holds_head_and_the_names_to_the_env(monkeypatch, capsys):
    monkeypatch.setenv("GENGOU_VERSION", "6.0.0")
    stamp = lambda unique: (lambda f, chk: verifylib.check_version_stamp(f, chk, unique))  # noqa: E731
    font = _metadata_font()
    assert _gate(stamp(False), font) == []
    assert _gate(stamp(True), font) == []
    font["name"].setName("Version 5.0.0", 5, 3, 1, 0x409)
    assert _gate(stamp(False), font)
    font = _metadata_font()
    font["name"].removeNames(nameID=3)
    assert _gate(stamp(False), font) == []
    assert _gate(stamp(True), font)
    monkeypatch.delenv("GENGOU_VERSION")
    assert _gate(stamp(True), font) == []
    assert "skip" in capsys.readouterr().out


def _named_font(family, ps, style="Regular"):
    font = _metadata_font(style=style)
    font["name"].setName(family, 16, 3, 1, 0x409)
    font["name"].setName(f"{ps}-{style}", 6, 3, 1, 0x409)
    return font


def test_check_family_names_strips_the_nerd_font_mark_and_wants_nf():
    gate = lambda fam, ps: (  # noqa: E731
        lambda f, chk: verifylib.check_family_names(f, chk, fam, ps))
    assert _gate(gate("Gengou Code", "GengouCode"), _named_font("Gengou Code", "GengouCode")) == []
    patched = _named_font("Gengou Code NF", "GengouCodeNF")
    assert _gate(gate("Gengou Code", "GengouCode"), patched) == []
    # a patched face that kept the plain PostScript name
    unmarked = _named_font("Gengou Code NF", "GengouCode")
    assert _gate(gate("Gengou Code", "GengouCode"), unmarked) == [
        "PostScript name 'GengouCode-Regular' (want GengouCodeNF-...)"]
    assert _gate(gate("Gengou Code JP", "GengouCodeJP"), _named_font("Gengou Code", "GengouCode")) == [
        "family name 'Gengou Code' (want 'Gengou Code JP')",
        "PostScript name 'GengouCode-Regular' (want GengouCodeJP-...)"]


def test_check_family_names_says_whether_the_face_is_patched():
    ask = lambda font: verifylib.check_family_names(  # noqa: E731
        font, lambda ok, msg: ok, "Gengou Code", "GengouCode")
    assert ask(_named_font("Gengou Code NF", "GengouCodeNF")) is True
    assert ask(_named_font("Gengou Code", "GengouCode")) is False



def test_the_nerd_font_mark_is_the_one_nerdpatch_writes():
    # the icon gates run only on a face whose name carries this mark:
    # when nerdpatch's changed and the JP driver's spelling did not, the
    # gates skipped every JP Nerd Fonts face without a word
    import nerdpatch
    assert verifylib.NERD_FONT_MARK == nerdpatch.NF_MARKER
    assert nerdpatch.nf_name("Gengou Code JP Term").endswith(verifylib.NERD_FONT_MARK)

def test_check_weight_class_holds_the_number_to_the_name():
    font = _metadata_font()
    font["OS/2"].usWeightClass = verifylib.build.WEIGHT_CLASS["Regular"]
    gate = lambda sub: lambda f, chk: verifylib.check_weight_class(f, chk, sub)  # noqa: E731
    assert _gate(gate("Regular"), font) == []
    # the italic Regular is plain "Italic" (weight_name)
    assert _gate(gate("Italic"), font) == []
    font["OS/2"].usWeightClass = 700
    assert _gate(gate("Regular"), font) == [
        f"OS/2 usWeightClass 700 (want {verifylib.build.WEIGHT_CLASS['Regular']} for Regular)"]
    # a subfamily that names no weight is one FAIL, not two
    assert _gate(gate("Hairline"), font) == [
        "subfamily 'Hairline' names a weight ('Hairline')"]


def test_check_weight_class_returns_the_weight_only_when_named():
    font = _metadata_font()
    font["OS/2"].usWeightClass = verifylib.build.WEIGHT_CLASS["Bold"]
    ask = lambda sub: verifylib.check_weight_class(font, lambda ok, msg: ok, sub)  # noqa: E731
    assert ask("Bold Italic") == "Bold"
    assert ask("Hairline") is None


def test_check_charstring_metrics_reports_each_list():
    font = _metadata_font()
    gate = lambda w, b: lambda f, chk: verifylib.check_charstring_metrics(f, chk, w, b)  # noqa: E731
    assert _gate(gate([], []), font) == []
    got = _gate(gate([("a", 500, 600)], [("b", 12, 0)]), font)
    assert got == ["CFF charstring widths agree with hmtx (3 glyphs, 1 off: [('a', 500, 600)])",
                   "hmtx bearings are the outlines' xMin (1 off: [('b', 12, 0)])"]


def test_check_ink_inside_fails_a_glyph_drawn_into_the_next_cell():
    cmap = {0x61: "a"}
    hmtx = {"a": (600, 0)}

    def gate(box):
        return _gate(lambda f, chk: verifylib.check_ink_inside(
            chk, {"a": box}, hmtx, cmap, 600), None)
    assert gate((50, 0, 550, 500)) == []
    assert len(gate((650, 0, 1150, 500))) == 1


def test_check_monospace_metadata_asks_all_four():
    assert _gate(verifylib.check_monospace_metadata, _metadata_font()) == []
    for spoil in (lambda f: setattr(f["post"], "isFixedPitch", 0),
                  lambda f: setattr(f["OS/2"].panose, "bWeight", 11),
                  lambda f: setattr(f["OS/2"], "sTypoAscender", 799),
                  lambda f: setattr(f["OS/2"], "usWinAscent", 699)):
        font = _metadata_font()
        spoil(font)
        assert len(_gate(verifylib.check_monospace_metadata, font)) == 1


def test_check_grid_names_the_advances_off_the_cell():
    metrics = {"a": (600, 0), "b": (1200, 0), "m": (0, 0)}
    assert _gate(lambda f, chk: verifylib.check_grid(chk, metrics, 600), None) == []
    metrics["c"] = (601, 0)
    assert "601" in _gate(lambda f, chk: verifylib.check_grid(chk, metrics, 600), None)[0]


def test_check_widths_by_class_asks_one_cell_of_notdef_and_the_ambiguous_symbols():
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, cmap_extra={0x2190: "b4"}, width=500)
    assert _cells(font) == []
    font["hmtx"].metrics["b4"] = (1200, 0)      # ← is East Asian Ambiguous, a cell by policy
    assert "'←': ('A', 1200)" in _cells(font)[0]
    font["hmtx"].metrics["b4"] = (600, 0)
    font["hmtx"].metrics[".notdef"] = (1200, 0)
    assert "'.notdef': ('policy', 1200)" in _cells(font)[0]


def test_check_latin_repertoire_wants_the_size_and_no_cjk():
    latin = {cp: "a" for cp in range(0x20, 0x20 + 800)}
    assert _gate(lambda f, chk: verifylib.check_latin_repertoire(chk, latin), None) == []
    assert _gate(lambda f, chk: verifylib.check_latin_repertoire(chk, {**latin, 0x4E00: "a"}), None) \
        == ["no CJK / full-width codepoints"]
    assert _gate(lambda f, chk: verifylib.check_latin_repertoire(chk, dict(list(latin.items())[:10])), None)


# round 8: the model follows the shaper's lookup order and mark filters ---

def test_mark_model_takes_the_last_lookup_covering_the_pair():
    """A shaper applies the lookups in order and each attachment
    overwrites the one before: two mark lookups both covering (b0,
    acute) with base anchors 20 and 120 above the letter place the
    accent by the second. The model once took the first and failed a
    correct face."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights,
                      fea_extra="feature mark { pos base b0 <anchor 50 520> mark @TOP; } mark;\n")
    assert _attach(font) == []
    assert verifylib._MarkModel(font).on_base("b0", "acute") == (50 - 50 - 600, 520, 0)


def test_mark_model_skips_the_marks_a_lookups_class_filter_skips():
    """A mkmk lookup flagged MarkAttachmentType looks back past marks of
    other classes: b0 + grave (class 2) + acute (class 1) leaves the
    acute on the letter, and the model says so."""
    anchors, heights = _ruled()
    heights["grave"] = 500
    # encoded as an overlay, which no gate asks to be stackable
    font = _mark_font(anchors, heights, cmap_extra={0x335: "grave"},
                      fea_extra="markClass grave <anchor 50 0> @GR;\n"
                                "feature mark { pos base b0 <anchor 50 420> mark @GR; } mark;\n"
                                "feature mkmk { lookupflag MarkAttachmentType @TOP; "
                                "pos mark acute <anchor 50 500> mark @TOP; } mkmk;\n")
    assert _stack(font) == []
    model = verifylib._MarkModel(font)
    assert model.run(["b0", "grave", "acute"])[1] == model.on_base("b0", "acute")
    assert model.run(["b0", "acute", "acute"])[1] == (
        model.on_base("b0", "acute")[0], model.on_base("b0", "acute")[1] + 500, 0)


def test_check_mark_reachability_reports_a_lookup_that_never_sees_its_marks():
    """IgnoreMarks on a mark lookup, or a class filter its own marks are
    not in, is a lookup that never applies."""
    anchors, heights = _ruled()
    deaf = _mark_font(anchors, heights, mark_scope="lookupflag IgnoreMarks;")
    assert any("admits its own marks" in m for m in _gate(verifylib.check_mark_reachability, deaf))
    heights["grave"] = 500
    filtered = _mark_font(anchors, heights, cmap_extra={0x300: "grave"},
                          fea_extra="markClass grave <anchor 50 0> @GR;\n"
                                    "feature mark { pos base b0 <anchor 50 420> mark @GR; } mark;\n"
                                    "feature mkmk { lookupflag MarkAttachmentType @TOP; "
                                    "pos mark grave <anchor 50 200> mark @TOP; } mkmk;\n")
    assert any("filters out" in m for m in _gate(verifylib.check_mark_reachability, filtered))


def test_check_anchor_placement_does_not_ask_stacking_of_a_glyph_nothing_reaches():
    """A Mark2 glyph no cmap or GSUB produces cannot be shaped; its
    collapsed anchor is not a finding (the italic donor's uni0306.c)."""
    anchors, heights = _ruled()
    heights["grave2"] = 500
    font = _mark_font(anchors, heights, marks={"grave2": None},
                      mark2={"grave2": (50, 0), "acute": (50, 200)})
    assert _placement(font) == []


# round 8: an expectation independent of the anchors -------------------

def test_check_marks_seat_catches_one_letters_anchor_off_inside_the_bands():
    """An anchor wrong on ONE letter by less than a placement band
    passed every gate: the rule is a median, attach is an equality
    against the same anchor. The seat gate measures the mark's ink
    against the letter's."""
    anchors, heights = _ruled()
    seated = _mark_font(anchors, heights)
    assert _gate(lambda f, chk: verifylib.check_marks_seat(f, _shaper_for(f), chk,
                                                          f.getGlyphSet()), seated) == []
    anchors["b3"] = (50, heights["b3"] - 300)      # into the letter, within 350
    font = _mark_font(anchors, heights)
    assert _placement(font) == []
    assert _attach(font) == []
    off = _gate(lambda f, chk: verifylib.check_marks_seat(f, _shaper_for(f), chk,
                                                         f.getGlyphSet()), font)
    assert off and "b3" in off[0]


def test_check_marks_seat_holds_the_lookups_median():
    """Every mark's outline moved 200 right with its anchor left behind
    stays inside each pair's band and moves only the median."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, width=100)
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    pen = T2CharStringPen(0, None)
    pen.moveTo((200, 0))
    pen.lineTo((300, 0))
    pen.lineTo((300, 500))
    pen.closePath()
    td = font["CFF "].cff.topDictIndex[0]
    td.CharStrings["acute"] = pen.getCharString(private=td.Private)
    off = _gate(lambda f, chk: verifylib.check_marks_seat(f, _shaper_for(f), chk,
                                                         f.getGlyphSet()), font)
    assert off and "median" in off[0]


def test_check_cap_forms_wants_the_raised_form_after_every_capital():
    """The fixture's letters are A..T (b0..b19): after B the acute must
    not be the plain acute; a font swapping after A only leaves the
    rest low."""
    anchors, heights = _ruled()
    heights["acutecap"] = 500
    swapped = _mark_font(anchors, heights, marks={"acutecap": None},
                         fea_extra="feature ccmp { sub [%s] acute' by acutecap; } ccmp;\n"
                                   % " ".join(anchors))
    assert _gate(lambda f, chk: verifylib.check_cap_forms(f, _shaper_for(f), chk), swapped) == []
    partial = _mark_font(anchors, heights, marks={"acutecap": None},
                         fea_extra="feature ccmp { sub [b0 b1] acute' by acutecap; } ccmp;\n")
    low = _gate(lambda f, chk: verifylib.check_cap_forms(f, _shaper_for(f), chk), partial)
    assert low and "D" in low[0].split("low: ")[1]


def test_check_tie_bars_wants_the_tie_across_the_join():
    anchors, heights = _ruled()
    heights["tie"] = 100
    font = _mark_font(anchors, heights, cmap_extra={0x61: "b0", 0x62: "b1", 0x361: "tie"},
                      width=100)
    # the tie is a 100-wide box at x 0..100 with a 600 advance zeroed by
    # GDEF: it draws at 600..700 after 'a', inside b's cell -- not across
    off = _gate(lambda f, chk: verifylib.check_tie_bars(f, _shaper_for(f), chk,
                                                       f.getGlyphSet()), font)
    assert off and "a͡b" in off[0]


def test_check_letter_glyphs_wants_each_ascii_letter_drawn_and_its_own():
    font = _metadata_font()
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    for g in ("a", "b", ".notdef"):
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.closePath()
        font["glyf"][g] = pen.glyph()
    font["cmap"].tables[0].cmap = {0x61: "a", 0x62: "b"}
    out = _gate(lambda f, chk: verifylib.check_letter_glyphs(f, chk, f.getGlyphSet()), font)
    assert len(out) == 1 and "blank" in out[0]       # c..z, digits, capitals absent
    font["cmap"].tables[0].cmap = {0x61: "a", 0x62: "a"}
    out = _gate(lambda f, chk: verifylib.check_letter_glyphs(f, chk, f.getGlyphSet()), font)
    assert "shared: [('b', 'a')]" in out[0]


# the band constants, pinned one unit either side ------------------------

def _placement_with(font, **over):
    saved = {k: getattr(verifylib, k) for k in over}
    try:
        for k, v in over.items():
            setattr(verifylib, k, v)
        return _placement(font)
    finally:
        for k, v in saved.items():
            setattr(verifylib, k, v)


def test_anchor_y_into_ink_is_the_bound():
    anchors, heights = _ruled()
    anchors["b3"] = (50, heights["b3"] - verifylib._ANCHOR_Y_INTO_INK)
    assert _placement(_mark_font(anchors, heights)) == []
    anchors["b3"] = (50, heights["b3"] - verifylib._ANCHOR_Y_INTO_INK - 1)
    assert _placement(_mark_font(anchors, heights))


def test_anchor_y_past_edge_is_the_bound():
    anchors, heights = _ruled()
    anchors["b3"] = (50, heights["b3"] + verifylib._ANCHOR_Y_PAST_EDGE)
    assert _placement(_mark_font(anchors, heights)) == []
    anchors["b3"] = (50, heights["b3"] + verifylib._ANCHOR_Y_PAST_EDGE + 1)
    assert _placement(_mark_font(anchors, heights))


def test_anchor_x_slack_is_the_bound():
    anchors, heights = _ruled()
    slack = round(verifylib._ANCHOR_X_SLACK * 600)
    anchors["b3"] = (100 + slack, heights["b3"] + 20)
    assert _placement(_mark_font(anchors, heights)) == []
    anchors["b3"] = (100 + slack + 1, heights["b3"] + 20)
    assert _placement(_mark_font(anchors, heights))


def test_anchor_x_from_centre_is_the_bound():
    """On a wide glyph the slack is loose and the centre bound is what
    holds."""
    heights = {f"b{i}": 700 + 10 * i for i in range(20)}
    spread = round(verifylib._ANCHOR_X_FROM_CENTRE * 1000)
    ok = {g: (500, h + 20) for g, h in heights.items()}
    ok["b3"] = (500 + spread, heights["b3"] + 20)       # one, so the rule stays centred
    assert _placement(_mark_font(ok, heights, advance=1000, width=1000)) == []
    ok["b3"] = (500 + spread + 1, heights["b3"] + 20)
    assert _placement(_mark_font(ok, heights, advance=1000, width=1000))


def test_rule_dy_is_the_bound():
    anchors, heights = _ruled()
    high = {g: (x, y - 20 + verifylib._RULE_DY) for g, (x, y) in anchors.items()}
    assert _placement(_mark_font(high, heights)) == []
    over = {g: (x, y - 20 + verifylib._RULE_DY + 1) for g, (x, y) in anchors.items()}
    assert _placement(_mark_font(over, heights))


def test_mark2_below_ink_is_the_bound():
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, -verifylib._MARK2_BELOW_INK), "acute": (50, 200)})
    assert _placement(font) == []
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, -verifylib._MARK2_BELOW_INK - 1), "acute": (50, 200)})
    assert _placement(font)


def test_letter_and_mark_ranges_reach_their_last_blocks():
    """Latin Extended Additional letters and the combining supplement
    marks are asked for (a range dropped from either passed)."""
    anchors, heights = _ruled()
    heights["loose"] = 500
    font = _mark_font(anchors, heights, cmap_extra={0x1EF8: "loose"})
    assert _coverage(font)
    font = _mark_font(anchors, heights, mark_cp=0x1DC4)
    assert 0x1DC4 in verifylib._latin_marks(font, font.getGlyphSet())


def test_hold_run_reports_an_unanchored_mark():
    """A pair the shaper substitutes into a glyph nothing covers is
    reported as such, not skipped."""
    anchors, heights = _ruled()
    heights["acutecap"] = 500
    orphan = _mark_font(anchors, heights,
                        fea_extra="feature ccmp { sub acute by acutecap; } ccmp;\n")
    off = _attach(orphan)
    assert off and "unanchored" in off[0]


def test_reachability_asks_of_mkmk_lookups_too():
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, 200), "acute": (50, 200)})
    for fr in font["GPOS"].table.FeatureList.FeatureRecord:
        if fr.FeatureTag == "mkmk":
            fr.FeatureTag = "dist"
    assert any("reached from a mark feature" in m
               for m in _gate(verifylib.check_mark_reachability, font))


def test_langsys_parity_asks_of_mkmk_too():
    anchors, heights = _ruled()
    systems = "languagesystem DFLT dflt; languagesystem latn dflt; languagesystem latn SRB;"
    font = _mark_font(anchors, heights, langsys=systems, marks={"grave": 0x0300},
                      mark2={"grave": (50, 200), "acute": (50, 200)},
                      mkmk_tail="script latn; language SRB exclude_dflt;")
    short = _gate(verifylib.check_langsys_parity, font)
    assert short and "mkmk" in short[0]


def test_mark_features_require_ccmp_in_gpos():
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, 200)})
    assert any("GPOS has ccmp" in m for m in _gate(verifylib.check_mark_features, font))


def test_mark_model_reads_the_marks_own_class_anchor():
    """A two-class lookup: the .cap form's class-1 anchor is what the
    shaper reads, and what the model must read (BaseAnchor[0] read
    every mark against the first class)."""
    anchors, heights = _ruled()
    heights["acutecap"] = 500
    fea = ("markClass acutecap <anchor 50 0> @CAP;\n"
           "feature mark { " + "".join(f"pos base {g} <anchor 50 {h + 120}> mark @CAP; "
                                       for g, h in heights.items() if g.startswith("b")) + "} mark;\n")
    font = _mark_font(anchors, heights, marks={"acutecap": None}, fea_extra=fea)
    assert verifylib._MarkModel(font).on_base("b0", "acutecap") == (-600, heights["b0"] + 120, 0)


def test_check_tie_bars_rounds_the_span_to_the_unit():
    """The below tie's left end sits ON the cell edge at Bold in the
    donor's own design, and a variable instance interpolates it 0.14
    units past: the gate reads the span to the unit, as the reported
    numbers are, so the instance and the static agree."""
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    anchors, heights = _ruled()
    heights["tie"] = 100
    font = _mark_font(anchors, heights, cmap_extra={0x61: "b0", 0x62: "b1", 0x361: "tie"},
                      width=100)
    td = font["CFF "].cff.topDictIndex[0]
    for left, ok in ((-600.4, True), (-601, False)):
        pen = T2CharStringPen(0, None, roundTolerance=0)
        pen.moveTo((left, 700))
        pen.lineTo((50, 700))
        pen.lineTo((50, 800))
        pen.closePath()
        td.CharStrings["tie"] = pen.getCharString(private=td.Private)
        off = _gate(lambda f, chk: verifylib.check_tie_bars(f, _shaper_for(f), chk,
                                                           f.getGlyphSet()), font)
        assert (off == []) is ok, (left, off)


def _greek_font(locl, italic=False):
    """B and Beta as bases, the acute, and an unencoded tonos the Greek
    'locl' maps the acute to (or not)."""
    anchors, heights = _ruled(2)
    fea = "feature locl { script grek; sub acute by tonos; } locl;\n" if locl else ""
    font = _mark_font(anchors, heights, marks={"tonos": None},
                      cmap_extra={0x42: "b0", 0x392: "b1"},
                      langsys="languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
                              "languagesystem grek dflt;\n",
                      fea_extra=fea)
    if italic:
        font["post"].italicAngle = -12.0
    return font


def test_check_greek_accents_wants_the_tonos_after_a_greek_capital():
    """Beta + U+0301 must not take the accent B + U+0301 takes, unless
    the face is italic, where that is the listed gap."""
    def run(font):
        return _gate(lambda f, chk: verifylib.check_greek_accents(f, _shaper_for(f), chk), font)
    assert run(_greek_font(locl=True)) == []
    off = run(_greek_font(locl=False))
    assert off and "'Β': 'the Latin accent'" in off[0]
    assert run(_greek_font(locl=False, italic=True)) == []
    # the gap is an allowance, not a requirement: an italic that gives
    # Greek the tonos has closed it, and passes
    assert run(_greek_font(locl=True, italic=True)) == []


def test_greek_italic_gap_is_the_listed_three():
    assert verifylib.GREEK_ITALIC_GAP == {"Β": "the Latin accent",
                                          "ῤ́": 3, "ἂ": 3}


def _tone_font(shared):
    """A letter lookup plus a Bopomofo tone-mark lookup; `shared` puts
    the letters in the tone lookup as well."""
    anchors_, heights = _ruled(2)
    heights["tone"] = 500
    bases = "tone b0 b1" if shared else "tone"
    return _mark_font(anchors_, heights, cmap_extra={0x3105: "tone"},
                      fea_extra="feature mark { pos base [%s] <anchor 50 520> mark @TOP; } mark;\n"
                                % bases)


def test_tone_lookups_are_not_letter_lookups_for_the_anchor_passes():
    import anchors
    font = _tone_font(shared=False)
    every = anchors._mark_base_lookups(font)
    on_letter = anchors._mark_base_lookups(font, on_letter=True)
    assert len(every) == 2 and len(on_letter) == 1
    assert "tone" not in on_letter[0][1][0].BaseCoverage.glyphs
    # and the verifier reads the same subtables
    assert [i for i, _ in verifylib._mark_base_subtables(font)] == [i for i, _ in on_letter]


def test_check_tone_lookups_wants_no_letter_in_a_tone_lookup():
    assert _gate(verifylib.check_tone_lookups, _tone_font(shared=False)) == []
    off = _gate(verifylib.check_tone_lookups, _tone_font(shared=True))
    assert off and "b0" in off[0]


def _seat(font):
    return _gate(lambda f, chk: verifylib.check_marks_seat(f, _shaper_for(f), chk,
                                                          f.getGlyphSet()), font)


def _cells(font, full=None):
    """check_cells minus check_letter_glyphs's two messages: every
    _mark_font fixture below maps only a handful of ASCII codepoints
    (whichever the anchors/cmap_extra name), so the full-repertoire
    check fails on all of them by construction. That check has its own
    tests (test_check_letter_glyphs_... and
    test_check_cells_also_runs_check_letter_glyphs below); this helper
    stays about the width/placement gates the callers below mutate."""
    out = _gate(lambda f, chk: verifylib.check_cells(f, chk, _shaper_for(f), f.getGlyphSet(),
                                                     600, full), font)
    return [m for m in out if "ASCII letter" not in m and m != ".notdef draws"]


def test_check_marks_seat_holds_each_letter_to_its_kind():
    """One letter's anchor 100 below its category's, inside every
    absolute band (round 9, mutant L12b: B's anchors 140 down passed)."""
    anchors, heights = _ruled()
    anchors["b3"] = (50, heights["b3"] - 80)      # dy -80: inside _SEAT_DY, 100 off the kind
    off = _seat(_mark_font(anchors, heights))
    assert off and "b3" in off[0] and "kind" in off[0]
    # the same letter, in a kind too small to have a median (the one
    # lowercase letter among capitals), is held to the absolute bands only
    assert _seat(_mark_font(anchors, heights, cmap_extra={0x61: "b3"})) == []


def test_check_marks_seat_measures_a_letter_that_composes_with_the_first_mark():
    """'A' + acute composes to Á and used to be skipped; the gate takes
    the next mark that does not compose (round 9, mutants L8, L14)."""
    anchors, heights = _ruled()
    anchors["b0"] = (50, heights["b0"] - 80)      # b0 is 'A'
    font = _mark_font(anchors, heights, marks={"grave": 0x0310})  # U+0310 composes with nothing
    assert any("b0" in m for m in _seat(font))


def test_check_marks_stack_holds_the_second_marks_ink_over_the_first():
    """An exact Mark2 anchor 200 to the side stacks the second accent
    beside the first (round 9, mutant L18)."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (250, 200), "acute": (250, 200)})
    off = _stack(font)
    assert off and "ink" in off[0]


def test_check_cap_forms_fails_a_face_that_does_not_raise():
    """This used to return with no check when B + acute kept the plain
    acute (round 9, mutant L10: the raising chain deleted)."""
    anchors, heights = _ruled()
    low = _gate(lambda f, chk: verifylib.check_cap_forms(f, _shaper_for(f), chk),
                _mark_font(anchors, heights))
    assert low and "plain acute" in low[0]


def test_check_dotless_wants_i_and_j_swapped_under_an_accent():
    anchors, heights = _ruled(2)
    heights["dotlessi"] = 400
    cmap = {0x69: "b0", 0x6A: "b1"}
    swapped = _mark_font(anchors, heights, cmap_extra=cmap,
                         fea_extra="feature ccmp { sub [b0 b1]' acute by dotlessi; } ccmp;\n")
    run = lambda f: _gate(lambda g, chk: verifylib.check_dotless(g, _shaper_for(g), chk), f)  # noqa: E731
    assert run(swapped) == []
    dotted = run(_mark_font(anchors, heights, cmap_extra=cmap))
    assert dotted and "U+0301" in dotted[0]


def test_check_widths_by_class_holds_the_advance_and_the_shaped_advance():
    """'e' at two cells passed check_grid (a whole number of cells);
    a SinglePos advance under ccmp moved the next column (round 9,
    mutants L1, L5b)."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, cmap_extra={0x65: "b4"}, width=500)
    assert _cells(font) == []
    font["hmtx"].metrics["b4"] = (1200, 0)
    off = _cells(font)
    assert off and "'e': ('Na', 1200)" in off[0]
    pushed = _mark_font(anchors, heights, cmap_extra={0x65: "b4"}, width=500,
                        fea_extra="feature ccmp { pos b4 <0 0 100 0>; } ccmp;\n")
    off = _cells(pushed)
    assert off and "'e': (600, 700)" in off[0]


def test_check_glyph_placement_holds_a_letter_to_its_cells_centre_and_baseline():
    """One glyph drawn 250 to the side, or 200 up, passed every gate
    (round 9, mutants L2, L3)."""
    anchors, heights = _ruled()
    assert _cells(_mark_font(anchors, heights, width=500)) == []
    aside = _cells(_mark_font(anchors, heights, width=100))    # ink 0..100, centre 50 of 300
    assert aside and "centre" in aside[0]
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    font = _mark_font(anchors, heights, width=500)
    pen = T2CharStringPen(0, None)
    pen.moveTo((0, 200))
    pen.lineTo((500, 200))
    pen.lineTo((500, 600))
    pen.closePath()
    td = font["CFF "].cff.topDictIndex[0]
    td.CharStrings["b2"] = pen.getCharString(private=td.Private)
    up = _cells(font)
    assert up and "baseline" in up[0]


def test_check_cells_also_runs_check_letter_glyphs():
    """check_cells wires check_letter_glyphs in after check_glyph_placement
    (it used to be defined and unit-tested but reached from no driver),
    so a font whose cmap never reaches most of ASCII -- every _mark_font
    fixture above, which cmaps only the handful of codepoints a test
    names -- fails through the one entry point every driver calls."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, width=500)
    off = _gate(lambda f, chk: verifylib.check_cells(f, chk, _shaper_for(f), f.getGlyphSet(),
                                                     600, None), font)
    assert any("ASCII letter" in m for m in off)


def test_round_9_bands_are_the_measured_ones():
    assert verifylib._SEAT_SPREAD == 60 and verifylib._SEAT_KIND == 5
    assert verifylib._STACK_DX == 80 and verifylib._LEAN == 230
    assert verifylib._CENTRE_BAND == 120 and verifylib._BASELINE == (-20, 10)
    assert verifylib._IDEOGRAPH_Y == (-130, 890)
    assert verifylib._EDGE == 12 and verifylib._ZERO_ADVANCE_X == (-120, 300)
    assert verifylib.MULTI_EM == {0x2E3A: 2, 0x2E3B: 3}
    assert 0xFEFF in verifylib.DEFAULT_IGNORABLE and 0x00AD in verifylib.DEFAULT_IGNORABLE


def test_check_marks_seat_holds_each_mark_to_the_lookups_sideways_offset():
    """One mark's outline moved 220 right, its anchor left behind, sits
    220 off where the lookup's other marks sit (round 9, mutant L13)."""
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300, "circ": 0x0302}, width=100)
    pen = T2CharStringPen(0, None)
    pen.moveTo((220, 0))
    pen.lineTo((320, 0))
    pen.lineTo((320, 500))
    pen.closePath()
    td = font["CFF "].cff.topDictIndex[0]
    td.CharStrings["circ"] = pen.getCharString(private=td.Private)
    off = _seat(font)
    assert off and "'circ', 'dx', 220" in off[0]


# --- the face-wide gates (round 10) ------------------------------------------

def test_check_font_matrix_wants_1_1000_everywhere():
    """A FontMatrix of 0.0007 drew every glyph at 70% in FreeType while
    every other gate here read it whole, since fontTools ignores the
    matrix (round 10, mutants G8, J29)."""
    anchors, heights = _ruled(2)
    font = _mark_font(anchors, heights)
    assert _gate(verifylib.check_font_matrix, font) == []
    td = font["CFF "].cff.topDictIndex[0]
    td.FontMatrix = [0.0007, 0, 0, 0.0007, 0, 0]
    off = _gate(verifylib.check_font_matrix, font)
    assert off and "top" in off[0]


def test_check_line_metrics_wants_the_pinned_numbers_not_just_agreement():
    """verify.py pinned LINE_METRICS and the Latin faces only asked
    hhea == typo, so a 1400/-600 line -- equal to itself but not the
    real numbers -- passed there (round 10, mutants G7, G33, V11)."""
    font = _metadata_font()
    hhea, os2 = font["hhea"], font["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = verifylib.LINE_METRICS
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = verifylib.LINE_METRICS
    assert _gate(verifylib.check_line_metrics, font) == []
    bad = _metadata_font()
    hhea, os2 = bad["hhea"], bad["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = 1400, -600, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = 1400, -600, 0
    off = _gate(verifylib.check_line_metrics, bad)
    assert off and "1400" in off[0]


def test_check_gdef_classes_wants_no_spacing_letter_marked_as_a_mark():
    """A shaper zeroes the advance of every class-3 glyph: '?' classed
    as a mark drew over the letter before it (round 10, mutants G3,
    J27)."""
    anchors, heights = _ruled(2)
    font = _mark_font(anchors, heights)
    assert _gate(verifylib.check_gdef_classes, font) == []
    font["GDEF"].table.GlyphClassDef.classDefs["b0"] = 3
    off = _gate(verifylib.check_gdef_classes, font)
    assert off and "U+0041" in off[0]


def test_check_pair_positioning_wants_only_vkrn_pairs():
    """A PairPos under ccmp moved the letter after 'a' 300 units; the
    build drops kern/palt/halt because the grid is the spacing, and
    Source Han Sans's vertical kerning stays, opt-in (round 10,
    mutants G4, J28b, J46)."""
    anchors, heights = _ruled(2)
    kerned = _mark_font(anchors, heights,
                        fea_extra="feature kern { pos b0 b1 -300; } kern;\n")
    off = _gate(verifylib.check_pair_positioning, kerned)
    assert off and "kern" in off[0]
    vkerned = _mark_font(anchors, heights,
                         fea_extra="feature vkrn { pos b0 b1 -300; } vkrn;\n")
    assert _gate(verifylib.check_pair_positioning, vkerned) == []


def test_check_substitution_identity_wants_nfkd_equivalence():
    """A substitution never turns a character into another character --
    rn to m, 0 to O, ａ to ｂ's half-width form -- but an unencoded
    output (the ligature glyphs the other gates measure) is exempt, and
    so is 'aalt', whose whole point is to reach every related glyph
    (round 10, mutants G5, G37, J51)."""
    anchors, heights = _ruled(3)          # b0/b1/b2 cmap to 'A'/'B'/'C'
    bad = _mark_font(anchors, heights,
                     fea_extra="feature liga { sub b0 b1 by b2; } liga;\n")
    off = _gate(verifylib.check_substitution_identity, bad)
    assert off and "b2" in off[0]
    good = _mark_font(anchors, heights, marks={"lig": None},
                      fea_extra="feature liga { sub b0 b1 by lig; } liga;\n"
                                "feature aalt { sub b0 by b2; } aalt;\n")
    assert _gate(verifylib.check_substitution_identity, good) == []


def _lig_box(cell, *pts):
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    x0, y0, x1, y1 = pts
    pen = T2CharStringPen(0, None)
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return pen


def _lig_font(lig_box, cell=500):
    """b0 ('-'), b1 ('>') and an unencoded 'lig' -- build.LIGATURES'
    '->' entry, the one two-character ligature a two-letter fixture can
    map -- with 'lig' drawn at `lig_box`."""
    from conftest import make_cff_font
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    order = [".notdef", "b0", "b1", "lig"]
    boxes = {".notdef": (0, 0, cell, 500), "b0": (0, 0, cell, 500),
            "b1": (0, 0, cell, 500), "lig": lig_box}
    font = make_cff_font(order, {g: _lig_box(cell, *boxes[g]).getCharString() for g in order},
                         {0x2D: "b0", 0x3E: "b1"}, {g: (cell, 0) for g in order})
    td = font["CFF "].cff.topDictIndex[0]
    for g in order:                       # re-cut with the real Private subrs
        td.CharStrings[g] = _lig_box(cell, *boxes[g]).getCharString(private=td.Private)
    addOpenTypeFeaturesFromString(font, "feature liga { sub b0 b1 by lig; } liga;\n")
    return font


def test_check_ligature_cells_holds_the_unencoded_glyph_to_its_parts():
    """A ligature glyph is unencoded, so nothing else holds its ink: one
    drawn 250 up floated over the x-height and every other gate passed
    it (round 10, mutants G1, G1b, G1c, V10)."""
    good = _lig_font((0, 0, 1000, 500))
    off = _gate(lambda f, chk: verifylib.check_ligature_cells(
        f, _shaper_for(f), chk, f.getGlyphSet(), 500), good)
    assert off == []
    bad = _lig_font((0, 700, 1000, 900))     # floats over b0/b1's 0..500 ink
    off = _gate(lambda f, chk: verifylib.check_ligature_cells(
        f, _shaper_for(f), chk, f.getGlyphSet(), 500), bad)
    assert off and "'->': ('height'" in off[0]


def test_check_blank_glyphs_wants_notdef_inked_and_spaces_blank():
    """.notdef must draw a box (an unknown character shows one, not
    nothing) and the spaces / default-ignorables must draw nothing
    (round 10, mutants G25, G26)."""
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    anchors, heights = _ruled(2)
    font = _mark_font(anchors, heights, width=200)
    assert _gate(lambda f, chk: verifylib.check_blank_glyphs(f, chk, f.getGlyphSet()),
                font) == []
    blank_notdef = _mark_font(anchors, heights, width=200)
    td = blank_notdef["CFF "].cff.topDictIndex[0]
    td.CharStrings[".notdef"] = T2CharStringPen(0, None).getCharString(private=td.Private)
    off = _gate(lambda f, chk: verifylib.check_blank_glyphs(f, chk, f.getGlyphSet()),
               blank_notdef)
    assert off and ".notdef draws a box" in off[0]
    inked_space = _mark_font(anchors, heights, width=200, cmap_extra={0x20: "b0"})
    off = _gate(lambda f, chk: verifylib.check_blank_glyphs(f, chk, f.getGlyphSet()),
               inked_space)
    assert off and "U+0020" in off[0]


def test_check_name_composition_wants_full_and_postscript_to_match_family_and_style():
    """nameID 4 is the family and subfamily, 6 the PostScript pair: a
    Regular calling itself 'Gengou Code Bold' in both passed (round 10,
    mutant G13)."""
    font = _metadata_font()
    font["name"].setName("Test", 4, 3, 1, 0x409)
    font["name"].setName("Test-Regular", 6, 3, 1, 0x409)
    assert _gate(verifylib.check_name_composition, font) == []
    bad = _metadata_font()
    bad["name"].setName("Test Bold", 4, 3, 1, 0x409)
    bad["name"].setName("Test-Regular", 6, 3, 1, 0x409)
    off = _gate(verifylib.check_name_composition, bad)
    assert off and "Test Bold" in off[0]


def test_check_family_cmap_wants_every_sibling_codepoint():
    """A codepoint dropped from one face still passed its own repertoire
    floor: check_family_cmap holds it to a sibling built beside it
    (round 10, mutant G9)."""
    mine = _metadata_font()
    sibling = _metadata_font()
    sibling["cmap"].tables[0].cmap[0x63] = "a"
    off = _gate(lambda f, chk: verifylib.check_family_cmap(f, chk, sibling), mine)
    assert off and "U+0063" in off[0]
    assert _gate(lambda f, chk: verifylib.check_family_cmap(f, chk, mine), sibling) == []
    assert verifylib._MARK_DX_SPREAD == 150


def _donor_font(tmp_path, cmap):
    """A tiny real font saved to disk, standing in for
    SourceCodeVF-Upright.otf: check_donor_repertoire only ever reads its
    cmap back off disk."""
    from conftest import make_font
    order = [".notdef", *dict.fromkeys(cmap.values())]
    font = make_font(order, cmap, {g: 600 for g in order})
    path = tmp_path / "donor.ttf"
    font.save(path)
    return path


def test_check_donor_repertoire_passes_a_cmap_that_covers_the_donor(monkeypatch, tmp_path):
    donor_cmap = {0x21: "exclam", 0x41: "A", 0x61: "a"}
    monkeypatch.setenv("SCP_VF_U", str(_donor_font(tmp_path, donor_cmap)))
    check = verifylib.Checker()
    verifylib.check_donor_repertoire(check, {**donor_cmap, 0x30: "zero"})
    assert not check.failed


def test_check_donor_repertoire_fails_and_names_the_missing_codepoint_in_hex(
        monkeypatch, tmp_path, capsys):
    """The Latin layer is grafted whole, so the donor's cmap is a floor
    under every face of the family; a sibling comparison alone left the
    family's own Regular with nothing to be compared against, and 40 IPA
    letters deleted from it passed every gate (round 11, mutant B2)."""
    donor_cmap = {0x21: "exclam", 0x41: "A", 0x61: "a"}
    monkeypatch.setenv("SCP_VF_U", str(_donor_font(tmp_path, donor_cmap)))
    check = verifylib.Checker()
    verifylib.check_donor_repertoire(check, {0x41: "A", 0x61: "a"})   # 0x21 missing
    assert check.failed
    assert "0x21" in capsys.readouterr().out


def test_check_donor_repertoire_skips_without_scp_vf_u(monkeypatch, capsys):
    """SCP_VF_U names the donor; without it there is nothing to read, so
    the gate says skip rather than reporting a pass it has no grounds
    for (the None verdict Checker prints as 'skip', not 'ok')."""
    monkeypatch.delenv("SCP_VF_U", raising=False)
    check = verifylib.Checker()
    verifylib.check_donor_repertoire(check, {0x61: "a"})
    assert check.failed is False
    out = capsys.readouterr().out
    assert out.startswith("skip ") and "SCP_VF_U unset" in out


def test_check_donor_repertoire_skips_when_scp_vf_u_names_no_file(monkeypatch, tmp_path,
                                                                  capsys):
    """A stale or mistyped path is exactly as unreadable as an unset one
    -- it skips instead of raising."""
    monkeypatch.setenv("SCP_VF_U", str(tmp_path / "does-not-exist.otf"))
    check = verifylib.Checker()
    verifylib.check_donor_repertoire(check, {0x61: "a"})
    assert check.failed is False
    assert capsys.readouterr().out.startswith("skip ")


# --- round 11: a shaper reads everything at once (check_run_identity,
# check_ligature_guards), the GPOS surface, mark filtering sets, the
# stacked gap, and every GSUB kind -------------------------------------

def _run_identity(font):
    return _gate(lambda f, chk: verifylib.check_run_identity(f, _shaper_for(f), chk), font)


def test_check_run_identity_passes_a_plain_run():
    anchors, heights = _ruled()
    assert _run_identity(_mark_font(anchors, heights)) == []


def test_check_run_identity_catches_a_singlepos_placement_under_ccmp():
    """The gates around this one read one thing each -- check_widths_by_class
    the advance, check_glyph_placement the outline -- and a shaper reads
    both at once: a SinglePos y placement under ccmp dropped the digits
    180 units, sitting 3 px low beside the letters, while every gate
    that reads one thing at a time stayed clean (round 11)."""
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights,
                      fea_extra="feature ccmp { pos b0 <0 -180 0 0>; } ccmp;\n")
    off = _run_identity(font)
    assert off and "moved" in off[0] and "'A'" in off[0]


def test_check_run_identity_catches_an_uncontexted_substitution():
    """check_substitution_identity excuses i -> dotless i by name, since
    that pair is meant for a letter about to take an accent -- so an
    UNCONTEXTED version of the same rule, firing on a bare 'i' too, is
    invisible to it; only shaping a run on its own shows it (round 11)."""
    anchors, heights = _ruled(2)
    heights["dotlessi"] = heights["iletter"] = 400
    font = _mark_font(anchors, heights, cmap_extra={0x69: "iletter"},
                      fea_extra="feature ccmp { sub iletter by dotlessi; } ccmp;\n")
    assert _gate(verifylib.check_substitution_identity, font) == []
    off = _run_identity(font)
    assert off and "'i'" in off[0] and "dotlessi" in off[0]


def test_plain_characters_leaves_out_marks_ignorables_gdef3_and_double_span():
    """_plain_characters is what check_run_identity now shapes alone --
    every mapped codepoint that ordinary text is made of: not a Unicode
    Mark, not a DEFAULT_IGNORABLE, not a DOUBLE_SPAN diacritic, and not a
    glyph GDEF calls a mark (class 3). An ordinary letter among them is
    kept."""
    from conftest import make_font
    cmap = {0x61: "a",            # an ordinary letter: kept
            0x62: "b3",           # GDEF class 3, though not a Unicode mark
            0x0301: "acute",      # combining acute: Unicode category Mn
            0x200B: "zwsp",       # DEFAULT_IGNORABLE (zero-width space)
            0x035C: "dbrv"}       # DOUBLE_SPAN (a double diacritic)
    order = [".notdef", *cmap.values()]
    font = make_font(order, cmap, {g: 500 for g in order})
    assert verifylib._plain_characters(font, {"b3": 3}) == [0x61]


def _wide_repertoire_font(bad_index=None):
    """ASCII 'a'/'b' plus a 100-character block of Private Use Area
    codepoints well past 0x7F -- a shape wide enough that
    _run_alphabet's 40-character spread of it (step 2) never lands on an
    odd index. `bad_index`, given odd, puts a SinglePos y placement
    under ccmp on that one block glyph: reachable only by shaping the
    whole repertoire alone, never by the sampled pair alphabet (round
    11, mutant D2 -- a ccmp rule dropping every kana this way slipped
    through the same 40-sample spread used for both probes)."""
    from conftest import make_font
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    block = [f"p{i}" for i in range(100)]
    cmap = {0x61: "a", 0x62: "b", **{0xE000 + i: f"p{i}" for i in range(100)}}
    order = [".notdef", "a", "b", *block]
    font = make_font(order, cmap, {g: 600 for g in order})
    target = None
    if bad_index is not None:
        assert bad_index % 2 == 1     # never selected by rest[::2]
        addOpenTypeFeaturesFromString(
            font, f"feature ccmp {{ pos p{bad_index} <0 50 0 0>; }} ccmp;\n")
        target = 0xE000 + bad_index
    return font, target


def test_check_run_identity_reaches_a_character_the_sampled_alphabet_steps_over():
    font, target = _wide_repertoire_font(bad_index=51)
    assert target not in verifylib._run_alphabet(font, {})    # the mutant's blind spot
    off = _run_identity(font)
    assert off and "moved" in off[0]


def test_check_run_identity_passes_a_clean_font_of_the_same_shape():
    font, _ = _wide_repertoire_font()
    assert _run_identity(font) == []


def _guard_font(guarded):
    """':' alone in the cmap and the unencoded glyph build.LIGATURES'
    own '::' entry compiles to -- every other declared ligature needs a
    second character (=, >, <) this font has no glyph for, so '::' is
    the only one check_ligature_guards has anything to probe.
    `guarded` writes the real defence, a chain context that blocks the
    rule when a third colon precedes or follows (build._guard_subtables'
    rules a and b); without it the ligature reaches into a longer run,
    same as deleting those two rules did (round 11, mutant B3)."""
    from conftest import make_cff_font
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    order = [".notdef", "colon", "lig"]

    def box():
        pen = T2CharStringPen(0, None)
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((500, 500))
        pen.closePath()
        return pen.getCharString()
    font = make_cff_font(order, {g: box() for g in order}, {0x3A: "colon"},
                         {g: (500, 0) for g in order})
    fea = ("feature liga {\n"
           "    ignore sub colon colon' colon';\n"
           "    ignore sub colon' colon' colon;\n"
           "    sub colon' colon' by lig;\n"
           "} liga;\n") if guarded else "feature liga { sub colon colon by lig; } liga;\n"
    addOpenTypeFeaturesFromString(font, fea)
    return font


def test_check_ligature_guards_passes_a_guarded_ligature():
    font = _guard_font(guarded=True)
    assert _gate(lambda f, chk: verifylib.check_ligature_guards(f, _shaper_for(f), chk),
                font) == []


def test_check_ligature_guards_catches_a_ligature_reaching_into_a_longer_run():
    """Only verify.py's hand-written CASES list ever probed the guards:
    without them ':::' shapes as the '::' ligature and a bare colon,
    three colons collapsed to two glyphs instead of staying three."""
    font = _guard_font(guarded=False)
    off = _gate(lambda f, chk: verifylib.check_ligature_guards(f, _shaper_for(f), chk), font)
    assert off and "':::'" in off[0]


def _fire_font(fires, blank=False):
    """'a', 'b', the space and ':' in the cmap, and the unencoded glyph
    build.LIGATURES' '::' entry compiles to -- the one declared
    sequence a font with this cmap can shape. `fires` writes the rule;
    without it the sequence stays two colons, which is what a build
    that lost its liga lookup ships. `blank` keeps the rule and empties
    the ligature glyph."""
    from conftest import make_cff_font
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    order = [".notdef", "a", "b", "space", "colon", "lig"]

    def box(empty=False):
        pen = T2CharStringPen(0, None)
        if not empty:
            pen.moveTo((0, 0))
            pen.lineTo((400, 0))
            pen.lineTo((400, 400))
            pen.closePath()
        return pen.getCharString()
    charstrings = {g: box(g == "lig" and blank) for g in order}
    cmap = {0x61: "a", 0x62: "b", 0x20: "space", 0x3A: "colon"}
    widths = {g: (500, 0) for g in order}
    widths["lig"] = (1000, 0)          # build.LIGATURES['::'] is two cells
    font = make_cff_font(order, charstrings, cmap, widths)
    if fires:
        addOpenTypeFeaturesFromString(
            font, "feature liga { sub colon colon by lig; } liga;\n")
    return font


def test_check_ligatures_fire_passes_a_ligature_that_fires():
    font = _fire_font(fires=True)
    assert _gate(lambda f, chk: verifylib.check_ligatures_fire(
        f, _shaper_for(f), chk, f.getGlyphSet(), 500), font) == []


def test_check_ligatures_fire_catches_a_ligature_that_stays_plain():
    """The rule the JP driver could not see: it summed the advances of
    whatever sat between the padding, and a sequence that does not
    ligate leaves its own characters there at one cell each -- the same
    number the declared cells come to. All 61 passed while not firing
    (round 12)."""
    off = _gate(lambda f, chk: verifylib.check_ligatures_fire(
        f, _shaper_for(f), chk, f.getGlyphSet(), 500), _fire_font(fires=False))
    assert off and "'::'" in off[0] and "glyphs" in off[0]


def test_check_ligatures_fire_catches_a_ligature_drawn_as_whitespace():
    """It has to draw: a build that emptied the set would pass on the
    glyph count and the advance alone."""
    off = _gate(lambda f, chk: verifylib.check_ligatures_fire(
        f, _shaper_for(f), chk, f.getGlyphSet(), 500), _fire_font(fires=True, blank=True))
    assert off and "blank" in off[0]


def test_check_pair_positioning_wants_only_positioning_kinds():
    """A cursive lookup under 'curs' (type 3) walks a word up the line
    -- the build makes only single adjustment, pair, the two mark
    attachments and chain context (POSITIONING_KINDS) -- while every
    gate that read by feature, not by type, passed it (round 11,
    mutant A2)."""
    anchors, heights = _ruled(2)
    assert _gate(verifylib.check_pair_positioning, _mark_font(anchors, heights)) == []
    curs = _mark_font(anchors, heights,
                      fea_extra="feature curs { pos cursive b0 <anchor 100 0> "
                                "<anchor 500 260>; } curs;\n")
    off = _gate(verifylib.check_pair_positioning, curs)
    assert off and "curs" in off[0]


def test_check_mark_reachability_wants_the_filtering_set_to_hold_every_mark():
    """The two doors a lookup filters its marks through are the mark
    attachment class and the filtering set (LookupFlag 0x10); a set
    that leaves the acute out silenced the stacking and every gate
    agreed (round 11, mutant C1)."""
    from fontTools.ttLib.tables import otTables
    anchors, heights = _ruled()
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, 500), "acute": (50, 500)})
    assert _gate(verifylib.check_mark_reachability, font) == []
    cov = otTables.Coverage()
    cov.glyphs = ["grave"]              # leaves 'acute' out
    mgs = otTables.MarkGlyphSetsDef()
    mgs.Coverage = [cov]
    mgs.MarkSetCount = 1
    font["GDEF"].table.MarkGlyphSetsDef = mgs
    lookup = next(font["GPOS"].table.LookupList.Lookup[i]
                 for i, kind, _subs, _tags in verifylib._pos_lookups(font) if kind == 6)
    lookup.LookupFlag |= 0x10
    lookup.MarkFilteringSet = 0
    off = _gate(verifylib.check_mark_reachability, font)
    assert off and "leaves out" in off[0] and "acute" in off[0]


def test_check_substitution_identity_catches_an_alternate_subst():
    """A shaper takes alternate 0 of a default feature, so every
    alternate is a rule: an AlternateSubst turning l into 1 was read by
    nothing while the gate walked the single and ligature kinds only
    (round 11, mutant A4)."""
    anchors, heights = _ruled(3)
    off = _gate(verifylib.check_substitution_identity,
               _mark_font(anchors, heights,
                          fea_extra="feature ccmp { sub b0 from [b1 b2]; } ccmp;\n"))
    assert off and "b0" in off[0] and "b1" in off[0]


def test_check_substitution_identity_excuses_an_alternate_to_an_unencoded_glyph():
    """An alternate reaching an unencoded glyph is what the other gates
    measure, same as a ligature's own unencoded output."""
    anchors, heights = _ruled(3)
    heights["variant"] = 500
    font = _mark_font(anchors, heights, marks={"variant": None},
                      fea_extra="feature ccmp { sub b0 from [variant]; } ccmp;\n")
    assert _gate(verifylib.check_substitution_identity, font) == []


def test_check_substitution_identity_catches_a_multiple_subst():
    """All four GSUB kinds are walked now: a MultipleSubst spelling one
    character as two others was invisible to the single/ligature walk
    (round 11)."""
    anchors, heights = _ruled(3)
    off = _gate(verifylib.check_substitution_identity,
               _mark_font(anchors, heights,
                          fea_extra="feature ccmp { sub b0 by b1 b2; } ccmp;\n"))
    assert off and "b0" in off[0]


def test_check_substitution_identity_allows_the_ukrainian_yi_decomposition():
    """SUBSTITUTED_CHARACTERS is built by NFKD-normalising its pairs and
    names the Ukrainian ї, which both Adobe donors take apart onto the
    Latin dotless i before a combining accent so the accent can stack
    (anchors.import_donor_decompositions) -- its own canonical
    decomposition uses the Cyrillic і instead, so only the donor's exact
    pair is let through, not ї's decomposition in general."""
    anchors, heights = _ruled(2)
    heights["dotlessi"] = heights["diaeresis"] = 400
    font = _mark_font(anchors, heights,
                      cmap_extra={0x457: "b0", 0x131: "dotlessi", 0x308: "diaeresis"},
                      fea_extra="feature ccmp { sub b0 by dotlessi diaeresis; } ccmp;\n")
    assert _gate(verifylib.check_substitution_identity, font) == []
