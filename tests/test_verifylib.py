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
                         ("Gengou JP Term NFM SemiBold", True),
                         ("Gengou JP Term Nerd Font Mono SemiBold", False),
                         (None, True)):                      # absent reads as empty
        check = verifylib.Checker()
        verifylib.check_gdi_family_name({"name": _Name(family)}, check)
        assert (not check.failed) is want, family


# --- the mark gates: placement, coverage, attachment ------------------------

def _mark_font(anchors, heights=None, advance=600, cmap_extra=(), width=100,
               mark_anchor=None, classify_mark=True, mark_cp=0x0301, marks=(),
               fea_extra="", mark2=None, langsys="", mark_scope="", mark_tail=""):
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
                         {".notdef": (0, 0), **{g: (advance, 0) for g in order[1:]}})
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
        fea += f"feature mkmk {{\n{stacks}\n}} mkmk;\n"
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
    fn(font, *args, lambda ok, msg: None if ok else out.append(msg))
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


def test_check_anchor_coverage_asks_only_of_letters():
    """A drawn, cmapped glyph that is not a letter takes no accent and
    is not a base; its absence is not a gap. The middle dot (U+00B7)
    sits inside the Latin-1 letter range, so it is the category test,
    not the range test, that has to excuse it."""
    anchors, heights = _ruled()
    heights["periodcentered"] = 500
    font = _mark_font(anchors, heights, cmap_extra={0xB7: "periodcentered"})
    assert _coverage(font) == []


def test_ink_spill_allows_half_a_cell_and_not_a_unit_more():
    """The bound is half a cell of lean either side of the advance."""
    cmap = {0x61: "a"}
    ok = {"a": (-300, 0, 900, 700)}
    assert verifylib.ink_spill(ok, lambda g: 600, cmap, 600) == []
    assert verifylib.ink_spill({"a": (-301, 0, 500, 700)}, lambda g: 600, cmap, 600) \
        == [("a", 600, -301, 500)]
    assert verifylib.ink_spill({"a": (0, 0, 901, 700)}, lambda g: 600, cmap, 600) \
        == [("a", 600, 0, 901)]


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
    assert verifylib.ink_spill({"a": (-300.135, 0, 500, 700)},
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
                      mark2={"grave": (50, 200), "acute": (50, 200)})
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
    font = _mark_font(anchors, heights, marks={"grave": 0x0300},
                      mark2={"grave": (50, 200), "acute": (50, 200)},
                      fea_extra="feature ccmp { pos b1 <0 10 0 0>; } ccmp;\n")
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


def test_check_one_cell_asks_of_notdef_and_the_ambiguous_symbols():
    font = _metadata_font()
    font["cmap"].tables[0].cmap = {0x61: "a", 0x2190: "b"}
    metrics = {".notdef": (600, 0), "a": (600, 0), "b": (600, 0)}
    assert _gate(lambda f, chk: verifylib.check_one_cell(f, chk, f.getBestCmap(), metrics, 600), font) == []
    metrics["b"] = (1200, 0)
    assert "'←' is one cell" in _gate(
        lambda f, chk: verifylib.check_one_cell(f, chk, f.getBestCmap(), metrics, 600), font)


def test_check_latin_repertoire_wants_the_size_and_no_cjk():
    latin = {cp: "a" for cp in range(0x20, 0x20 + 800)}
    assert _gate(lambda f, chk: verifylib.check_latin_repertoire(chk, latin), None) == []
    assert _gate(lambda f, chk: verifylib.check_latin_repertoire(chk, {**latin, 0x4E00: "a"}), None) \
        == ["no CJK / full-width codepoints"]
    assert _gate(lambda f, chk: verifylib.check_latin_repertoire(chk, dict(list(latin.items())[:10])), None)
