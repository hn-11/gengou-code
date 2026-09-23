"""Unit tests for scripts/golden.py, the golden-file regression tool
every "byte-identical" / "no difference in rendered ink" claim in
the design notes (`git show a7c86ec:docs/gengou-plan.md`) was
established with. It had no test of its own:
a check that quietly stopped noticing a difference would fail silently
forever after, so each test here pins ONE of golden.py's checks by
building a golden/candidate pair that differs in exactly the thing
that check exists to catch, and asserting golden reports a failure --
plus, for the same pair made identical, that it reports none."""

import io
import sys
from pathlib import Path
from types import SimpleNamespace

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.misc.psCharStrings import T2CharString
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import golden  # noqa: E402
from conftest import make_cff_font, make_font  # noqa: E402

ARGS = SimpleNamespace(tolerance=2, ignore_names=False)


def _box_glyph(x0, y0, x1, y1):
    """A TTGlyph box, for the outline tests (TrueType outlines, no CFF
    machinery needed)."""
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return pen.glyph()


def _box_cs(w=600, h=700):
    """A fresh T2CharString box -- fresh every call, since FontBuilder.
    setupCFF stamps its own Private/GlobalSubrs onto whatever charstring
    objects it is given, so two fonts must never share one instance."""
    pen = T2CharStringPen(0, None)
    pen.moveTo((0, 0))
    pen.lineTo((w, 0))
    pen.lineTo((w, h))
    pen.closePath()
    return pen.getCharString()


def _boxes(order, w=600, h=700):
    return {g: _box_cs(w, h) for g in order}


def _hinted_box_cs(w=600, h=700):
    """A box outline that also carries an hstem, for the compare_pair
    tests below: HINT_CHARS includes 'a', so an 'a' with no hint at all
    fails check_hints on its own regardless of golden vs. candidate --
    real faces hint it, and an all-in-one pipeline test should use a
    fixture that could pass every check, not just the one under test."""
    pen = T2CharStringPen(0, None)
    pen.moveTo((0, 0))
    pen.lineTo((w, 0))
    pen.lineTo((w, h))
    pen.closePath()
    cs = pen.getCharString()
    cs.program = [10, 20, "hstem", *cs.program]
    return cs


def _shaper_for(font):
    buf = io.BytesIO()
    font.save(buf)
    return golden.make_shaper(buf.getvalue())


# --- check_cmap: codepoint coverage ------------------------------------------

def test_check_cmap_catches_a_missing_codepoint():
    """The whole comparison is keyed off codepoints shared by both
    builds; a codepoint present in the golden cmap and gone from the
    candidate's is exactly the case check_cmap exists for."""
    cmap_g, cmap_c = {97: "a", 98: "b"}, {97: "a"}
    rep = golden.Reporter()
    common = golden.check_cmap(rep, cmap_g, cmap_c)
    assert rep.failures == 1
    assert common == {97}

    rep = golden.Reporter()
    golden.check_cmap(rep, cmap_g, dict(cmap_g))
    assert rep.failures == 0


# --- check_advances: hmtx by codepoint ---------------------------------------

def test_check_advances_catches_one_advance_different():
    font_g = make_font([".notdef", "A"], {65: "A"}, {"A": 600})
    font_c = make_font([".notdef", "A"], {65: "A"}, {"A": 650})
    rep = golden.Reporter()
    golden.check_advances(rep, {65}, {65: "A"}, {65: "A"}, font_g["hmtx"], font_c["hmtx"])
    assert rep.failures == 1

    rep = golden.Reporter()
    golden.check_advances(rep, {65}, {65: "A"}, {65: "A"}, font_g["hmtx"], font_g["hmtx"])
    assert rep.failures == 0


def test_check_advances_catches_a_cmap_entry_redirected_to_a_different_glyph():
    """Glyph *names* (and indices) are free to differ between the two
    builds -- a rebuild routinely renumbers them -- so the comparison
    goes through each build's OWN cmap. If U+0041 is redirected to a
    same-named-nothing glyph whose width differs, that has to surface
    exactly as an advance mismatch even though no glyph is named 'A'
    in both fonts."""
    font_g = make_font([".notdef", "A"], {65: "A"}, {"A": 600})
    font_c = make_font([".notdef", "B"], {65: "B"}, {"B": 650})
    rep = golden.Reporter()
    golden.check_advances(rep, {65}, {65: "A"}, {65: "B"}, font_g["hmtx"], font_c["hmtx"])
    assert rep.failures == 1

    # renamed but otherwise the same width: not a difference
    font_c_same_width = make_font([".notdef", "B"], {65: "B"}, {"B": 600})
    rep = golden.Reporter()
    golden.check_advances(rep, {65}, {65: "A"}, {65: "B"},
                          font_g["hmtx"], font_c_same_width["hmtx"])
    assert rep.failures == 0


# --- check_feature_tags: GSUB/GPOS feature sets ------------------------------

def test_check_feature_tags_catches_a_feature_present_in_one_only():
    order = [".notdef", "a", "b", "ab"]
    cmap = {97: "a", 98: "b"}
    metrics = {".notdef": (0, 0), "a": (600, 0), "b": (600, 0), "ab": (1000, 0)}
    font_g = make_cff_font(order, _boxes(order), cmap, dict(metrics))
    font_c = make_cff_font(order, _boxes(order), cmap, dict(metrics))
    addOpenTypeFeaturesFromString(font_g, "feature calt { sub a b by ab; } calt;\n")

    rep = golden.Reporter()
    golden.check_feature_tags(rep, font_g, font_c, "GSUB")
    assert rep.failures == 1


def test_check_feature_tags_catches_a_differing_tag_set():
    order = [".notdef", "a", "b", "ab"]
    cmap = {97: "a", 98: "b"}
    metrics = {".notdef": (0, 0), "a": (600, 0), "b": (600, 0), "ab": (1000, 0)}
    font_g = make_cff_font(order, _boxes(order), cmap, dict(metrics))
    font_c = make_cff_font(order, _boxes(order), cmap, dict(metrics))
    addOpenTypeFeaturesFromString(
        font_g, "feature liga { sub a b by ab; } liga;\n"
                "feature calt { sub a b by ab; } calt;\n")
    addOpenTypeFeaturesFromString(font_c, "feature calt { sub a b by ab; } calt;\n")

    rep = golden.Reporter()
    golden.check_feature_tags(rep, font_g, font_c, "GSUB")
    assert rep.failures == 1

    font_c_same = make_cff_font(order, _boxes(order), cmap, dict(metrics))
    addOpenTypeFeaturesFromString(
        font_c_same, "feature liga { sub a b by ab; } liga;\n"
                     "feature calt { sub a b by ab; } calt;\n")
    rep = golden.Reporter()
    golden.check_feature_tags(rep, font_g, font_c_same, "GSUB")
    assert rep.failures == 0


# --- check_shaping: the actual shaped run ------------------------------------

def test_check_shaping_catches_a_run_that_shapes_differently():
    """A kerning pair changes how 'ab' shapes (x_advance of the first
    glyph) without touching cmap, hmtx or the outlines of either glyph
    on its own -- the one difference only an actual shaped run, not a
    per-glyph metric, can see."""
    order = [".notdef", "a", "b"]
    cmap = {97: "a", 98: "b"}
    metrics = {".notdef": (0, 0), "a": (600, 0), "b": (600, 0)}
    font_g = make_cff_font(order, _boxes(order), cmap, dict(metrics))
    font_c = make_cff_font(order, _boxes(order), cmap, dict(metrics))
    addOpenTypeFeaturesFromString(font_g, "feature kern { pos a b -50; } kern;\n")

    rep = golden.Reporter()
    golden.check_shaping(rep, _shaper_for(font_g), _shaper_for(font_c), ["ab"])
    assert rep.failures == len(golden.FEATURE_SETS)   # every feature set shapes it

    rep = golden.Reporter()
    golden.check_shaping(rep, _shaper_for(font_g), _shaper_for(font_g), ["ab"])
    assert rep.failures == 0


# --- check_outlines: bounding box within tolerance ---------------------------

def test_check_outlines_tolerance_boundary():
    """The bound is inclusive: a delta AT --tolerance is not a failure,
    one unit past it is. Contour count also has to agree even if the
    box does (not exercised here, but the same function)."""
    font_g = make_font([".notdef", "a"], {97: "a"}, {"a": 600},
                       glyphs={"a": _box_glyph(0, 0, 600, 700)})
    pairs = {"a": ("a", "U+0061")}

    over = make_font([".notdef", "a"], {97: "a"}, {"a": 603},
                     glyphs={"a": _box_glyph(0, 0, 603, 700)})
    rep = golden.Reporter()
    golden.check_outlines(rep, font_g, over, pairs, tolerance=2)
    assert rep.failures == 1

    at_bound = make_font([".notdef", "a"], {97: "a"}, {"a": 602},
                         glyphs={"a": _box_glyph(0, 0, 602, 700)})
    rep = golden.Reporter()
    golden.check_outlines(rep, font_g, at_bound, pairs, tolerance=2)
    assert rep.failures == 0

    identical = make_font([".notdef", "a"], {97: "a"}, {"a": 600},
                          glyphs={"a": _box_glyph(0, 0, 600, 700)})
    rep = golden.Reporter()
    golden.check_outlines(rep, font_g, identical, pairs, tolerance=2)
    assert rep.failures == 0


# --- check_metadata: OS/2, post, hhea, head and the name table --------------

def test_check_metadata_catches_a_field_difference():
    font_g = make_font([".notdef", "a"], {97: "a"}, {"a": 600})
    font_c = make_font([".notdef", "a"], {97: "a"}, {"a": 600})
    font_c["OS/2"].usWeightClass = 700

    rep = golden.Reporter()
    golden.check_metadata(rep, font_g, font_c, ignore_names=False)
    assert rep.failures == 1

    rep = golden.Reporter()
    golden.check_metadata(rep, font_g, font_g, ignore_names=False)
    assert rep.failures == 0


def test_check_metadata_catches_a_name_table_record_difference():
    font_g = make_font([".notdef", "a"], {97: "a"}, {"a": 600}, family="Gengou Code")
    font_c = make_font([".notdef", "a"], {97: "a"}, {"a": 600}, family="Gengou Code JP")

    rep = golden.Reporter()
    golden.check_metadata(rep, font_g, font_c, ignore_names=False)
    assert rep.failures == 1

    # --ignore-names exists for a deliberate rename; it must not also
    # hide an accidental one anywhere else, but here it is the only diff
    rep = golden.Reporter()
    golden.check_metadata(rep, font_g, font_c, ignore_names=True)
    assert rep.failures == 0


# --- check_hints: CFF hinting on the key characters --------------------------

def _hinted_cs():
    return T2CharString(program=[10, 20, "hstem", 0, 0, "rmoveto", "endchar"])


def _plain_cs():
    return T2CharString(program=[0, 0, "rmoveto", 100, "hlineto", "endchar"])


def test_check_hints_catches_a_glyph_that_lost_its_hint():
    font_g = make_cff_font([".notdef", "A"], {".notdef": _plain_cs(), "A": _hinted_cs()},
                           {65: "A"}, {".notdef": (0, 0), "A": (600, 0)})
    font_c = make_cff_font([".notdef", "A"], {".notdef": _plain_cs(), "A": _plain_cs()},
                           {65: "A"}, {".notdef": (0, 0), "A": (600, 0)})

    rep = golden.Reporter()
    golden.check_hints(rep, font_g, font_c, {65: "A"}, {65: "A"})
    assert rep.failures == 1

    font_c_hinted = make_cff_font([".notdef", "A"], {".notdef": _plain_cs(), "A": _hinted_cs()},
                                  {65: "A"}, {".notdef": (0, 0), "A": (600, 0)})
    rep = golden.Reporter()
    golden.check_hints(rep, font_g, font_c_hinted, {65: "A"}, {65: "A"})
    assert rep.failures == 0


def test_check_hints_skips_non_cff_fonts(capsys):
    font_g = make_font([".notdef", "A"], {65: "A"}, {"A": 600})
    font_c = make_font([".notdef", "A"], {65: "A"}, {"A": 600})
    rep = golden.Reporter()
    golden.check_hints(rep, font_g, font_c, {65: "A"}, {65: "A"})
    assert rep.checks == 0        # neither ok nor FAIL: nothing to hint-check
    assert "skip" in capsys.readouterr().out


# --- check_glyph_count: informational, never a failure -----------------------

def test_check_glyph_count_is_informational_only():
    """The docstring says +/-5% is informational; a candidate with
    double the glyphs still prints FAIL (so a human reading the log
    sees it) but must not move rep.failures, or a routine glyph-count
    change (renumbering, a dropped variant) would fail the whole run."""
    rep = golden.Reporter()
    golden.check_glyph_count(rep, [".notdef", "a"], [".notdef", "a", "b", "c"])
    assert rep.failures == 0
    assert rep.checks == 1


# --- compare_pair: the full pipeline on real files ---------------------------

def _hinted_a_font(width):
    return make_cff_font([".notdef", "a"], {".notdef": _box_cs(), "a": _hinted_box_cs()},
                         {97: "a"}, {".notdef": (0, 0), "a": (width, 0)})


def test_compare_pair_reports_no_failures_for_identical_builds(tmp_path):
    font_g = _hinted_a_font(600)
    font_c = _hinted_a_font(600)
    font_g.save(tmp_path / "g.otf")
    font_c.save(tmp_path / "c.otf")

    rep = golden.compare_pair(tmp_path / "g.otf", tmp_path / "c.otf", ARGS, ["a"])
    assert rep.failures == 0
    assert rep.checks > 0


def test_compare_pair_surfaces_a_single_advance_difference(tmp_path):
    """Wires every check together on real files: one width changed and
    nothing else should be enough for the whole pipeline (not just
    check_advances in isolation) to come back non-clean."""
    font_g = _hinted_a_font(600)
    font_c = _hinted_a_font(650)
    font_g.save(tmp_path / "g.otf")
    font_c.save(tmp_path / "c.otf")

    rep = golden.compare_pair(tmp_path / "g.otf", tmp_path / "c.otf", ARGS, ["a"])
    assert rep.failures > 0
