"""Unit tests that need no font files — pure logic + data validation."""

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pathops
import pytest
import uharfbuzz as hb
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import anchors  # noqa: E402
import build  # noqa: E402
import nerdpatch  # noqa: E402
import vfsource  # noqa: E402
from conftest import make_cff_font, make_font  # noqa: E402

# --- SCP feature tag remapping -------------------------------------------

@pytest.mark.parametrize("tag, want", [
    ("zero", "zero"),
    ("salt", "salt"),
    ("cv01", "cv01"),
    ("cv17", "cv17"),
    ("ss01", "ss11"),
    ("ss02", "ss12"),
    ("ss07", "ss17"),
    ("liga", None),
    ("calt", None),
    ("kern", None),
    ("ss10", "ss20"),   # ss01-ss10 all shift by +10
    ("ss11", "ss11"),   # ss11+ is already in our own numbering: unchanged
    ("ss17", "ss17"),
    ("ssxx", None),     # not a digit suffix
    ("case", None),
    ("frac", None),
])
def test_remap_scp_tag(tag, want):
    assert build._remap_scp_tag(tag) == want


def test_group_names_all_remap_nontrivially():
    """Invariant behind the explicit GROUP_NAMES skip in
    import_scp_variants: every tag we author ourselves (GROUP_NAMES) is
    exactly the shape _remap_scp_tag maps ssNN -> ss(NN+10) for (or, for
    cv99, passes through unchanged) — none of them come back None. So if
    an SCP font happened to carry a feature under one of our own tags
    (ss01-ss08, cv99), _remap_scp_tag alone would NOT filter it out: it
    would be remapped/kept just like any other SCP feature and collide
    with the glyph variants Gengou itself authors under that tag. That
    is exactly why import_scp_variants must skip fr.FeatureTag in
    GROUP_NAMES explicitly, before ever calling _remap_scp_tag."""
    for tag in build.GROUP_NAMES:
        assert build._remap_scp_tag(tag) is not None, tag


# --- Latin donor face paths (LATIN_FAMILY) --------------------------------

def test_latin_face_path_regular_upright():
    got = build.latin_face_path("dist/latin", "Regular", False)
    assert got == Path("dist/latin") / "Gengou-Regular.otf"


def test_latin_face_path_bold_italic():
    got = build.latin_face_path("dist/latin", "Bold", True)
    assert got == Path("dist/latin") / "Gengou-BoldItalic.otf"


# --- the weight roster ----------------------------------------------------

def test_faces_are_source_code_pro_named_instances_with_a_partner_each():
    assert [w for w, _ in build.FACES] == list(build.WEIGHT_CLASS)
    assert list(build.WEIGHT_CLASS.values()) == [300, 400, 500, 600, 700]
    assert all(f.startswith("SourceHanSansJP-") and f.endswith(".otf")
               for _, f in build.FACES)


# --- CID allocation ------------------------------------------------------

class DummyFont:
    """Just enough of TTFont for alloc_glyph_name."""

    def __init__(self, order):
        self._order = list(order)

    def getGlyphOrder(self):
        return self._order


def test_alloc_starts_above_adobe_japan1():
    f = DummyFont([".notdef", "cid00001", "cid00500"])
    assert build.alloc_glyph_name(f) == f"cid{build.CID_ALLOC_START:05d}"


def test_alloc_walks_gaps_and_is_unique():
    start = build.CID_ALLOC_START
    used = [f"cid{n:05d}" for n in (start, start + 1, start + 3)]
    f = DummyFont(used)
    got = [build.alloc_glyph_name(f) for _ in range(3)]
    assert got == [f"cid{start + 2:05d}", f"cid{start + 4:05d}",
                   f"cid{start + 5:05d}"]
    assert len(set(got)) == 3


def test_alloc_never_reuses_low_cids():
    f = DummyFont(["cid%05d" % n for n in range(1, 100)])
    for _ in range(50):
        assert int(build.alloc_glyph_name(f)[3:]) >= build.CID_ALLOC_START


# --- command-line face filter -------------------------------------------

@pytest.mark.parametrize("only, weight, label, suffix, want", [
    (None, "Light", "Light", "", True),
    ("Light", "Light", "Light", "", True),
    ("Light", "Light", "Light Italic", "", True),
    ("Light", "ExtraLight", "ExtraLight", "", False),        # was a bug
    ("Light", "ExtraLight", "ExtraLight Italic", "", False),
    ("Regular", "Regular", "Regular", "", True),
    ("Regular", "Regular", "Regular Italic", "", True),
    ("Regular Italic", "Regular", "Regular Italic", "", True),
    ("Regular Italic", "Regular", "Regular", "", False),
    ("Term", "Bold", "Bold", "Term", True),
    ("Term", "Bold", "Bold", "", False),
    ("", "Bold", "Bold", "", True),          # "" selects the base family
    ("", "Bold", "Bold", "Term", False),
    ("Light Upright", "Light", "Light", "", True),
    ("Light Upright", "Light", "Light Italic", "", False),
    ("Light Upright", "Light", "Light", "Term", True),   # every family
    ("Light Upright Term", "Light", "Light", "Term", True),
    ("Light Upright Term", "Light", "Light", "", False),
    ("Term Regular Italic", "Regular", "Regular Italic", "Term", True),
    ("Upright", "Bold", "Bold", "Term", True),
    ("Upright", "Bold", "Bold Italic", "Term", False),
    ("Regular Upright base", "Regular", "Regular", "", True),
    ("Regular Upright base", "Regular", "Regular", "Term", False),
    ("SemiBold", "SemiBold", "SemiBold Italic", "", True),
    ("Semibold", "Bold", "Bold", "", False),  # not a weight, suffix or style
    ("Regular Term Extra", "Regular", "Regular", "Term", True),   # "Extra": a variant nobody has
    ("Regular Extra", "Regular", "Regular", "Term", False),
    ("Light Regular base", "Regular", "Regular Italic", "", True),   # either weight
    ("Light Regular base", "Medium", "Medium", "", False),
    ("Light Regular Term base", "Light", "Light", "Term", True),    # either variant
    ("Light Regular Term base", "Light", "Light", "", True),
    ("Light Regular Term", "Light", "Light", "", False),
    ("Upright Italic Bold", "Bold", "Bold Italic", "Term", True),
])
def test_face_matches(only, weight, label, suffix, want):
    assert build.face_matches(only, weight, label, suffix) is want


# --- data/mona_ligs.json schema -----------------------------------------

KNOWN_GROUPS = {f"ss{n:02d}" for n in range(1, 9)}


def test_ligature_schema():
    ligs = build.load_ligatures()
    assert ligs, "no ligatures loaded"
    for seq, spec in ligs.items():
        assert isinstance(seq, str) and seq, f"bad key {seq!r}"
        assert {"cells", "glyphs", "group"} <= set(spec) <= {
            "cells", "glyphs", "group", "at"}, seq
        assert spec["glyphs"], f"{seq}: empty glyph list"
        assert all(isinstance(g, str) and g for g in spec["glyphs"]), seq
        assert spec["group"] in KNOWN_GROUPS, f"{seq}: group {spec['group']}"
        assert 2 <= spec["cells"] <= 4, f"{seq}: cells {spec['cells']}"
        # one cell per input character, and never fewer cells than parts
        assert spec["cells"] == len(seq), f"{seq}: cells != len(sequence)"
        assert len(spec["glyphs"]) <= spec["cells"], seq
        if "at" in spec:   # explicit cell per part: in range, ascending
            at = spec["at"]
            assert len(at) == len(spec["glyphs"]), seq
            assert all(0 <= c < spec["cells"] for c in at), seq
            assert at == sorted(at) and len(set(at)) == len(at), seq


def test_every_group_has_a_ui_name():
    groups = {spec["group"] for spec in build.load_ligatures().values()}
    assert groups <= set(build.GROUP_NAMES), "group without a UI name"
    # cv99 (the alternate designs) is authored too; no name goes unused
    assert set(build.GROUP_NAMES) == groups | {"cv99"}


def test_ui_names_are_nonempty_ascii():
    for tag, name in build.GROUP_NAMES.items():
        assert tag in KNOWN_GROUPS or tag.startswith("cv"), tag
        assert name and name.strip() == name, tag
        assert name.isascii(), tag


def test_feature_params_only_for_our_own_features():
    class Feat:
        FeatureParams = None

    class Rec:
        Feature = Feat()

    class GSUB:
        class FeatureList:
            FeatureRecord = [Rec()]

    # merged into an existing record (index None) -> untouched
    build._set_feature_params(None, GSUB, None, "ss01")
    assert GSUB.FeatureList.FeatureRecord[0].Feature.FeatureParams is None
    # a tag we do not author (e.g. SCP-remapped ss11) -> untouched
    build._set_feature_params(None, GSUB, 0, "ss11")
    assert GSUB.FeatureList.FeatureRecord[0].Feature.FeatureParams is None


# --- GSUB feature-list plumbing (_add_feature / sort_feature_list) ------

class FakeFeature:
    def __init__(self, lookup_indices):
        self.LookupListIndex = list(lookup_indices)
        self.LookupCount = len(self.LookupListIndex)
        self.FeatureParams = None


class FakeFeatureRecord:
    def __init__(self, tag, feature):
        self.FeatureTag = tag
        self.Feature = feature


class FakeFeatureList:
    def __init__(self, records):
        self.FeatureRecord = list(records)
        self.FeatureCount = len(self.FeatureRecord)


class FakeLangSys:
    def __init__(self, feature_index):
        self.FeatureIndex = list(feature_index)
        self.FeatureCount = len(self.FeatureIndex)


class FakeScript:
    def __init__(self, default_langsys, langsys_records=()):
        self.DefaultLangSys = default_langsys
        self.LangSysRecord = list(langsys_records)


class FakeScriptRecord:
    def __init__(self, script):
        self.Script = script


class FakeScriptList:
    def __init__(self, script_records):
        self.ScriptRecord = list(script_records)


class FakeGSUB:
    def __init__(self, feature_records, script_records):
        self.FeatureList = FakeFeatureList(feature_records)
        self.ScriptList = FakeScriptList(script_records)


def test_add_feature_merges_into_every_langsys_and_creates_for_the_rest():
    liga = FakeFeatureRecord("liga", FakeFeature([1, 2]))
    gsub = FakeGSUB([liga], [])

    has_liga = FakeLangSys([0])       # already lists the 'liga' record
    lacks_liga = FakeLangSys([])      # has no 'liga' record at all
    script_a = FakeScript(has_liga)
    script_b = FakeScript(lacks_liga)
    gsub.ScriptList.ScriptRecord = [
        FakeScriptRecord(script_a), FakeScriptRecord(script_b)]

    new_index = build._add_feature(gsub, "liga", [7])

    # merged into the existing record reachable from every LangSys that had it
    assert liga.Feature.LookupListIndex == [1, 2, 7]
    assert liga.Feature.LookupCount == 3

    # a fresh record was appended for the LangSys lacking the tag
    assert new_index == 1
    new_record = gsub.FeatureList.FeatureRecord[1]
    assert new_record.FeatureTag == "liga"
    assert new_record.Feature.LookupListIndex == [7]

    # only the lacking LangSys got the new index wired in
    assert has_liga.FeatureIndex == [0]
    assert has_liga.FeatureCount == 1
    assert lacks_liga.FeatureIndex == [1]
    assert lacks_liga.FeatureCount == 1


def test_add_feature_dedups_lookups():
    liga = FakeFeatureRecord("liga", FakeFeature([7]))
    gsub = FakeGSUB([liga], [])
    ls = FakeLangSys([0])
    gsub.ScriptList.ScriptRecord = [FakeScriptRecord(FakeScript(ls))]

    first = build._add_feature(gsub, "liga", [7])
    assert first is None
    assert liga.Feature.LookupListIndex == [7]

    second = build._add_feature(gsub, "liga", [7])
    assert second is None
    assert liga.Feature.LookupListIndex == [7]


def test_sort_feature_list_remaps_langsys_indices():
    records = [FakeFeatureRecord(tag, FakeFeature([]))
               for tag in ("ss02", "calt", "liga")]
    ls = FakeLangSys([0, 2])   # ss02 (0) and liga (2), unsorted by tag
    gsub = FakeGSUB(records, [FakeScriptRecord(FakeScript(ls))])

    build.sort_feature_list(gsub)

    tags = [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord]
    assert tags == sorted(tags)
    kept = {gsub.FeatureList.FeatureRecord[i].FeatureTag
            for i in ls.FeatureIndex}
    assert kept == {"ss02", "liga"}
    assert ls.FeatureCount == 2


def test_ligature_module_constant_matches_loader():
    assert build.load_ligatures() == build.LIGATURES


# --- drop_features (pwid/palt removal) -----------------------------------

class FakeTable:
    """font["GSUB"] / font["GPOS"] stand-in: just carries `.table`."""
    def __init__(self, table):
        self.table = table


def test_drop_features_removes_from_langsys_and_remaps():
    records = [FakeFeatureRecord(tag, FakeFeature([]))
               for tag in ("calt", "pwid", "liga")]
    ls = FakeLangSys([0, 1, 2])   # calt, pwid, liga
    gsub = FakeGSUB(records, [FakeScriptRecord(FakeScript(ls))])
    font = {"GSUB": FakeTable(gsub)}

    build.drop_features(font, {"pwid"})

    tags = [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord]
    assert tags == ["calt", "liga"]
    assert gsub.FeatureList.FeatureCount == 2
    # old index 1 (pwid) is gone; old index 2 (liga) remaps to 1
    assert ls.FeatureIndex == [0, 1]
    assert ls.FeatureCount == 2


def test_drop_features_noop_when_tag_absent():
    records = [FakeFeatureRecord("calt", FakeFeature([]))]
    ls = FakeLangSys([0])
    gsub = FakeGSUB(records, [FakeScriptRecord(FakeScript(ls))])
    font = {"GSUB": FakeTable(gsub)}

    build.drop_features(font, {"pwid"})

    assert [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord] == ["calt"]
    assert ls.FeatureIndex == [0]


def test_drop_features_skips_tables_the_font_lacks():
    font = {"GSUB": FakeTable(FakeGSUB([], []))}
    build.drop_features(font, {"palt"})   # no "GPOS" key: must not raise


# --- recalc_codepage_range -------------------------------------------------

class FakeOS2:
    def __init__(self, ul_code_page_range1):
        self.ulCodePageRange1 = ul_code_page_range1


class FakeCmapFont:
    def __init__(self, cmap, ul_code_page_range1):
        self._cmap = cmap
        self._tables = {"OS/2": FakeOS2(ul_code_page_range1)}

    def getBestCmap(self):
        return self._cmap

    def __getitem__(self, key):
        return self._tables[key]


def test_recalc_codepage_range_sets_and_clears_sampled_bits():
    # only the Latin-1 sample is present in cmap
    cmap = {ord(c): "g" for c in "éàü"}
    # bit 1 (Latin 2) starts incorrectly set; bit 29 is an unrelated
    # inherited bit recalc_codepage_range must leave alone
    font = FakeCmapFont(cmap, ul_code_page_range1=(1 << 1) | (1 << 29))

    build.recalc_codepage_range(font)

    bits = font["OS/2"].ulCodePageRange1
    assert bits & (1 << 0)          # Latin 1 sample present -> set
    assert not bits & (1 << 1)      # Latin 2 sample absent -> cleared
    assert not bits & (1 << 2)      # Cyrillic absent
    assert not bits & (1 << 17)     # JIS absent
    assert bits & (1 << 29)         # untouched, non-sampled bit preserved


# --- per-contour bounds (the '=' bar probe) ------------------------------

def test_contour_boxes_reads_the_curve_not_its_control_points():
    """A cubic that bulges only slightly: the control points sit at
    y=100 but the curve itself never reaches beyond y=75; an open
    contour is a box too."""
    class Glyph:
        def draw(self, pen):
            pen.moveTo((0, 0))
            pen.curveTo((0, 100), (100, 100), (100, 0))
            pen.closePath()
            pen.moveTo((200, 0))
            pen.lineTo((210, 20))
            pen.endPath()
    boxes = build.contour_boxes({"g": Glyph()}, "g")
    assert len(boxes) == 2
    assert boxes[0][:3] == (0, 0, 100) and boxes[0][3] == pytest.approx(75.0)
    assert boxes[1] == (200, 0, 210, 20)


def test_contour_boxes_splits_all_off_curve_contours_with_no_movetos():
    """A TrueType contour with no on-curve point at all draws as a bare
    qCurveTo ending in None, with nothing recorded before it -- no
    moveTo to split on (611 of the Nerd Fonts symbols draw this way).
    Two such contours back to back, with no moveTo between them either,
    must still come out as two boxes: closePath/endPath is what has to
    do the splitting here, and without it these merge into one box
    covering both."""
    class Glyph:
        def draw(self, pen):
            pen.qCurveTo((0, 0), (100, 100), None)
            pen.closePath()
            pen.qCurveTo((300, 0), (400, 100), None)
            pen.closePath()
    boxes = build.contour_boxes({"g": Glyph()}, "g")
    assert len(boxes) == 2
    assert boxes[0] == (25.0, 25.0, 75.0, 75.0)
    assert boxes[1] == (325.0, 25.0, 375.0, 75.0)


# --- erosion for the Monaspace wght floor ---------------------------------

def test_erode_path_shrinks_every_side():
    import pathops
    bar = pathops.Path()
    pen = bar.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((100, 0))
    pen.lineTo((100, 30))
    pen.lineTo((0, 30))
    pen.closePath()
    out = vfsource.erode_path(bar, 5)
    assert tuple(round(v) for v in out.bounds) == (5, 5, 95, 25)


def test_mona_glyphset_only_erodes_when_floor_was_hit():
    class Mona:
        gs = {"equal": object()}
        erode = 0.0

        def getGlyphSet(self):
            return self.gs
    m = Mona()
    assert vfsource.mona_glyphset(m) is m.gs   # nothing to erode
    m.erode = 0.2
    assert vfsource.mona_glyphset(m) is m.gs   # below threshold
    m.erode = 6.0
    assert isinstance(vfsource.mona_glyphset(m), vfsource._ErodedGlyphSet)


# --- tiny TTF fixtures for the tests below --------------------------------

def _tt_font(glyph_order, cmap, widths, ascent=800, descent=-200):
    """conftest.make_font with this file's argument order (see there)."""
    return make_font(glyph_order, cmap, widths, ascent=ascent, descent=descent)


# --- _guard_subtables: the DirectWrite-safe context guards ---------------

def test_guard_subtables_structure():
    """Structural check on the chain-context guards + triggers.

    fontTools' ChainContextSubstBuilder picks whichever of Format 1/2/3
    compiles smallest; every guard/trigger built here uses a SINGLE glyph
    at each position (never a class), so Format 1 — one subtable, glyph-
    indexed rule lists keyed by first glyph — always compiles smaller than
    the naively-imagined "one Format 3 subtable per rule" and is what this
    actually returns. That is in fact a STRONGER version of the property
    the docstring cares about: a Format 1 rule's input can only ever match
    one exact glyph per position, so an input match trivially covers the
    whole ligature — precisely what DirectWrite needs.
    """
    glyph_order = [".notdef", "hyphen", "greater", "less", "equal",
                   "lig_hg", "lig_hhg", "lig_lh"]
    font = _tt_font(
        glyph_order,
        {ord("-"): "hyphen", ord(">"): "greater",
         ord("<"): "less", ord("="): "equal"},
        {g: 600 for g in glyph_order})

    ligatures = {
        ("hyphen", "greater"): "lig_hg",
        ("hyphen", "hyphen", "greater"): "lig_hhg",
        ("less", "hyphen"): "lig_lh",
    }

    subtables = build._guard_subtables(font, ligatures, 0)
    assert len(subtables) == 1
    st = subtables[0]
    assert st.Format == 1

    triggers = []
    for gi, ruleset in enumerate(st.ChainSubRuleSet):
        if ruleset is None:
            continue
        first = st.Coverage.glyphs[gi]
        seen_trigger = False
        for rule in ruleset.ChainSubRule:
            seq = (first,) + tuple(rule.Input)
            if rule.SubstLookupRecord:
                seen_trigger = True
                triggers.append((seq, rule.SubstLookupRecord))
            else:
                # (a) every guard for this first glyph precedes every
                # trigger for it — a guard that fires after a trigger
                # would never run (the trigger already matched first)
                assert not seen_trigger, f"guard {seq} follows a trigger"

    # (b) exactly one trigger per ligature, (c) each covers the WHOLE
    # ligature (see the Format-1 note above — trivially true here, since
    # `seq` above is built from exactly-one-glyph-per-position rules)
    trigger_seqs = [seq for seq, _ in triggers]
    assert len(trigger_seqs) == len(ligatures)
    assert set(trigger_seqs) == set(ligatures)

    # (d) triggers sharing a first glyph are tried longest input first
    by_first = {}
    for seq in trigger_seqs:
        by_first.setdefault(seq[0], []).append(seq)
    for group in by_first.values():
        assert group == sorted(group, key=len, reverse=True)

    # (e) each trigger calls lig_lookup (passed in as 0) at SequenceIndex 0
    for seq, slrs in triggers:
        assert len(slrs) == 1
        assert slrs[0].SequenceIndex == 0
        assert slrs[0].LookupListIndex == 0


# --- add_gsub -> real HarfBuzz shaping ------------------------------------

def _empty_gsub_table():
    """A GSUB with one 'DFLT' script, no features, no lookups — what
    add_gsub expects to find already in the font and build onto."""
    table = otTables.GSUB()
    table.Version = 0x00010000

    default_langsys = otTables.DefaultLangSys()
    default_langsys.LookupOrder = None
    default_langsys.ReqFeatureIndex = 0xFFFF
    default_langsys.FeatureIndex = []
    default_langsys.FeatureCount = 0

    script = otTables.Script()
    script.DefaultLangSys = default_langsys
    script.LangSysRecord = []

    script_record = otTables.ScriptRecord()
    script_record.ScriptTag = "DFLT"
    script_record.Script = script

    table.ScriptList = otTables.ScriptList()
    table.ScriptList.ScriptRecord = [script_record]

    table.FeatureList = otTables.FeatureList()
    table.FeatureList.FeatureRecord = []
    table.FeatureList.FeatureCount = 0

    table.LookupList = otTables.LookupList()
    table.LookupList.Lookup = []
    table.LookupList.LookupCount = 0
    return table


def _shape(font_bytes, text, features):
    face = hb.Face(hb.Blob(font_bytes))
    hbfont = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, features)
    return [info.codepoint for info in buf.glyph_infos]


@pytest.fixture
def gsub_font_bytes():
    """A tiny font with calt/liga/ss01/ss02 ligatures wired through
    add_gsub, saved to bytes for HarfBuzz to shape."""
    glyph_order = [".notdef", "hyphen", "greater", "less", "equal",
                   "lig_hg", "lig_hhg", "lig_lh", "lig_ge"]
    font = _tt_font(
        glyph_order,
        {ord("-"): "hyphen", ord(">"): "greater",
         ord("<"): "less", ord("="): "equal"},
        {g: 600 for g in glyph_order})
    font["GSUB"] = newTable("GSUB")
    font["GSUB"].table = _empty_gsub_table()

    # data/mona_ligs.json shape; "glyphs" (the Monaspace donor names) are
    # never read by add_gsub — only "group" is — so they're dummies here.
    ligatures = {
        "->": {"cells": 2, "glyphs": ["hg"], "group": "ss02"},
        "-->": {"cells": 3, "glyphs": ["hhg"], "group": "ss02"},
        "<-": {"cells": 2, "glyphs": ["lh"], "group": "ss02"},
        ">=": {"cells": 2, "glyphs": ["ge"], "group": "ss01"},
    }
    added = {"->": "lig_hg", "-->": "lig_hhg", "<-": "lig_lh", ">=": "lig_ge"}
    build.add_gsub(font, added, {}, ligatures, {}, {})

    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def test_add_gsub_shapes_every_ligature(gsub_font_bytes):
    features = {"calt": True, "liga": True}
    assert len(_shape(gsub_font_bytes, "->", features)) == 1
    assert len(_shape(gsub_font_bytes, "-->", features)) == 1
    assert len(_shape(gsub_font_bytes, "<-", features)) == 1
    assert len(_shape(gsub_font_bytes, ">=", features)) == 1


def test_add_gsub_guard_keeps_longer_run_plain(gsub_font_bytes):
    # '->>' is longer than any known ligature ('->' plus a trailing '>')
    # so the guard rules must keep all three glyphs unsubstituted
    features = {"calt": True, "liga": True}
    assert len(_shape(gsub_font_bytes, "->>", features)) == 3
    # '<->' is not itself a ligature in this reduced set. The guard that
    # normally protects '<->'-shaped input (so a real '<->' ligature can
    # win) fires even though no '<->' ligature exists here to claim it —
    # so '<-' does NOT fire either, and the whole run stays plain (verified
    # against real HarfBuzz output, not assumed).
    assert len(_shape(gsub_font_bytes, "<->", features)) == 3


def _shift_font_bytes():
    """The real font's '>' family in miniature: '>=', '>>' and '>>=' are
    ligatures, '>>>' and '>>>=' are not."""
    glyph_order = [".notdef", "greater", "equal", "lig_ge", "lig_gg", "lig_gge"]
    font = _tt_font(glyph_order, {ord(">"): "greater", ord("="): "equal"},
                    {g: 600 for g in glyph_order})
    font["GSUB"] = newTable("GSUB")
    font["GSUB"].table = _empty_gsub_table()
    ligatures = {">=": {"cells": 2, "glyphs": ["ge"], "group": "ss01"},
                 ">>": {"cells": 2, "glyphs": ["gg"], "group": "ss01"},
                 ">>=": {"cells": 3, "glyphs": ["gge"], "group": "ss01"}}
    added = {">=": "lig_ge", ">>": "lig_gg", ">>=": "lig_gge"}
    build.add_gsub(font, added, {}, ligatures, {}, {})
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def test_add_gsub_guard_holds_when_the_longer_ligature_is_itself_blocked():
    """'>>>=' shaped as '>' '>' '≥': the '>>' guard consumed the first two
    glyphs, so the '>>=' that was supposed to claim them never matched,
    and '>=' was left unguarded because that '>>=' existed. A guard with
    a backtrack is safe unconditionally — the longer ligature's own
    trigger matches at the earlier position and consumes the run first."""
    b = _shift_font_bytes()
    on = {"calt": True, "liga": True}
    assert len(_shape(b, ">=", on)) == 1        # still ligatures
    assert len(_shape(b, ">>", on)) == 1
    assert len(_shape(b, ">>=", on)) == 1
    assert len(_shape(b, ">>>=", on)) == 4      # the leak
    assert len(_shape(b, ">>>", on)) == 3
    assert len(_shape(b, "a >>= b", on)) == 5


def test_guard_subtables_keep_the_skip_only_for_lookahead_guards():
    """A guard whose backtrack is empty starts where the longer ligature
    starts, and every guard is tried before every trigger, so it would
    pre-empt it — '===' shaped as three plain glyphs the moment '==' was
    guarded against a following '='. Those keep the skip; the backtrack
    ones do not."""
    glyph_order = [".notdef", "greater", "equal", "lig_ge", "lig_gg",
                   "lig_gge", "lig_ee", "lig_eee"]
    font = _tt_font(glyph_order, {ord(">"): "greater", ord("="): "equal"},
                    {g: 600 for g in glyph_order})
    subtables = build._guard_subtables(font, {
        ("greater", "equal"): "lig_ge", ("greater", "greater"): "lig_gg",
        ("greater", "greater", "equal"): "lig_gge",
        ("equal", "equal"): "lig_ee",
        ("equal", "equal", "equal"): "lig_eee"}, 0)
    st = subtables[0]
    guards = set()
    for gi, ruleset in enumerate(st.ChainSubRuleSet):
        if ruleset is None:
            continue
        first = st.Coverage.glyphs[gi]
        for rule in ruleset.ChainSubRule:
            if not rule.SubstLookupRecord:
                guards.add((tuple(rule.Backtrack), (first,) + tuple(rule.Input),
                            tuple(rule.LookAhead)))
    # '>>=' is a ligature, and '>=' is guarded after a '>' all the same
    assert (("greater",), ("greater", "equal"), ()) in guards
    # '===' is a ligature, so '==' is NOT guarded before a '='
    assert ((), ("equal", "equal"), ("equal",)) not in guards
    # ... but it is guarded after one
    assert (("equal",), ("equal", "equal"), ()) in guards


def test_add_gsub_calt_liga_off_leaves_ligatures_plain(gsub_font_bytes):
    assert len(_shape(gsub_font_bytes, "->",
                      {"calt": False, "liga": False})) == 2


def test_add_gsub_stylistic_set_is_group_scoped(gsub_font_bytes):
    # NOTE: HarfBuzz enables 'liga' by default even when it's absent from
    # the features dict — only an explicit "liga": False turns it off. The
    # guarded combined lookup (every group) is registered under 'liga' too,
    # so without disabling it, ">=" (ss01) would still ligate through
    # 'liga' regardless of ss02 below, silently defeating this test.
    features = {"calt": False, "liga": False, "ss02": True}
    assert len(_shape(gsub_font_bytes, "->", features)) == 1    # ss02: on
    assert len(_shape(gsub_font_bytes, ">=", features)) == 2    # ss01: off


# --- set_monospace_metadata -----------------------------------------------

def test_set_monospace_metadata():
    glyph_order = [".notdef", "space", "a", "b", "c"]
    widths = {"space": 0, "a": 500, "b": 700, "c": 350}   # space is 0-width
    font = _tt_font(glyph_order, {ord(" "): "space", ord("a"): "a",
                                  ord("b"): "b", ord("c"): "c"}, widths)

    build.set_monospace_metadata(font)

    assert font["post"].isFixedPitch == 1
    assert font["OS/2"].panose.bProportion == 9
    # mean of the non-zero advances, rounded the way OS/2 v3+ (and
    # recalcAvgCharWidth) define xAvgCharWidth — zero-width glyphs excluded
    nonzero = [w for w in widths.values() if w > 0]
    assert font["OS/2"].xAvgCharWidth == otRound(sum(nonzero) / len(nonzero))


# --- add_stat ---------------------------------------------------------------

@pytest.mark.parametrize("weight, italic, want_wght, want_ital", [
    ("Regular", False, 400, 0),
    ("Bold", True, 700, 1),
    ("Light", False, 300, 0),
])
def test_add_stat_is_one_value_per_axis(weight, italic, want_wght, want_ital):
    # a static face lists only its own location; the whole family's values
    # in every file trip Windows' family model (fontbakery STAT_in_statics)
    font = _tt_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600})

    build.add_stat(font, weight, italic)

    assert "STAT" in font
    stat = font["STAT"].table
    assert [a.AxisTag for a in stat.DesignAxisRecord.Axis] == ["wght", "ital"]
    axis_values = stat.AxisValueArray.AxisValue
    wght_values = [v for v in axis_values if v.AxisIndex == 0]
    ital_values = [v for v in axis_values if v.AxisIndex == 1]
    assert [v.Value for v in wght_values] == [want_wght]
    assert [v.Value for v in ital_values] == [want_ital]
    # Regular links to Bold, upright to Italic, both elidable (Format 3)
    if weight == "Regular":
        assert wght_values[0].Flags & 0x2
        assert wght_values[0].LinkedValue == build.WEIGHT_CLASS["Bold"]
    else:
        assert wght_values[0].Format == 1
    if italic:
        assert ital_values[0].Format == 1
    else:
        assert ital_values[0].Flags & 0x2
        assert ital_values[0].LinkedValue == 1


# --- classify_marks ---------------------------------------------------------

class FakeGlyphClassDefTable:
    def __init__(self):
        self.GlyphClassDef = None


def test_classify_marks_creates_classdef_for_grafted_marks():
    gdef_table = FakeGlyphClassDefTable()
    font = {"GDEF": FakeTable(gdef_table)}

    build.classify_marks(font, {"mark1", "mark2"})

    assert gdef_table.GlyphClassDef is not None
    assert gdef_table.GlyphClassDef.classDefs == {"mark1": 3, "mark2": 3}


def test_classify_marks_without_gdef_does_not_raise():
    build.classify_marks({}, {"mark1"})   # no "GDEF" key at all


def test_classify_marks_empty_marks_is_noop():
    gdef_table = FakeGlyphClassDefTable()
    font = {"GDEF": FakeTable(gdef_table)}

    build.classify_marks(font, set())

    assert gdef_table.GlyphClassDef is None


# --- set_names ---------------------------------------------------------

def _cff_font():
    glyph_order = [".notdef", "A"]
    charstrings = {}
    for g in glyph_order:
        pen = T2CharStringPen(0, None)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.closePath()
        charstrings[g] = pen.getCharString()

    return make_cff_font(glyph_order, charstrings, {ord("A"): "A"},
                         {".notdef": (0, 0), "A": (600, 0)}, ps="TestPS",
                         font_info={"FullName": "Test Full", "FamilyName": "Test Family"},
                         family="Test", style="Regular")


def _cff_font_with_widths(widths, x0=0):
    """A CID-less CFF font whose glyphs are 100-unit squares at the given
    advances, drawn from x0: what fit_to_grid moves. A square at x0=0
    touches its left edge, which widen_fullwidth reads as "drawn to tile
    there"; tests of that pass give their glyphs a bearing."""
    glyph_order = [".notdef", *widths]
    charstrings = {}
    for g in glyph_order:
        pen = T2CharStringPen(0, None)
        pen.moveTo((x0, 0))
        pen.lineTo((x0 + 100, 0))
        pen.lineTo((x0 + 100, 100))
        pen.closePath()
        charstrings[g] = pen.getCharString()
    return make_cff_font(glyph_order, charstrings,
                         {0xE000 + i: g for i, g in enumerate(widths)},
                         {".notdef": (0, 0), **{g: (w, x0) for g, w in widths.items()}})


def test_append_glyph_takes_the_donor_s_vertical_origin_not_its_bearing():
    """A top side bearing is measured DOWN from each glyph's own yMax, so
    copying the donor's verbatim moves the origin by the difference
    between the two. Every glyph the graft appended inherited U+FF61's
    637 against its own yMax of 243, and stood 250-570 units low in a
    vertical run under any shaper that reads vmtx rather than VORG."""
    font = _cff_font_with_widths({"donor": 600, "tall": 600})
    font["vmtx"] = newTable("vmtx")
    font["vmtx"].metrics = {".notdef": (1000, 0), "donor": (1000, 637),
                            "tall": (1000, 637)}
    # the donor is a 100-unit square, so its origin is 100 + 637
    pen = T2CharStringPen(600, None)
    pen.moveTo((0, 0))
    pen.lineTo((100, 0))
    pen.lineTo((100, 400))
    pen.closePath()
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    build.append_glyph(font, td, "new", pen.getCharString(private=td.Private),
                       None, 600, None, "donor")
    assert font["vmtx"].metrics["new"] == (1000, 737 - 400)
    assert font["vmtx"].metrics["donor"] == (1000, 637)      # untouched
    assert font["hmtx"].metrics["new"] == (600, 0)


@pytest.mark.parametrize("us_weight, want", [(300, 4), (400, 5), (500, 6),
                                             (600, 7), (700, 8)])
def test_panose_weight_matches_source_han_sans_own_mapping(us_weight, want):
    assert build.panose_weight(us_weight) == want


@pytest.mark.parametrize("adv, ink, want", [
    (500, 400, 600),      # half-width kana: under the cell
    (500, 1400, 2000),    # ...unless its ink is nowhere near one cell
    (250, 100, 600),      # a Hangul tone mark
    (618, 548, 600),      # Source Han Sans's alpha: nearest the cell
    (663, 612, 600),      # its Bold alpha, ink a little over the cell
    (795, 687, 600),      # its Phi, still nearest the cell
    (920, 700, 1000),     # a Hangul jamo: nearest one full width
    (1005, 844, 1000),    # its Yu: a full width and a bit, not two
    (1672, 1600, 2000),
    (2452, 2400, 3000),   # a three-em dash: the ink needs the third
    (700, 1400, 2000),    # ink far past the step: up it goes
])
def test_grid_step_takes_the_nearest_step_the_ink_fits(adv, ink, want):
    assert build.grid_step(adv, ink, 600) == want


def test_fit_to_grid_centres_proportional_advances_on_the_grid():
    """Half-width kana at 500 -> the cell; Hangul jamo at 920 -> one full
    width; an advance of 2459 -> the nearest two (these fixtures are
    100-unit squares, so no ink pushes it to three, as the real three-em
    dash's does); a mark at 0, a cell, a full width and a ligature
    (2 cells) are left alone."""
    font = _cff_font_with_widths({"kana": 500, "jamo": 920, "dash": 2459,
                                  "mark": 0, "cell": 600, "full": 1000, "lig": 1200})
    assert build.fit_to_grid(font, 600) == 3
    hmtx = font["hmtx"].metrics
    assert {g: hmtx[g][0] for g in ("kana", "jamo", "dash", "mark", "cell", "full", "lig")} == \
        {"kana": 600, "jamo": 1000, "dash": 2000, "mark": 0, "cell": 600,
         "full": 1000, "lig": 1200}
    gs = font.getGlyphSet()
    for g, want_lsb in (("kana", 50), ("jamo", 40), ("dash", -230)):
        pen = BoundsPen(gs)
        gs[g].draw(pen)
        assert pen.bounds[0] == want_lsb == hmtx[g][1]     # centred, lsb kept in step
    assert build.state_of(font).redrawn == {"kana", "jamo", "dash"}


def _path(points):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(points[0])
    for pt in points[1:]:
        pen.lineTo(pt)
    pen.closePath()
    return path


def test_edge_is_rule_tells_a_rule_from_a_diagonal_and_a_pattern():
    """A rule, a cross and a tee present the same cross-section at the
    edge as 10 units in; a diagonal, a wave and a dot pattern do not.
    Extruding the edge of the latter puts a flat bar at every join."""
    rule = _path([(0, 360), (1000, 360), (1000, 400), (0, 400)])
    assert build.edge_is_rule(rule, "left") and build.edge_is_rule(rule, "right")
    cross = pathops.op(rule, _path([(480, -120), (520, -120), (520, 880), (480, 880)]),
                       pathops.PathOp.UNION)
    assert build.edge_is_rule(cross, "left") and build.edge_is_rule(cross, "right")
    corner = pathops.op(_path([(480, 360), (1000, 360), (1000, 400), (480, 400)]),
                        _path([(480, -120), (520, -120), (520, 400), (480, 400)]),
                        pathops.PathOp.UNION)
    assert build.edge_is_rule(corner, "right")          # the arm reaches it
    diagonal = _path([(0, 0), (40, 0), (1000, 960), (960, 1000), (0, 40)])
    assert not build.edge_is_rule(diagonal, "left")
    assert not build.edge_is_rule(diagonal, "right")
    saltire = pathops.op(diagonal, _path([(0, 1000), (0, 960), (960, 0), (1000, 0), (40, 1000)]),
                         pathops.PathOp.UNION)
    assert not build.edge_is_rule(saltire, "left")      # same extents, not a rule
    dots = pathops.Path()              # 8u dots on a 20u grid, like ▒
    pen = dots.getPen()
    for x in range(0, 1000, 20):
        for y in range(0, 1000, 20):
            pen.moveTo((x, y))
            pen.lineTo((x + 8, y))
            pen.lineTo((x + 8, y + 8))
            pen.lineTo((x, y + 8))
            pen.closePath()
    assert not build.edge_is_rule(dots, "left")


def test_widen_fullwidth_stretches_a_pattern_and_extrudes_a_rule():
    """A diagonal drawn edge to edge is stretched whole, so the ends of a
    run of ╳ keep their slope instead of growing a flat tick."""
    font = _cff_font_with_widths({"diag": 1000, "rule": 1000}, x0=20)
    font["cmap"].tables[0].cmap = {0x2571: "diag", 0x2500: "rule"}   # ╱ ─
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    for name, pts in (("diag", [(0, 0), (40, 0), (1000, 960), (960, 1000), (0, 40)]),
                      ("rule", [(0, 360), (1000, 360), (1000, 400), (0, 400)])):
        pen = T2CharStringPen(1000, None)
        pen.moveTo(pts[0])
        for pt in pts[1:]:
            pen.lineTo(pt)
        pen.closePath()
        td.CharStrings[name] = pen.getCharString(private=td.Private)
    build.widen_fullwidth(font, 600)
    gs = font.getGlyphSet()
    diag = pathops.Path()
    gs["diag"].draw(diag.getPen())
    # stretched: still a single slanted band, 1200 wide, no flat piece at
    # either end (the strip 0..100 is a parallelogram, ~80u tall, not 40)
    assert (round(diag.bounds[0]), round(diag.bounds[2])) == (0, 1200)
    strip = build._slab(diag, 0, 100).bounds
    assert strip[3] - strip[1] > 100
    rule = pathops.Path()
    gs["rule"].draw(rule.getPen())
    assert (round(rule.bounds[1]), round(rule.bounds[3])) == (360, 400)   # extruded, same thickness


def test_widen_fullwidth_lengthens_a_glyph_drawn_to_tile():
    """A glyph whose ink reaches both edges of its advance is drawn to
    tile (＿ ￣ 〰 ◢, and under fwid most of the box drawing). Centring it
    in the wider Term advance leaves white at every cell join, so a rule
    of ＿ comes out dashed and █ striped."""
    font = _cff_font_with_widths({"rule": 1000, "kanji": 1000}, x0=20)
    font["cmap"].tables[0].cmap = {0xFF3F: "rule", 0x4E00: "kanji"}    # ＿ 一
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    pen = T2CharStringPen(1000, None)          # a bar spanning the advance
    pen.moveTo((0, 40))
    pen.lineTo((1000, 40))
    pen.lineTo((1000, 100))
    pen.lineTo((0, 100))
    pen.closePath()
    td.CharStrings["rule"] = pen.getCharString(private=td.Private)
    build.widen_fullwidth(font, 600)
    hmtx = font["hmtx"].metrics
    assert hmtx["rule"][0] == hmtx["kanji"][0] == 1200
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()["rule"].draw(pen)
    x0, y0, x1, y1 = pen.bounds
    assert (round(x0), round(x1)) == (0, 1200)     # still edge to edge
    assert (round(y0), round(y1)) == (40, 100)     # and no thicker
    # the ordinary glyph is still centred, not stretched
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()["kanji"].draw(pen)
    assert round(pen.bounds[2] - pen.bounds[0]) == 100


def test_widen_fullwidth_centres_an_ordinary_glyph_that_touches_its_edge():
    """Ⅷ, ㌄ and 孰 in Bold have ink at their advance's edge and are not
    drawn to tile: an edge test alone stretched them 20% wide. Only a
    character in the tiling blocks is lengthened."""
    font = _cff_font_with_widths({"eight": 1000})
    font["cmap"].tables[0].cmap = {0x2167: "eight"}                    # Ⅷ, ink from x=0
    build.widen_fullwidth(font, 600)
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()["eight"].draw(pen)
    assert (round(pen.bounds[0]), round(pen.bounds[2])) == (100, 200)  # moved, not stretched


def test_widen_fullwidth_stretches_a_block_element_to_its_fraction():
    """▏ is an eighth of the cell; extruding its left edge as a rule made
    it 225 of 1200 where ▎ is 350, so the ▏▎▍▌▋▊▉█ series stepped
    unevenly. A block element is stretched whole."""
    font = _cff_font_with_widths({"eighth": 1000})
    font["cmap"].tables[0].cmap = {0x258F: "eighth"}
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    pen = T2CharStringPen(1000, None)
    pen.moveTo((0, -120))
    pen.lineTo((125, -120))
    pen.lineTo((125, 880))
    pen.lineTo((0, 880))
    pen.closePath()
    td.CharStrings["eighth"] = pen.getCharString(private=td.Private)
    build.widen_fullwidth(font, 600)
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()["eighth"].draw(pen)
    assert (round(pen.bounds[0]), round(pen.bounds[2])) == (0, 150)


def test_widen_fullwidth_stretches_a_dashed_rule_whose_ink_stops_short():
    """┄'s end dashes are inset by half a gap so that cells continue the
    pattern; its ink never reaches the edge, and centring it in 1200
    made the gap at every cell boundary three times the gap inside."""
    font = _cff_font_with_widths({"dashed": 1000})
    font["cmap"].tables[0].cmap = {0x2504: "dashed"}
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    pen = T2CharStringPen(1000, None)          # three dashes, 55u in from each edge
    for x in (55, 385, 715):
        pen.moveTo((x, 360))
        pen.lineTo((x + 230, 360))
        pen.lineTo((x + 230, 400))
        pen.lineTo((x, 400))
        pen.closePath()
    td.CharStrings["dashed"] = pen.getCharString(private=td.Private)
    build.widen_fullwidth(font, 600)
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()["dashed"].draw(pen)
    assert (round(pen.bounds[0]), round(pen.bounds[2])) == (66, 1134)   # 55*1.2 .. 945*1.2


def test_widen_fullwidth_spares_the_ligatures_it_is_given():
    """Term: a full width goes to two cells, three full widths to six,
    but a named 5-cell ligature — 3000 too — stays on the cell grid; a
    cell and a mark are never touched."""
    font = _cff_font_with_widths({"full": 1000, "dash": 3000, "lig5": 3000,
                                  "cell": 600, "mark": 0}, x0=20)
    build.widen_fullwidth(font, 600, skip={"lig5"})
    hmtx = font["hmtx"].metrics
    assert {g: hmtx[g][0] for g in ("full", "dash", "lig5", "cell", "mark")} == \
        {"full": 1200, "dash": 3600, "lig5": 3000, "cell": 600, "mark": 0}
    gs = font.getGlyphSet()
    for g, want_lsb in (("full", 120), ("dash", 320), ("lig5", 20)):
        pen = BoundsPen(gs)
        gs[g].draw(pen)
        assert pen.bounds[0] == want_lsb == hmtx[g][1]


def test_notdef_to_cell_takes_the_donors_box_and_keeps_it():
    """Source Han Sans's .notdef is full width, and a terminal gives an
    uncovered codepoint one column, so the box pushed the rest of the
    line along -- 1200 units into a 600-unit cell in the Term faces.
    The donor's .notdef is drawn for the cell. It has to survive both
    grid passes afterwards, including a family step map that still
    carries the donor's full width for the name."""
    font = _cff_font_with_widths({"a": 602, "kanji": 1000})
    font["hmtx"].metrics[".notdef"] = (1000, 107)
    latin = _cff_font_with_widths({"x": 600})
    latin["hmtx"].metrics[".notdef"] = (600, 62)

    assert build.notdef_to_cell(font, latin, 600) is True
    assert font["hmtx"].metrics[".notdef"][0] == 600
    # the family's reference still says full width; the pin wins
    build.fit_to_grid(font, 600, steps={".notdef": 1000})
    assert font["hmtx"].metrics[".notdef"][0] == 600
    # and the Term pass only widens a full-width advance
    build.widen_fullwidth(font, 600)
    assert font["hmtx"].metrics[".notdef"][0] == 600
    assert font["hmtx"].metrics["kanji"][0] == 1200      # this one does


def test_notdef_to_cell_leaves_a_donor_without_one_alone():
    font = _cff_font_with_widths({"a": 602})
    font["hmtx"].metrics[".notdef"] = (1000, 107)
    latin = _cff_font_with_widths({"x": 600})
    latin.setGlyphOrder([g for g in latin.getGlyphOrder() if g != ".notdef"])
    assert build.notdef_to_cell(font, latin, 600) is False
    assert font["hmtx"].metrics[".notdef"][0] == 1000


def test_narrow_halfwidth_leaves_the_latin_donors_glyph_alone():
    """The won sign is Halfwidth and came from the Latin donor a cell
    wide; at Bold Italic its ink is 605 wide, and judged on ink width
    alone this pass condensed it to zero side bearings at that one
    weight while every other weight and the Latin face kept the glyph
    as drawn. A glyph the donor supplied is its own."""
    font = _cff_font_with_widths({"won": 600, "jamo": 920}, x0=0)
    # ink wider than the cell on both: 'won' is the donor's, 'jamo' is not
    for g in ("won", "jamo"):
        pen = T2CharStringPen(0, None)
        pen.moveTo((-3, 0))
        pen.lineTo((605, 0))
        pen.lineTo((605, 500))
        pen.closePath()
        td = font["CFF "].cff.topDictIndex[0]
        td.CharStrings[g] = pen.getCharString(private=td.Private)
    font["cmap"].tables[0].cmap = {0x20A9: "won", 0xFFA1: "jamo"}
    build.state_of(font).built = {"won"}
    assert build.narrow_halfwidth(font, 600) == 1
    assert font.getBestCmap()[0x20A9] == "won"        # untouched
    assert font.getBestCmap()[0xFFA1] != "jamo"       # the jamo got its copy


def test_narrow_halfwidth_condenses_a_shared_glyph_into_the_cell():
    """A Halfwidth codepoint whose glyph is the wide compatibility one
    gets its own copy, squeezed into the cell; the wide codepoint keeps
    the original, and the copy stays out of _appended so add_latin_fd
    leaves it in the FontDict it came from."""
    font = _cff_font_with_widths({"jamo": 920, "kana": 600, "wide": 1000})
    # U+3131 (Wide) and U+FFA1 (Halfwidth) on one glyph, ｱ already a cell
    font["cmap"].tables[0].cmap = {0x3131: "jamo", 0xFFA1: "jamo",
                                   0xFF71: "kana", 0x4E00: "wide"}
    assert build.narrow_halfwidth(font, 600) == 1
    cmap, hmtx = font.getBestCmap(), font["hmtx"].metrics
    assert cmap[0x3131] == "jamo" and hmtx["jamo"][0] == 920      # untouched
    copy = cmap[0xFFA1]
    assert copy != "jamo" and hmtx[copy][0] == 600
    assert copy not in build.state_of(font).appended            # keeps its own FontDict
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[copy].draw(pen)
    assert pen.bounds[2] - pen.bounds[0] == pytest.approx(100 * 600 / 920, abs=1)


def test_narrow_halfwidth_copies_are_out_of_reach_of_the_reference_steps():
    """The copy's name comes from Source Han Sans's own CID space, where
    the reference font it is looked up in has 10,000 glyphs of its own —
    a name collision would re-advance a half-width form to whatever that
    reference glyph measures. It opts out of the Latin FontDict, not out
    of being ours, so fit_to_grid still takes the fallback path for it."""
    font = _cff_font_with_widths({"jamo": 920})
    font["cmap"].tables[0].cmap = {0x3131: "jamo", 0xFFA1: "jamo"}
    assert build.narrow_halfwidth(font, 600) == 1
    copy = font.getBestCmap()[0xFFA1]
    assert copy in build.state_of(font).built and copy not in build.state_of(font).appended
    # a reference that claims this very name is a full width
    assert build.fit_to_grid(font, 600, steps={copy: 1000, "jamo": 1000}) == 1
    assert font["hmtx"].metrics[copy][0] == 600        # still one cell
    assert font["hmtx"].metrics["jamo"][0] == 1000     # the reference did apply


def test_narrow_halfwidth_never_widens_a_glyph_that_already_fits():
    """Source Han Sans's half-width kana and punctuation are 500 wide —
    inside the cell, so there is nothing to condense. Scaling them by
    cell/advance would stretch every vertical stroke 20% against
    untouched horizontals; fit_to_grid centres them at 600 instead."""
    font = _cff_font_with_widths({"kana": 500, "sym": 500})
    font["cmap"].tables[0].cmap = {0xFF71: "kana", 0xFFE9: "sym"}
    def box():
        pen = BoundsPen(font.getGlyphSet())
        font.getGlyphSet()["kana"].draw(pen)
        return pen.bounds

    before = box()
    assert build.narrow_halfwidth(font, 600) == 0
    assert font.getBestCmap()[0xFF71] == "kana"
    assert font["hmtx"].metrics["kana"] == (500, before[0])   # left for fit_to_grid
    assert box() == before


def test_narrow_halfwidth_leaves_a_blank_glyph_alone():
    """A Halfwidth codepoint drawn as a 0-advance combining mark has no
    advance to scale by."""
    font = _cff_font_with_widths({"mark": 0})
    font["cmap"].tables[0].cmap = {0xFF9E: "mark"}
    assert build.narrow_halfwidth(font, 600) == 0


def test_remap_required_moves_a_required_feature_and_keeps_its_none():
    """ReqFeatureIndex points into the same FeatureList the remap
    renumbers; 0xFFFF is 'none' and must stay put."""
    class LangSys:
        pass

    ls = LangSys()
    ls.ReqFeatureIndex = 5
    build.remap_required(ls, {5: 2})
    assert ls.ReqFeatureIndex == 2
    build.remap_required(ls, {})            # the required feature was dropped
    assert ls.ReqFeatureIndex == 0xFFFF
    build.remap_required(ls, {0: 0})        # already none: left alone
    assert ls.ReqFeatureIndex == 0xFFFF
    build.remap_required(LangSys(), {0: 1})  # no attribute at all


def test_shift_anchors_moves_a_base_anchor_with_its_outline():
    """An anchor is a point on the glyph: re-centring the outline in a
    wider advance has to take it along, or the mark lands where the ink
    used to be (Source Han Sans's Bopomofo tone marks)."""
    from fontTools.ttLib.tables import otTables

    def anchor(x):
        a = otTables.Anchor()
        a.Format, a.XCoordinate, a.YCoordinate = 1, x, 0
        return a

    sub = otTables.MarkBasePos()
    sub.MarkCoverage = otTables.MarkCoverage()
    sub.MarkCoverage.glyphs = ["mark"]
    sub.MarkArray = otTables.MarkArray()
    rec = otTables.MarkRecord()
    rec.Class, rec.MarkAnchor = 0, anchor(10)
    sub.MarkArray.MarkRecord = [rec]
    sub.BaseCoverage = otTables.BaseCoverage()
    sub.BaseCoverage.glyphs = ["base", "still"]
    sub.BaseArray = otTables.BaseArray()
    base, still = otTables.BaseRecord(), otTables.BaseRecord()
    base.BaseAnchor, still.BaseAnchor = [anchor(640)], [anchor(500)]
    sub.BaseArray.BaseRecord = [base, still]
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.SubTable = 4, [sub]

    font = _cff_font_with_widths({"a": 600})
    gpos = newTable("GPOS")
    gpos.table = otTables.GPOS()
    gpos.table.LookupList = otTables.LookupList()
    gpos.table.LookupList.Lookup = [lookup]
    font["GPOS"] = gpos

    assert build.shift_anchors(font, {"base": 100, "mark": -5}) == 2
    assert base.BaseAnchor[0].XCoordinate == 740
    assert rec.MarkAnchor.XCoordinate == 5
    assert still.BaseAnchor[0].XCoordinate == 500      # not shifted, not moved
    assert build.shift_anchors(font, {}) == 0

    # and through GPOS's own Extension, which is type 9 (GSUB's is 7)
    ext = otTables.ExtensionPos()
    ext.Format, ext.ExtSubTable = 1, sub
    wrapper = otTables.Lookup()
    wrapper.LookupType, wrapper.SubTable = 9, [ext]
    gpos.table.LookupList.Lookup = [wrapper]
    assert build.shift_anchors(font, {"base": 60}) == 1
    assert base.BaseAnchor[0].XCoordinate == 800


def test_restore_cid_count_covers_the_highest_cid(tmp_path):
    """cffsubr sets CIDCount from the last charset entry; Source Han
    Sans's CID space is sparse, so the glyphs this build appends sit at
    the end of the order with lower CIDs than the Japanese ones."""
    font = _cff_font_with_widths({"a": 600})
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    td.ROS = ("Adobe", "Japan1", 6)           # what makes a CFF CID-keyed
    td.charset = [".notdef", "cid65497", "cid23058"]
    td.CIDCount = 23059                       # what cffsubr would leave
    assert build.restore_cid_count(font) == 65498
    td.CIDCount = 70000                       # never narrowed
    assert build.restore_cid_count(font) == 70000


def test_restore_cid_count_leaves_a_plain_cff_alone():
    """A plain CFF has a CIDCount attribute too (the spec default), so
    the CID-keyed test is ROS."""
    assert build.restore_cid_count(_cff_font_with_widths({"a": 600})) is None


def test_widen_fullwidth_redraws_a_charstring_shift_declines(monkeypatch):
    """shift_charstring declines a program it does not understand and the
    glyph is redrawn instead — on a plain CFF as well as a CID-keyed one."""
    font = _cff_font_with_widths({"full": 1000}, x0=20)
    monkeypatch.setattr(build, "shift_charstring", lambda *a, **k: False)
    build.widen_fullwidth(font, 600)
    assert font["hmtx"].metrics["full"][0] == 1200
    assert build.state_of(font).redrawn == {"full"}
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()["full"].draw(pen)
    assert pen.bounds[0] == 120                      # centred in the new advance


def test_fit_to_grid_follows_the_reference_steps_over_this_face():
    """The family decides a glyph's width once, on one weight
    (reference_steps): a heavier face whose own advance would round the
    other way follows it, and a glyph the reference does not name falls
    back to this face's advance."""
    font = _cff_font_with_widths({"phi": 824, "psi": 900})
    assert build.fit_to_grid(font, 600, steps={"phi": 600}) == 2
    hmtx = font["hmtx"].metrics
    assert hmtx["phi"][0] == 600                # the reference's answer
    assert hmtx["psi"][0] == 1000               # its own: nearest a full width


def test_fit_to_grid_reaches_a_glyph_no_codepoint_does():
    """'locl' and 'ccmp' put glyphs on the page without being asked, so
    the pass walks the whole font, not the cmap."""
    font = _cff_font_with_widths({"a": 500})
    order = list(font.getGlyphOrder())
    font["hmtx"].metrics["hidden"] = (1052, 0)   # a locl form, uncmap'd
    font.setGlyphOrder(order + ["hidden"])
    font["CFF "].cff.topDictIndex[0].CharStrings["hidden"] = \
        font["CFF "].cff.topDictIndex[0].CharStrings["a"]
    assert build.fit_to_grid(font, 600) == 2
    assert font["hmtx"].metrics["hidden"][0] == 1000


def test_set_names():
    font = _cff_font()
    name = font["name"]
    # simulate the inherited Source Han Sans / donor strings that must
    # survive alongside ours
    name.setName("© Adobe", 0, 3, 1, 0x409)
    name.setName("Paul", 9, 3, 1, 0x409)

    ps = build.set_names(font, "Term", "Bold", False,
                         credits=[("Monaspace", "Copyright GitHub",
                                  "Lettermatic")])

    assert ps == "GengouJPTerm-Bold"
    copyright_ = name.getDebugName(0)
    assert build.PROJECT_COPYRIGHT in copyright_
    assert "© Adobe" in copyright_
    assert "Copyright GitHub" in copyright_
    designer = name.getDebugName(9)
    assert "Paul" in designer
    assert "Lettermatic" in designer
    assert name.getDebugName(8) == "hn-11"
    assert name.getDebugName(11) == build.PROJECT_URL
    assert name.getDebugName(3).endswith(";GNGO;GengouJPTerm-Bold")
    assert name.getDebugName(6) == "GengouJPTerm-Bold"

    os2 = font["OS/2"]
    assert os2.achVendID == "GNGO"
    assert os2.usWeightClass == 700
    assert os2.fsSelection & 0x20    # bold
    assert os2.fsSelection & 0x100   # WWS
    assert not os2.fsSelection & 0x40   # regular clear
    assert os2.version >= 4


def test_set_names_credits_the_face_own_family_not_the_base():
    """nameID 0 and 5 name the family the face is actually in. A Term
    face saying "Gengou JP" filed it under a family it is not in, and
    nerdpatch.rename marks whatever it finds -- so the Nerd Fonts Term
    face's version string named the non-Term Nerd Fonts family."""
    font = _cff_font()
    build.set_names(font, "Term", "SemiBold", False, version="6.0.0")
    name = font["name"]
    assert name.getDebugName(1) == "Gengou JP Term SemiBold"
    assert name.getDebugName(0).startswith("Gengou JP Term:")
    assert name.getDebugName(5).startswith("Version 6.0.0;Gengou JP Term")
    # and the base family keeps naming itself
    plain = _cff_font()
    build.set_names(plain, "", "SemiBold", False, version="6.0.0")
    assert plain["name"].getDebugName(0).startswith("Gengou JP:")
    assert plain["name"].getDebugName(5).startswith("Version 6.0.0;Gengou JP;")


# --- donor_credits (Latin donor's own composed name IDs 0 / 9) -----------

def test_donor_credits_parses_scp_and_monaspace_in_order():
    font = _tt_font([".notdef", "A"], {ord("A"): "A"}, {"A": 600})
    font["name"].setName(
        "Gengou: Copyright 2026 hn-11 (https://x). "
        "Source Code Pro: © 2023 Adobe (http://www.adobe.com/), with "
        "Reserved Font Name ‘Source’. "
        "Monaspace: Copyright 2023 GitHub, Inc. "
        "(https://github.com/githubnext/monaspace), with Reserved Font "
        "Names 'Monaspace', 'Monaspace Argon'.",
        0, 3, 1, 0x409)
    font["name"].setName(
        "Source Code Pro: Paul D. Hunt, Teo Tuominen; "
        "Monaspace: Riley Cran and the Lettermatic Team",
        9, 3, 1, 0x409)

    credits = build.donor_credits(font)

    assert [label for label, _, _ in credits] == ["Source Code Pro", "Monaspace"]
    scp_label, scp_copyright, scp_designer = credits[0]
    assert scp_copyright == (
        "© 2023 Adobe (http://www.adobe.com/), with Reserved Font "
        "Name ‘Source’.")
    assert scp_designer == "Paul D. Hunt, Teo Tuominen"
    mona_label, mona_copyright, mona_designer = credits[1]
    assert mona_copyright.endswith("'Monaspace Argon'.")
    assert mona_designer == "Riley Cran and the Lettermatic Team"


def test_donor_credits_designers_none_when_name_id_9_absent():
    font = _tt_font([".notdef", "A"], {ord("A"): "A"}, {"A": 600})
    font["name"].setName(
        "Gengou: Copyright 2026 hn-11 (https://x). "
        "Source Code Pro: © 2023 Adobe (http://www.adobe.com/), with "
        "Reserved Font Name ‘Source’. "
        "Monaspace: Copyright 2023 GitHub, Inc. "
        "(https://github.com/githubnext/monaspace), with Reserved Font "
        "Names 'Monaspace', 'Monaspace Argon'.",
        0, 3, 1, 0x409)
    # nameID 9 is never set on this font

    credits = build.donor_credits(font)

    assert [designer for _, _, designer in credits] == [None, None]


# --- stretch_path (full-width arrows from Monaspace) ---------------------

def _arrow_path(axis):
    """Shaft 100 long x 20 thick plus a triangular head, along `axis`."""
    import pathops
    path = pathops.Path()
    pen = path.getPen()
    pts = [(0, -10), (100, -10), (100, -30), (140, 0), (100, 30), (100, 10),
           (0, 10)]
    if axis == 1:
        pts = [(y, x) for x, y in pts]
    pen.moveTo(pts[0])
    for pt in pts[1:]:
        pen.lineTo(pt)
    pen.closePath()
    return path


@pytest.mark.parametrize("axis", [0, 1])
def test_stretch_path_lengthens_only_the_shaft(axis):
    src = _arrow_path(axis)
    out = build.stretch_path(src, axis, 60)
    b0, b1 = src.bounds, out.bounds
    if axis == 0:
        assert b1[2] - b1[0] == pytest.approx((b0[2] - b0[0]) + 60)
        assert (b1[1], b1[3]) == pytest.approx((b0[1], b0[3]))
    else:
        assert b1[3] - b1[1] == pytest.approx((b0[3] - b0[1]) + 60)
        assert (b1[0], b1[2]) == pytest.approx((b0[0], b0[2]))
    # the gap is filled with the shaft's own cross-section (20 thick)
    assert abs(out.area) == pytest.approx(abs(src.area) + 60 * 20)


def test_stretch_path_noop_when_nothing_to_add():
    src = _arrow_path(0)
    assert build.stretch_path(src, 0, 0) is src


@pytest.mark.parametrize("axis", [0, 1])
def test_stretch_path_shortens_the_shaft(axis):
    src = _arrow_path(axis)
    out = build.stretch_path(src, axis, -40)
    b0, b1 = src.bounds, out.bounds
    length = (lambda b: b[2] - b[0]) if axis == 0 else (lambda b: b[3] - b[1])
    assert length(b1) == pytest.approx(length(b0) - 40)
    assert abs(out.area) == pytest.approx(abs(src.area) - 40 * 20)


# --- set_cmap / env_paths / run_faces --------------------

def test_set_cmap_replaces_existing_and_adds_only_when_asked():
    font = _tt_font([".notdef", "a", "b", "c"], {0x61: "a", 0x10000: "b"},
                    {"a": 600, "b": 600, "c": 600})
    formats = {t.format for t in font["cmap"].tables if t.isUnicode()}
    assert formats == {4, 12}   # BMP-only and full-range subtables
    build.set_cmap(font, {0x61: "c", 0x62: "c"})
    for t in font["cmap"].tables:
        assert t.cmap[0x61] == "c"
        assert 0x62 not in t.cmap            # not added without add_new
    build.set_cmap(font, {0x62: "c", 0x10001: "c"}, add_new=True)
    for t in font["cmap"].tables:
        assert t.cmap[0x62] == "c"
        assert (0x10001 in t.cmap) == (t.format == 12)   # BMP-only skips it


def test_env_paths_reads_defaults_and_exits_on_missing(tmp_path, monkeypatch, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("SHS_DIR", str(a))
    monkeypatch.delenv("NF_SYMBOLS", raising=False)
    monkeypatch.setenv("GENGOU_VERSION", "9.9.9")
    env = build.env_paths({"SHS_DIR": None, "NF_SYMBOLS": str(b)})
    assert env == {"SHS_DIR": str(a), "NF_SYMBOLS": str(b), "GENGOU_VERSION": "9.9.9"}
    monkeypatch.setenv("NF_SYMBOLS", str(tmp_path / "nowhere"))
    monkeypatch.delenv("SHS_DIR")
    with pytest.raises(SystemExit, match=r"missing env: \['SHS_DIR', 'NF_SYMBOLS'\]"):
        build.env_paths({"SHS_DIR": None, "NF_SYMBOLS": str(b)})


_SEEN_IN_THIS_PROCESS = []


def _face_worker(job):
    if job == "bad":
        raise KeyError("reference face not found")
    _SEEN_IN_THIS_PROCESS.append(job)   # visible to the test only if in-process
    return f"built {job}"


def test_run_faces_collects_every_failure_across_the_pool(capsys):
    results = []
    with pytest.raises(SystemExit, match="1/3 faces failed"):
        build.run_faces(["x", "bad", "y"], _face_worker,
                        label=lambda j: f"{j} [base]",
                        on_result=lambda j, r: results.append(r))
    assert sorted(results) == ["built x", "built y"]   # the failure did not stop the run
    assert "FAILED bad [base]: KeyError('reference face not found')" in capsys.readouterr().err


def test_run_faces_small_run_stays_in_process(capsys):
    results = []
    _SEEN_IN_THIS_PROCESS.clear()
    with pytest.raises(SystemExit, match="1/2 faces failed"):
        build.run_faces(["bad", "y"], _face_worker,
                        label=lambda j: j, on_result=lambda j, r: results.append(r))
    assert results == ["built y"]
    assert _SEEN_IN_THIS_PROCESS == ["y"]           # the worker ran here
    err = capsys.readouterr().err
    assert "FAILED bad: KeyError" in err
    assert "Traceback" in err and "_face_worker" in err   # the traceback survives


def test_run_faces_larger_run_uses_the_pool():
    _SEEN_IN_THIS_PROCESS.clear()
    build.run_faces(["x", "y", "z"], _face_worker,
                    label=lambda j: j, on_result=lambda j, r: None)
    assert _SEEN_IN_THIS_PROCESS == []               # the workers ran elsewhere


def test_run_faces_result_handler_errors_are_not_face_failures():
    def boom(job, result):
        raise RuntimeError("handler bug")
    with pytest.raises(RuntimeError, match="handler bug"):
        build.run_faces(["x"], _face_worker, label=lambda j: j, on_result=boom)


# --- referenced_name_ids / prune_orphan_names -------------------------------

def _font_with_named_tables():
    """A mini font whose STAT, fvar and a GSUB FeatureParams all point at
    name records, plus three records nothing points at."""
    font = _tt_font([".notdef", "a"], {0x61: "a"}, {"a": 600})
    name = font["name"]
    build.add_stat(font, ["Regular", "Bold"], italic=False)   # STAT names
    fb = FontBuilder(font=font)
    fb.setupFvar([("wght", 300, 400, 900, "Weight")],
                 [{"location": {"wght": 400}, "stylename": "Regular",
                   "postscriptfontname": "Test-Regular"}])
    font["GSUB"] = newTable("GSUB")
    font["GSUB"].table = _empty_gsub_table()
    fp = otTables.FeatureParamsStylisticSet()
    fp.Version, fp.UINameID = 0, 300
    name.setName("Alt forms", 300, 3, 1, 0x409)
    build._add_feature(font["GSUB"].table, "ss01", [])
    font["GSUB"].table.FeatureList.FeatureRecord[0].Feature.FeatureParams = fp
    for nid, text in ((301, "Upright"), (302, "Weight"), (303, "leftover")):
        name.setName(text, nid, 3, 1, 0x409)
    return font


def test_referenced_name_ids_covers_stat_fvar_and_feature_params():
    font = _font_with_named_tables()
    used = build.referenced_name_ids(font)
    stat = font["STAT"].table
    for av in stat.AxisValueArray.AxisValue:
        assert av.ValueNameID in used
    assert all(ax.AxisNameID in used for ax in stat.DesignAxisRecord.Axis)
    inst = font["fvar"].instances[0]
    assert {inst.subfamilyNameID, inst.postscriptNameID} <= used
    assert 300 in used
    assert not {301, 302, 303} & used


def test_prune_orphan_names_drops_only_the_unreferenced_high_ids():
    font = _font_with_named_tables()
    before = {r.nameID for r in font["name"].names}
    assert build.prune_orphan_names(font) == [301, 302, 303]
    after = {r.nameID for r in font["name"].names}
    assert before - after == {301, 302, 303}
    assert font["name"].getDebugName(300) == "Alt forms"   # still referenced
    assert font["name"].getDebugName(1) == "Test"          # < 256 untouched
    assert build.prune_orphan_names(font) == []            # idempotent


# --- shift_charstring (Term: hints survive the widening) --------------------

def _t2(program, nominal=100, default=1000):
    from types import SimpleNamespace

    from fontTools.misc.psCharStrings import T2CharString
    private = SimpleNamespace(nominalWidthX=nominal, defaultWidthX=default)
    cs = T2CharString(program=list(program), private=private, globalSubrs=[])
    return cs, private


def _drawn(cs):
    from fontTools.pens.boundsPen import BoundsPen
    pen = BoundsPen(None)
    cs.draw(pen)
    return cs.width, pen.bounds


@pytest.mark.parametrize("program, new_width, want_width, want_prog", [
    # explicit vstem, hmoveto first, no width operand (advance = default 1000)
    ([21, -21, 224, 72, "hstem", 157, 676, "vstem", 157, "hmoveto", 97, "hlineto", "endchar"],
     1200, 1200,
     [1100, 21, -21, 224, 72, "hstem", 257, 676, "vstem", 257, "hmoveto", 97, "hlineto", "endchar"]),
    # implicit vstem hints in front of cntrmask, rmoveto first, width operand present
    ([-4, 75, 281, "hstem", 176, 77, "cntrmask", b"\xf8", 253, 10, "rmoveto", 50, "hlineto", "endchar"],
     1200, 1200,
     [1100, 75, 281, "hstem", 276, 77, "cntrmask", b"\xf8", 353, 10, "rmoveto", 50, "hlineto", "endchar"]),
    # hstemhm + hintmask (implicit vstems), vmoveto first -> rmoveto
    ([3, 77, 361, 63, "hstemhm", 109, 76, "hintmask", b"\x80", 300, "vmoveto", 40, "hlineto", "endchar"],
     1200, 1200,
     [1100, 3, 77, 361, 63, "hstemhm", 209, 76, "hintmask", b"\x80", 100, 300, "rmoveto", 40, "hlineto", "endchar"]),
    # new width equals defaultWidthX: no width operand at all
    ([-4, 75, 281, "hstem", 10, 10, "rmoveto", 50, "hlineto", "endchar"],
     1000, 1000,
     [75, 281, "hstem", 110, 10, "rmoveto", 50, "hlineto", "endchar"]),
    # an empty glyph: only the width changes
    (["endchar"], 1200, 1200, [1100, "endchar"]),
])
def test_shift_charstring_moves_the_outline_and_keeps_the_hints(program, new_width, want_width,
                                                                 want_prog):
    cs, private = _t2(program)
    before_width, before_bounds = _drawn(cs)
    assert build.shift_charstring(cs, 100, new_width, private)
    assert cs.program == want_prog
    width, bounds = _drawn(cs)
    assert width == want_width
    if before_bounds:
        assert bounds == (before_bounds[0] + 100, before_bounds[1],
                          before_bounds[2] + 100, before_bounds[3])


def test_shift_charstring_declines_a_seac_endchar():
    cs, private = _t2([100, 200, 65, 66, "endchar"])
    assert not build.shift_charstring(cs, 100, 1200, private)
    assert cs.program == [100, 200, 65, 66, "endchar"]


# --- glyph_bounds / update_bbox (extents in one pass, saves without recalc) --

def _extents_font():
    """CFF font with vertical metrics, saved and reloaded so every
    charstring carries bytecode (as a loaded Source Han Sans does)."""
    boxes = {"A": (20, -30, 520, 700), "B": (-40, 0, 300, 850)}
    glyph_order = [".notdef", "A", "B", "space"]
    charstrings = {}
    for g in glyph_order:
        pen = T2CharStringPen(700 if g == "B" else 600, None)
        if g in boxes:
            x0, y0, x1, y1 = boxes[g]
            pen.moveTo((x0, y0))
            pen.lineTo((x1, y0))
            pen.lineTo((x1, y1))
            pen.lineTo((x0, y1))
            pen.closePath()
        charstrings[g] = pen.getCharString()
    font = make_cff_font(glyph_order, charstrings,
                         {ord("A"): "A", ord("B"): "B", ord(" "): "space"},
                         {".notdef": (600, 0), "A": (600, 20), "B": (700, -40),
                          "space": (600, 0)},
                         ps="Test", font_info={"FullName": "Test"},
                         family="Test", style="Regular",
                         vmetrics={g: (1000, 100) for g in glyph_order}, vhea=(880, -120))
    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    return TTFont(buf), boxes


def test_glyph_bounds_measures_every_inked_glyph_and_keeps_bytecode():
    font, boxes = _extents_font()
    charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
    assert all(charstrings[g].bytecode is not None for g in boxes)

    bounds = build.glyph_bounds(font)

    assert bounds == boxes                     # blank glyphs are absent
    # drawn, but saved as loaded: the bytecode is back, nothing recompiles
    assert all(charstrings[g].bytecode is not None for g in boxes)
    assert all(charstrings[g].program is None for g in boxes)


def test_update_bbox_sets_head_cff_hhea_and_vhea_like_fonttools():
    import copy
    font, boxes = _extents_font()
    stale = font["hhea"]
    stale.xMaxExtent = stale.minLeftSideBearing = 0

    assert build.update_bbox(font) == [-40, -30, 520, 850]

    head = font["head"]
    assert (head.xMin, head.yMin, head.xMax, head.yMax) == (-40, -30, 520, 850)
    cff = font["CFF "].cff
    assert cff[cff.fontNames[0]].FontBBox == [-40, -30, 520, 850]
    # the same numbers fontTools' save-time recalc would produce
    for tag, fields in (("hhea", ("advanceWidthMax", "minLeftSideBearing",
                                  "minRightSideBearing", "xMaxExtent")),
                        ("vhea", ("advanceHeightMax", "minTopSideBearing",
                                  "minBottomSideBearing", "yMaxExtent"))):
        ref = copy.copy(font[tag])
        ref.recalc(font)
        assert {f: getattr(font[tag], f) for f in fields} == \
            {f: getattr(ref, f) for f in fields}, tag
    assert font["hhea"].advanceWidthMax == 700
    assert font["hhea"].minLeftSideBearing == -40
    assert font["hhea"].minRightSideBearing == 600 - 20 - 500   # A: 80
    assert font["hhea"].xMaxExtent == 20 + 500                  # A: 520


def test_update_bbox_leaves_an_inkless_font_alone():
    font = make_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600})
    assert build.update_bbox(font) is None


def test_sync_lsb_sets_bearings_from_the_outlines():
    font, boxes = _extents_font()
    metrics = font["hmtx"].metrics
    metrics["A"] = (600, 0)          # stale: the outline starts at 20
    metrics["space"] = (600, 7)      # blank glyph: left alone

    assert vfsource.sync_lsb(font) == 1

    assert metrics["A"] == (600, 20) and metrics["B"] == (700, -40)
    assert metrics["space"] == (600, 7)
    assert vfsource.sync_lsb(font) == 0


def test_fit_to_grid_stretches_a_tiling_glyph_into_its_step():
    """A character drawn to butt against the next one must fill the step
    the grid rounds it up to, not sit centred in it: Source Han Sans's
    two-em dash is 1580 units of ink in a 1672 advance and the step is
    2000, so centring left a 420-unit hole in a run of them."""
    font = _cff_font_with_widths({"emdash": 824, "plain": 824}, x0=12)
    build.set_cmap(font, {0x2E3A: "emdash"}, add_new=True)
    assert build.fit_to_grid(font, 600) == 2
    gs = font.getGlyphSet()
    hmtx = font["hmtx"].metrics
    assert hmtx["emdash"][0] == hmtx["plain"][0] == 1000
    dash = build._bounds(gs, "emdash")
    plain = build._bounds(gs, "plain")
    # stretched: the ink grew with the advance and the bearing with it
    assert round(dash[2] - dash[0]) == round(100 * 1000 / 824)
    assert hmtx["emdash"][1] == pytest.approx(dash[0], abs=1)
    # the ordinary glyph beside it is the same 100 units, only moved
    assert round(plain[2] - plain[0]) == 100


def _vtiling_font():
    """A face shaped like the built ones where tile_vertically reads it:
    each tiling character has a one-cell default that already spans the
    line (-400..1000, as the Latin donor draws it) and a full-width form
    under fwid drawn to Source Han Sans's 1000-unit em (-120..880).
    Everything the pass has to tell apart is here: a rule, a rule whose
    ink stops short, a diagonal, a dashed vertical, an upper block, a
    lower block, the full block, a shade, and a character inside the
    blocks with no full-width form at all."""
    shapes = {
        ".notdef": [[(0, 0), (1, 0), (1, 1)]],
        # one-cell defaults, all spanning the line
        "vrule1": [[(280, -400), (320, -400), (320, 1000), (280, 1000)]],
        "block1": [[(0, -400), (600, -400), (600, 1000), (0, 1000)]],
        "eighth1": [[(0, -400), (600, -400), (600, -225), (0, -225)]],
        "upper1": [[(0, 300), (600, 300), (600, 1000), (0, 1000)]],
        "dash1": [[(280, -400), (320, -400), (320, 1000), (280, 1000)]],
        "diag1": [[(0, -400), (120, -400), (600, 1000), (480, 1000)]],
        "shade1": [[(0, -400), (600, -400), (600, -300), (0, -300)]],
        "hrule1": [[(0, 180), (600, 180), (600, 220), (0, 220)]],
        # full width already: its "full-width form" under fwid is
        # itself, so there is no one-cell drawing for it to match
        "heavy1": [[(460, -120), (540, -120), (540, 880), (460, 880)]],
        # full-width forms, in the 1000-unit em
        "vruleF": [[(480, -120), (520, -120), (520, 880), (480, 880)]],
        "blockF": [[(0, -120), (1000, -120), (1000, 880), (0, 880)]],
        "eighthF": [[(0, -120), (1000, -120), (1000, 5), (0, 5)]],
        "upperF": [[(0, 380), (1000, 380), (1000, 880), (0, 880)]],
        # three dashes, stopping 56 units short of the em at either end
        "dashF": [[(480, -64), (520, -64), (520, 216), (480, 216)],
                  [(480, 296), (520, 296), (520, 464), (480, 464)],
                  [(480, 544), (520, 544), (520, 824), (480, 824)]],
        "diagF": [[(0, -120), (200, -120), (1000, 880), (800, 880)]],
        "shadeF": [[(0, -120), (1000, -120), (1000, -20), (0, -20)]],
        "hruleF": [[(0, 360), (1000, 360), (1000, 400), (0, 400)]],
    }
    order = list(shapes)
    charstrings = {}
    for g, contours in shapes.items():
        pen = T2CharStringPen(0, None)
        for points in contours:
            pen.moveTo(points[0])
            for pt in points[1:]:
                pen.lineTo(pt)
            pen.closePath()
        charstrings[g] = pen.getCharString()
    metrics = {".notdef": (0, 0)}
    for g in order[1:]:
        wide = g.endswith("F") or g == "heavy1"
        box = min(pt[0] for c in shapes[g] for pt in c)
        metrics[g] = (1000 if wide else 600, box)
    font = make_cff_font(order, charstrings,
                         {0x2502: "vrule1", 0x2588: "block1", 0x2581: "eighth1",
                          0x2580: "upper1", 0x2506: "dash1", 0x2541: "diag1",
                          0x2592: "shade1", 0x2500: "hrule1", 0x2503: "heavy1"},
                         metrics, ascent=984, descent=-273)
    _with_gsub(font, "feature fwid {\n" + "".join(
        f"  sub {one} by {one[:-1]}F;\n"
        for one in ("vrule1", "block1", "eighth1", "upper1", "dash1",
                    "diag1", "shade1", "hrule1")) + "} fwid;\n")
    # a character whose full-width form is the glyph itself: feaLib will
    # not write `sub X by X`, so it goes straight into the table
    gsub = font["GSUB"].table
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag == "fwid":
            for li in fr.Feature.LookupListIndex:
                gsub.LookupList.Lookup[li].SubTable[0].mapping["heavy1"] = "heavy1"
    font["vmtx"] = newTable("vmtx")
    # origin = top side bearing + yMax: 120 + 880 for every full width
    font["vmtx"].metrics = {g: (1000, 120 if g.endswith("F") or g == "heavy1"
                                else 0) for g in order}
    return font


def _band(font, name):
    box = build._bounds(font.getGlyphSet(), name)
    return (round(box[1]), round(box[3]))


def test_tile_vertically_extrudes_a_rule_and_scales_a_block():
    """The full-width rules are Source Han Sans's, drawn to its
    1000-unit em, and the line is 1257: under fwid a column of │ broke
    at every line. A rule is extruded to the band its one-cell default
    occupies, so its stem keeps its weight; a block element is mapped
    onto the band instead, so an eighth block stays an eighth of the
    line rather than gaining the same units as the full block."""
    font = _vtiling_font()
    assert build.tile_vertically(font) == 6
    gs = font.getGlyphSet()
    assert _band(font, "vruleF") == (-400, 1000)
    assert round(build._bounds(gs, "vruleF")[2]
                 - build._bounds(gs, "vruleF")[0]) == 40   # no fattening
    assert _band(font, "blockF") == (-400, 1000)
    assert _band(font, "eighthF") == (-400, -225)          # an eighth, at the floor
    assert _band(font, "upperF") == (300, 1000)            # a half, at the ceiling
    # the origin is a bearing plus the glyph's own yMax, so the bearing
    # has to give back what the ink gained above it
    assert build.vmtx_origin(font, "blockF") == 1000
    assert font["vmtx"].metrics["blockF"][1] == 0


def test_tile_vertically_puts_a_dashed_rule_on_the_line_s_own_pitch():
    """A dashed vertical never reaches the edge of its em, so extruding
    would skip it and a column of them would break at every line. It is
    mapped onto the LINE rather than the band a block gets: a pattern
    has to repeat at the pitch a column of cells advances by, and on
    the band its period came out 11% long — one dash merged with the
    next line's."""
    font = _vtiling_font()
    build.tile_vertically(font)
    hhea = font["hhea"]
    line = hhea.ascent - hhea.descent
    # the em -120..880 mapped onto -273..984
    assert _band(font, "dashF") == (round(hhea.descent + 56 * line / 1000),
                                    round(hhea.descent + 944 * line / 1000))
    assert _band(font, "blockF") == (-400, 1000)   # a block keeps the band


def test_tile_vertically_leaves_a_short_rule_and_a_slant():
    """The two guards on the extrusion: ─'s ink stops well inside its
    em, so there is nothing at the edge to extrude, and a slanted shape
    in the rule class reaches both edges but presents no rule there —
    extruding one would grow it a tail."""
    font = _vtiling_font()
    build.tile_vertically(font)
    assert _band(font, "hruleF") == (360, 400)
    assert _band(font, "diagF") == (-120, 880)


def test_tile_vertically_tiles_a_shade_instead_of_stretching_it():
    """A shade's dots would come out ovals under a 40% stretch, so the
    pattern is repeated a whole em up and down and cut to the band."""
    font = _vtiling_font()
    build.tile_vertically(font)
    assert _band(font, "shadeF") == (-120, 980)


def test_tile_vertically_leaves_a_character_with_no_full_width_form():
    """The pass reads the full-width forms a fwid substitution reaches:
    a character whose only glyph is its default is not drawn to stack,
    and extruding it would redraw the character."""
    font = _vtiling_font()
    build.tile_vertically(font)
    assert _band(font, "heavy1") == (-120, 880)
    assert "heavy1" not in build.vtiling_glyphs(font)


def test_tile_vertically_needs_the_block_and_its_full_width_form():
    """Both references come from the cmap and fwid; a face without them
    is left alone rather than guessed at."""
    font = _vtiling_font()
    build.set_cmap(font, {0x2588: ".notdef"})
    assert build.tile_vertically(font) == 0


def _lookup(kind, subtable):
    lk = otTables.Lookup()
    lk.LookupType = kind
    lk.LookupFlag = 0
    lk.SubTable = [subtable]
    lk.SubTableCount = 1
    return lk


def _coverage(glyphs):
    cov = otTables.Coverage()
    cov.glyphs = list(glyphs)
    return cov


def test_ccmp_remap_rewrites_a_substitution_and_drops_what_we_lack():
    """The donor's lookups are copied in OUR glyph names; a rule naming a
    glyph the graft never made is dropped, and a lookup that loses all
    of them says so."""
    st = otTables.SingleSubst()
    st.mapping = {"i": "dotlessi", "q": "qvariant"}
    lookup = _lookup(1, st)
    gmap = {"i": "cid1", "dotlessi": "cid2"}
    assert build._ccmp_remap(lookup, gmap, {}, "abcdefgh".index)
    assert lookup.SubTable[0].mapping == {"cid1": "cid2"}

    st2 = otTables.SingleSubst()
    st2.mapping = {"q": "qvariant"}
    dead = _lookup(1, st2)
    assert not build._ccmp_remap(dead, gmap, {}, "abcdefgh".index)
    assert dead.SubTable == []


def test_ccmp_remap_sorts_a_coverage_and_renumbers_its_callee():
    """A coverage is searched in glyph-id order, and the donor's order is
    not ours; a chain context calls its lookup by index, which the copy
    moves."""
    st = otTables.ChainContextSubst()
    st.Format = 3
    st.BacktrackCoverage = []
    st.InputCoverage = [_coverage(["a", "b"])]
    st.LookAheadCoverage = [_coverage(["c"])]
    rec = otTables.SubstLookupRecord()
    rec.SequenceIndex, rec.LookupListIndex = 0, 4
    st.SubstLookupRecord = [rec]
    st.SubstCount = 1
    lookup = _lookup(6, st)
    gmap = {"a": "za", "b": "yb", "c": "xc"}
    gid = {"za": 7, "yb": 3, "xc": 9}.get
    assert build._ccmp_remap(lookup, gmap, {4: 12}, gid)
    assert lookup.SubTable[0].InputCoverage[0].glyphs == ["yb", "za"]
    assert lookup.SubTable[0].SubstLookupRecord[0].LookupListIndex == 12


def test_ccmp_remap_drops_a_context_whose_callee_did_not_survive():
    """A chain context substitutes nothing itself: with its only callee
    gone it matches and does nothing, so it goes too."""
    st = otTables.ChainContextSubst()
    st.Format = 3
    st.BacktrackCoverage = []
    st.InputCoverage = [_coverage(["a"])]
    st.LookAheadCoverage = []
    rec = otTables.SubstLookupRecord()
    rec.SequenceIndex, rec.LookupListIndex = 0, 4
    st.SubstLookupRecord = [rec]
    st.SubstCount = 1
    lookup = _lookup(6, st)
    assert not build._ccmp_remap(lookup, {"a": "za"}, {}, {"za": 1}.get)


def test_insert_lookups_first_renumbers_everything_that_points_at_one():
    """ccmp has to run before the features that change a letter, and a
    shaper runs a stage's lookups in LookupList order whatever order the
    features name them — so the copies go in front, and every index
    already in the table moves up: the features' own lists and the
    nested ones a chain context calls."""
    st = otTables.ChainContextSubst()
    st.Format = 3
    st.BacktrackCoverage = []
    st.InputCoverage = [_coverage(["a"])]
    st.LookAheadCoverage = []
    rec = otTables.SubstLookupRecord()
    rec.SequenceIndex, rec.LookupListIndex = 0, 1
    st.SubstLookupRecord = [rec]
    st.SubstCount = 1
    single = otTables.SingleSubst()
    single.mapping = {"a": "b"}
    table = otTables.GSUB()
    table.LookupList = otTables.LookupList()
    table.LookupList.Lookup = [_lookup(6, st), _lookup(1, single)]
    table.FeatureList = otTables.FeatureList()
    fr = otTables.FeatureRecord()
    fr.FeatureTag = "cv04"
    fr.Feature = otTables.Feature()
    fr.Feature.LookupListIndex = [0, 1]
    table.FeatureList.FeatureRecord = [fr]

    ours = _lookup(1, otTables.SingleSubst())
    ours.SubTable[0].mapping = {"i": "dotlessi"}
    build._insert_lookups_first(table, [ours])

    assert table.LookupList.Lookup[0] is ours
    assert table.LookupList.LookupCount == 3
    assert fr.Feature.LookupListIndex == [1, 2]
    assert table.LookupList.Lookup[1].SubTable[0].SubstLookupRecord[0].LookupListIndex == 2


def test_insert_lookups_first_on_nothing_changes_nothing():
    table = otTables.GSUB()
    table.LookupList = otTables.LookupList()
    table.LookupList.Lookup = [_lookup(1, otTables.SingleSubst())]
    table.FeatureList = otTables.FeatureList()
    table.FeatureList.FeatureRecord = []
    build._insert_lookups_first(table, [])
    assert len(table.LookupList.Lookup) == 1


def _anchor(x, y):
    a = otTables.Anchor()
    a.Format, a.XCoordinate, a.YCoordinate = 1, x, y
    return a


def _mark_base_subtable():
    """A MarkBasePos in the donor's own glyph order: two marks and two
    bases, each with one anchor, listed the way SCP numbers them."""
    sub = otTables.MarkBasePos()
    sub.Format = 1
    sub.ClassCount = 1
    sub.MarkCoverage = _coverage(["grave", "acute"])
    sub.MarkArray = otTables.MarkArray()
    sub.MarkArray.MarkRecord = []
    for x in (10, 20):
        rec = otTables.MarkRecord()
        rec.Class, rec.MarkAnchor = 0, _anchor(x, 700)
        sub.MarkArray.MarkRecord.append(rec)
    sub.BaseCoverage = _coverage(["b", "a"])
    sub.BaseArray = otTables.BaseArray()
    sub.BaseArray.BaseRecord = []
    for y in (712, 486):
        rec = otTables.BaseRecord()
        rec.BaseAnchor = [_anchor(300, y)]
        sub.BaseArray.BaseRecord.append(rec)
    return sub


def test_remap_mark_subtable_sorts_each_coverage_with_its_anchors():
    """A mark coverage is not a set: its order is the order of the
    anchor array beside it, so the two are sorted together. Sorting one
    alone would hand every accent the next letter's anchor."""
    sub = _mark_base_subtable()
    gmap = {"grave": "cid01", "acute": "cid02", "a": "cid03", "b": "cid04"}
    gid = {"cid01": 9, "cid02": 4, "cid03": 7, "cid04": 2}.get
    assert build._remap_mark_subtable(sub, 4, gmap, gid)
    assert sub.MarkCoverage.glyphs == ["cid02", "cid01"]     # by our ids
    assert [r.MarkAnchor.XCoordinate for r in sub.MarkArray.MarkRecord] == [20, 10]
    assert sub.BaseCoverage.glyphs == ["cid04", "cid03"]
    assert [r.BaseAnchor[0].YCoordinate
            for r in sub.BaseArray.BaseRecord] == [712, 486]


def test_remap_mark_subtable_drops_a_coverage_we_cannot_fill():
    """A donor whose bases we never grafted leaves nothing to attach
    to, and an empty coverage would match everywhere."""
    sub = _mark_base_subtable()
    assert not build._remap_mark_subtable(
        sub, 4, {"grave": "cid01", "acute": "cid02"}, {"cid01": 1, "cid02": 2}.get)


def test_shift_subtable_anchors_moves_the_mark_and_leaves_the_base():
    """The outline of a grafted mark is a cell left of the donor's, so
    the anchor ON it has to be too — the base's does not move."""
    sub = _mark_base_subtable()
    moved = build._shift_subtable_anchors(4, sub, {"grave": -600})
    assert moved == 1
    assert [r.MarkAnchor.XCoordinate for r in sub.MarkArray.MarkRecord] == [-590, 20]
    assert [r.BaseAnchor[0].XCoordinate for r in sub.BaseArray.BaseRecord] == [300, 300]


def _gpos_skeleton():
    """An empty GPOS with the three lists _add_feature walks."""
    gpos = newTable("GPOS")
    gpos.table = otTables.GPOS()
    gpos.table.LookupList = otTables.LookupList()
    gpos.table.LookupList.Lookup = []
    gpos.table.LookupList.LookupCount = 0
    gpos.table.FeatureList = otTables.FeatureList()
    gpos.table.FeatureList.FeatureRecord = []
    gpos.table.FeatureList.FeatureCount = 0
    langsys = otTables.LangSys()
    langsys.FeatureIndex, langsys.FeatureCount = [], 0
    langsys.ReqFeatureIndex = 0xFFFF
    script = otTables.Script()
    script.DefaultLangSys, script.LangSysRecord = langsys, []
    script.LangSysCount = 0
    record = otTables.ScriptRecord()
    record.ScriptTag, record.Script = "DFLT", script
    gpos.table.ScriptList = otTables.ScriptList()
    gpos.table.ScriptList.ScriptRecord = [record]
    gpos.table.ScriptList.ScriptCount = 1
    return gpos


def test_realign_halfwidth_marks_backtracks_on_every_base_the_widening_left():
    """The correction fires after a base whose advance the Term widening
    did not change — which is not the same as "one cell wide". The Latin
    layer's 63 multi-cell ligature glyphs (== is 1200 units, === 1800)
    are in the widening's own skip set, so they are the same advance in
    both families; asking for one cell missed all 488 ligature-and-mark
    pairs, and the enclosing ring came out 100 units left of the cells
    it encloses. Advance cannot tell them apart: a widened full-width
    glyph is 1200 in Term too."""
    font = _cff_font_with_widths({"half": 600, "lig": 1200, "cjk": 1200,
                                  "mark": 0})
    font["GPOS"] = _gpos_skeleton()
    covered = build.realign_halfwidth_marks(font, {"mark": -100},
                                            {"cjk": 100})
    assert covered == 2                       # half and lig, not cjk
    lookups = font["GPOS"].table.LookupList.Lookup
    back, chain = lookups[-2], lookups[-1]
    assert back.SubTable[0].Value.XPlacement == 100        # the move, undone
    bases = set(chain.SubTable[0].BacktrackCoverage[-1].glyphs)
    assert bases == {"half", "lig"}
    # every depth reads the same set of bases behind its run of marks
    assert [len(sub.BacktrackCoverage) for sub in chain.SubTable] == [1, 2, 3, 4]
    assert all(set(sub.BacktrackCoverage[-1].glyphs) == bases
               for sub in chain.SubTable)
    # and the marks get an attachment class of their own, so an
    # intervening accent does not break the chain
    ours = font["GDEF"].table.MarkAttachClassDef.classDefs["mark"] \
        if "GDEF" in font else chain.LookupFlag >> 8
    assert chain.LookupFlag >> 8 == ours
    assert {fr.FeatureTag for fr in font["GPOS"].table.FeatureList.FeatureRecord} \
        == {"dist"}


def test_realign_halfwidth_marks_does_nothing_without_marks_or_bases():
    font = _cff_font_with_widths({"cjk": 1200, "mark": 0})
    font["GPOS"] = _gpos_skeleton()
    assert build.realign_halfwidth_marks(font, {}, {"cjk": 100}) == 0
    # every glyph widened: nothing is left to backtrack on
    assert build.realign_halfwidth_marks(font, {"mark": -100},
                                         {"cjk": 100, "mark": -100}) == 0
    assert font["GPOS"].table.LookupList.Lookup == []


def _mark_font(boxes):
    """A font whose cmap'd combining marks draw the given boxes at
    advance 0. `boxes` is {codepoint: (x0, x1)}."""
    names = {cp: f"m{i}" for i, cp in enumerate(boxes)}
    font = _cff_font_with_widths({n: 0 for n in names.values()})
    font["cmap"].tables[0].cmap = {cp: names[cp] for cp in boxes}
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    for cp, (x0, x1) in boxes.items():
        pen = T2CharStringPen(0, None)
        pen.moveTo((x0, 0))
        pen.lineTo((x1, 0))
        pen.lineTo((x1, 100))
        pen.closePath()
        td.CharStrings[names[cp]] = pen.getCharString(private=td.Private)
    return font, names


def test_fullwidth_marks_reads_where_the_ink_is_centred_not_the_cell_edges():
    """Source Han Sans's strokes thicken with the weight: at Medium the
    ideographic tone marks reach -1007 and +7, at Bold the voicing marks
    +5 and +7. A flat two units of tolerance dropped four of the eight
    at Medium and six at Bold — those kept the 1000-unit cell in Term,
    and the half-set then broke the build in shift_mark_placements. What
    says "drawn in the full-width cell" is which side of the origin the
    ink's centre falls on; the donor's own Latin marks are drawn to the
    right of it, U+0304 centred on it."""
    font, names = _mark_font({
        0x302A: (-1013, -807),     # Bold's tone mark, 13u past the cell
        0x3099: (-263, 5),         # Bold's dakuten, 5u past the origin
        0x20DD: (-972, -28),       # the enclosing ring
        0x0300: (98, 511),         # the donor's grave: right of the origin
        0x0304: (-163, 163),       # the donor's macron: centred on it
        0x0041: (0, 500),          # not a mark at all
    })
    got = build.fullwidth_marks(font)
    assert got == {names[0x302A], names[0x3099], names[0x20DD]}
    # ... and ours, drawn one CELL left, are told apart by _built alone
    build.state_of(font).built = {names[0x20DD]}
    assert build.fullwidth_marks(font) == {names[0x302A], names[0x3099]}


def test_shift_mark_placements_moves_only_the_marks_in_a_shared_subtable():
    """A Format 2 SinglePos carries one value per covered glyph, so a
    subtable covering both moved marks and other glyphs needs no
    splitting — only a Format 1 one, whose single value they share,
    does."""
    font = _cff_font_with_widths({"mark": 0, "other": 600})
    font["GPOS"] = _gpos_skeleton()

    def value(x):
        v = otTables.ValueRecord()
        v.XPlacement = x
        return v

    sub = otTables.SinglePos()
    sub.Format = 2
    sub.Coverage = otTables.Coverage()
    sub.Coverage.glyphs = ["mark", "other"]
    sub.Value = [value(500), value(70)]
    sub.ValueFormat = 0x1
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.SubTable = 1, [sub]
    font["GPOS"].table.LookupList.Lookup = [lookup]
    assert build.shift_mark_placements(font, {"mark": -100}) == 1
    assert [v.XPlacement for v in sub.Value] == [600, 70]

    flat = otTables.SinglePos()
    flat.Format = 1
    flat.Coverage = otTables.Coverage()
    flat.Coverage.glyphs = ["mark", "other"]
    flat.Value = value(500)
    flat.ValueFormat = 0x1
    lookup.SubTable = [flat]
    with pytest.raises(ValueError, match="would need splitting"):
        build.shift_mark_placements(font, {"mark": -100})
    flat.Coverage.glyphs = ["mark"]
    assert build.shift_mark_placements(font, {"mark": -100}) == 1
    assert flat.Value.XPlacement == 600


def test_rehome_replaced_marks_puts_the_grafted_accent_in_the_donor_s_lookup():
    """Source Han Sans attaches the Bopomofo tone marks with lookups
    whose MarkCoverage names its OWN U+0300/U+0301/U+0307/U+030C. The
    graft re-points those codepoints at the Latin donor's accents, so
    the coverage named glyphs no codepoint reaches and nothing
    attached: the accent drew through the letter's strokes. The anchor
    comes over shifted by the difference between the two inks' centres,
    because the two outlines are not the same shape."""
    font, names = _mark_font({0x0301: (100, 300)})     # ours, ink centre 200
    # their glyph: same font, a wider ink centred at 400
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    pen = T2CharStringPen(0, None)
    pen.moveTo((300, 0))
    pen.lineTo((500, 0))
    pen.lineTo((500, 100))
    pen.closePath()
    build.append_glyph(font, td, "theirs", pen.getCharString(private=td.Private),
                       None, 0, None, None)
    sub = otTables.MarkBasePos()
    sub.Format = 1
    sub.MarkCoverage = otTables.Coverage()
    sub.MarkCoverage.glyphs = ["theirs"]
    rec = otTables.MarkRecord()
    rec.Class = 0
    rec.MarkAnchor = otTables.Anchor()
    rec.MarkAnchor.Format = 1
    rec.MarkAnchor.XCoordinate, rec.MarkAnchor.YCoordinate = 10, 20
    sub.MarkArray = otTables.MarkArray()
    sub.MarkArray.MarkRecord = [rec]
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.SubTable = 4, [sub]
    font["GPOS"] = _gpos_skeleton()
    font["GPOS"].table.LookupList.Lookup = [lookup]

    assert build.rehome_replaced_marks(font, {0x0301: "theirs"}) == 1
    assert set(sub.MarkCoverage.glyphs) == {"theirs", names[0x0301]}
    gid = font.getGlyphID
    assert sub.MarkCoverage.glyphs == sorted(sub.MarkCoverage.glyphs, key=gid)
    ours = sub.MarkArray.MarkRecord[sub.MarkCoverage.glyphs.index(names[0x0301])]
    assert ours.Class == 0
    # 10 + (200 - 400): the donor's accent sits 200 units further left
    assert (ours.MarkAnchor.XCoordinate, ours.MarkAnchor.YCoordinate) == (-190, 20)
    # idempotent: a second pass adds nothing
    assert build.rehome_replaced_marks(font, {0x0301: "theirs"}) == 0


def test_extend_realign_bases_adds_glyphs_appended_after_the_widening():
    """nerdpatch.py appends 10,402 one-cell icons to a finished Term
    face, and realign_halfwidth_marks froze its backtrack at widening
    time — so a full-width mark after an icon kept the widening's
    -100."""
    font = _cff_font_with_widths({"half": 600, "cjk": 1200, "mark": 0})
    font["GPOS"] = _gpos_skeleton()
    assert build.realign_halfwidth_marks(font, {"mark": -100}, {"cjk": 100}) == 1
    chain = font["GPOS"].table.LookupList.Lookup[-1]
    assert chain.SubTable[0].BacktrackCoverage[-1].glyphs == ["half"]
    assert nerdpatch.extend_realign_bases(font, ["cjk", "half"]) == 4
    gid = font.getGlyphID
    for sub in chain.SubTable:
        names = sub.BacktrackCoverage[-1].glyphs
        assert names == sorted(set(names), key=gid) == sorted(["half", "cjk"], key=gid)
    assert nerdpatch.extend_realign_bases(font, []) == 0


def _ligature(components, name):
    lig = otTables.Ligature()
    lig.Component, lig.LigGlyph = list(components), name
    lig.CompCount = len(components) + 1
    return lig


def test_classify_unicode_marks_follows_a_mark_through_its_substitutes():
    """A substituted glyph takes its GDEF class from GDEF alone once a
    font has a GlyphClassDef — HarfBuzz has no Unicode-category
    fallback — so a variant left unclassified becomes a BASE and the
    mark-to-base search for the next mark stops on it. Source Code Pro
    Italic leaves the `.cap` design its ccmp swaps U+0310 for after a
    capital unclassified, and 23 of the 53 combining marks lost their
    attachment after U+0310 in every italic Latin face."""
    order = [".notdef", "mark", "cap", "capalt", "stack", "base", "lig"]
    font = make_font(order, {0x0310: "mark", ord("E"): "base"},
                     dict.fromkeys(order, 600))
    gdef = newTable("GDEF")
    gdef.table = otTables.GDEF()
    gdef.table.Version = 0x00010000
    gdef.table.GlyphClassDef = otTables.GlyphClassDef()
    gdef.table.GlyphClassDef.classDefs = {"base": 1}
    font["GDEF"] = gdef

    single = otTables.SingleSubst()
    single.mapping = {"mark": "cap"}
    alt = otTables.AlternateSubst()
    alt.alternates = {"cap": ["capalt"]}
    # a ligature of marks IS a mark (Source Code Pro's ccmp stacks 30
    # pairs of combining marks into one glyph); a ligature that takes a
    # BASE is not — calling Ą a mark would zero its advance
    liga = otTables.LigatureSubst()
    liga.ligatures = {"mark": [_ligature(["cap"], "stack")],
                      "base": [_ligature(["mark"], "lig")]}
    gsub = newTable("GSUB")
    gsub.table = otTables.GSUB()
    gsub.table.LookupList = otTables.LookupList()
    gsub.table.LookupList.Lookup = []
    for kind, sub in ((1, single), (3, alt), (4, liga)):
        lookup = otTables.Lookup()
        lookup.LookupType, lookup.SubTable = kind, [sub]
        gsub.table.LookupList.Lookup.append(lookup)
    font["GSUB"] = gsub

    fixed = anchors.classify_unicode_marks(font)
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    # the cmap'd mark, its variant, the variant's variant, and the
    # stack of two marks — but not the ligature a base takes part in
    assert set(fixed) == {"mark", "cap", "capalt", "stack"}
    assert classes["stack"] == 3
    assert classes["mark"] == classes["cap"] == classes["capalt"] == 3
    assert classes["base"] == 1 and "lig" not in classes
    assert anchors.classify_unicode_marks(font) == []      # idempotent


class _Tbl:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_copy_line_metrics_takes_the_line_from_the_latin_and_pins_the_win_box():
    """The line pitch comes from the Latin donor; the win box does not.
    It is pinned, because it is a clipping bound in the GDI paths and
    this family's ink runs far past any line it would be sane to
    declare -- and because at Source Han Sans's own 288 the Latin
    layer's box drawing (-400) and shade blocks (-454) were sliced."""
    base = {"hhea": _Tbl(ascent=1160, descent=-288, lineGap=0),
            "OS/2": _Tbl(sTypoAscender=1160, sTypoDescender=-288, sTypoLineGap=0,
                         usWinAscent=1160, usWinDescent=288, fsSelection=0x40)}
    latin = {"hhea": _Tbl(ascent=984, descent=-273, lineGap=0),
             "OS/2": _Tbl(sTypoAscender=984, sTypoDescender=-273, sTypoLineGap=0,
                          usWinAscent=1060, usWinDescent=454, fsSelection=0x40)}
    build.copy_line_metrics(base, latin)
    assert (base["hhea"].ascent, base["hhea"].descent) == (984, -273)
    assert (base["OS/2"].sTypoAscender, base["OS/2"].sTypoDescender) == (984, -273)
    assert base["OS/2"].fsSelection & (1 << 7)            # USE_TYPO_METRICS
    assert (base["OS/2"].usWinAscent, base["OS/2"].usWinDescent) == build.WIN_METRICS
    assert build.WIN_METRICS == (1160, 454)
    # deep enough for the shade blocks, and not the typo descender
    assert build.WIN_METRICS[1] >= 454 > 288


def test_cell_fit_centres_what_fits_and_condenses_only_what_does_not():
    """The one rule for seating a proportional glyph in a monospaced
    cell, which build_latin.add_missing_from_sans applies. Condensing
    costs stroke weight, so a glyph that already fits keeps its drawn
    width and only its position moves."""
    cell, bearing = 600, 8
    room = cell - 2 * bearing

    # fits: untouched horizontally, ink centred in the cell. 400 of ink
    # in 600 leaves 100 either side, which is where it was already drawn
    sx, dx = build.cell_fit((100, 0, 500, 700), cell, bearing)
    assert (sx, dx) == (1.0, 0)
    assert (100 + dx, 500 + dx) == (100, 500)

    # too wide: condensed to exactly the room, then centred, so the ink
    # lands on the bearing at each side
    box = (0, 0, 918, 742)                       # Ж as Source Han Sans draws it
    sx, dx = build.cell_fit(box, cell, bearing)
    assert sx == room / 918
    left, right = box[0] * sx + dx, box[2] * sx + dx
    assert (round(left), round(right)) == (bearing, cell - bearing)

    # exactly the room: still not condensed
    sx, _ = build.cell_fit((0, 0, room, 100), cell, bearing)
    assert sx == 1.0

    # a blank glyph has nothing to seat
    assert build.cell_fit(None, cell, bearing) == (1.0, 0)


def test_cell_fit_ignores_where_the_ink_sits_when_centring():
    """Only the ink's width decides the scale, and only its position
    decides the offset: a glyph drawn far off its origin still lands in
    the middle of the cell."""
    for x0 in (-300, 0, 250):
        sx, dx = build.cell_fit((x0, 0, x0 + 400, 500), 600, 8)
        assert sx == 1.0
        assert round(x0 + dx) == 100          # (600 - 400) / 2


# --- prune_orphan_lookups --------------------------------------------------

def _single(mapping):
    st = otTables.SingleSubst()
    st.mapping = dict(mapping)
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag, lk.SubTable = 1, 0, [st]
    lk.SubTableCount = 1
    return lk


def _chain_f3(*targets):
    """A format 3 chain context: its records sit on the subtable."""
    st = otTables.ChainContextSubst()
    st.Format = 3
    st.SubstLookupRecord = []
    for seq, idx in enumerate(targets):
        rec = otTables.SubstLookupRecord()
        rec.SequenceIndex, rec.LookupListIndex = seq, idx
        st.SubstLookupRecord.append(rec)
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag, lk.SubTable = 6, 0, [st]
    lk.SubTableCount = 1
    return lk


def _chain_f1(target):
    """A format 1 chain context, whose records sit two objects down —
    the nesting _lookup_records has to walk rather than enumerate."""
    rec = otTables.SubstLookupRecord()
    rec.SequenceIndex, rec.LookupListIndex = 0, target
    rule = otTables.ChainSubRule()
    rule.SubstLookupRecord = [rec]
    rule.Backtrack, rule.Input, rule.LookAhead = [], [], []
    rs = otTables.ChainSubRuleSet()
    rs.ChainSubRule = [rule]
    st = otTables.ChainContextSubst()
    st.Format = 1
    st.ChainSubRuleSet = [rs]
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag, lk.SubTable = 6, 0, [st]
    lk.SubTableCount = 1
    return lk


class _FakeLookupList:
    def __init__(self, lookups):
        self.Lookup = list(lookups)
        self.LookupCount = len(self.Lookup)


def _gsub_with(lookups, feature_lookups):
    """One 'calt' record over `feature_lookups`, named by one LangSys:
    reachability starts at the LangSys, so a record nothing names is
    no root."""
    default = FakeLangSys([0])
    default.ReqFeatureIndex = 0xFFFF
    gsub = FakeGSUB([FakeFeatureRecord("calt", FakeFeature(list(feature_lookups)))],
                    [FakeScriptRecord(FakeScript(default))])
    gsub.LookupList = _FakeLookupList(lookups)
    return gsub


def test_prune_orphan_lookups_keeps_what_a_feature_reaches_through_a_chain():
    """Reachability, not membership: lookup 3 is in no feature at all and
    survives because a chain context calls it, while 1 and 2 go."""
    gsub = _gsub_with([_chain_f3(3), _single({"a": "b"}), _single({"c": "d"}),
                       _single({"e": "f"})], [0])
    font = {"GSUB": FakeTable(gsub)}

    assert build.prune_orphan_lookups(font) == {"GSUB": 2}

    assert gsub.LookupList.LookupCount == 2
    assert [lk.LookupType for lk in gsub.LookupList.Lookup] == [6, 1]
    # the chain's callee moved from 3 to 1, and the feature still points at 0
    assert (gsub.LookupList.Lookup[0].SubTable[0]
            .SubstLookupRecord[0].LookupListIndex) == 1
    assert gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex == [0]
    assert gsub.LookupList.Lookup[1].SubTable[0].mapping == {"e": "f"}


def test_prune_orphan_lookups_follows_a_chain_nested_in_rule_sets():
    """Format 1 buries its records two objects deeper. Missing them would
    drop a live lookup, which is worse than leaving a dead one."""
    gsub = _gsub_with([_chain_f1(2), _single({"a": "b"}), _single({"e": "f"})],
                      [0])
    font = {"GSUB": FakeTable(gsub)}

    assert build.prune_orphan_lookups(font) == {"GSUB": 1}
    assert gsub.LookupList.Lookup[1].SubTable[0].mapping == {"e": "f"}
    assert (gsub.LookupList.Lookup[0].SubTable[0].ChainSubRuleSet[0]
            .ChainSubRule[0].SubstLookupRecord[0].LookupListIndex) == 1


def test_prune_orphan_lookups_follows_a_chain_through_a_chain():
    """Transitive: 0 calls 2, and 2 calls 3."""
    gsub = _gsub_with([_chain_f3(2), _single({"a": "b"}), _chain_f3(3),
                       _single({"e": "f"})], [0])
    font = {"GSUB": FakeTable(gsub)}

    assert build.prune_orphan_lookups(font) == {"GSUB": 1}
    assert [lk.LookupType for lk in gsub.LookupList.Lookup] == [6, 6, 1]


def test_prune_orphan_lookups_leaves_a_font_with_nothing_orphaned_alone():
    lookups = [_single({"a": "b"}), _single({"c": "d"})]
    gsub = _gsub_with(lookups, [0, 1])
    font = {"GSUB": FakeTable(gsub)}

    assert build.prune_orphan_lookups(font) == {}
    assert gsub.LookupList.Lookup == lookups


def test_prune_orphan_lookups_leaves_a_font_with_jstf_alone():
    """JSTF indexes this same LookupList and nothing here renumbers it."""
    gsub = _gsub_with([_single({"a": "b"}), _single({"c": "d"})], [0])
    font = {"GSUB": FakeTable(gsub), "JSTF": object()}

    assert build.prune_orphan_lookups(font) == {}
    assert gsub.LookupList.LookupCount == 2


# --- update_bbox_after -----------------------------------------------------

class _FakeCFFTop:
    def __init__(self):
        self.FontBBox = [0, 0, 0, 0]


class _FakeCFFIndex:
    def __init__(self):
        self.fontNames = ["T"]
        self._td = _FakeCFFTop()

    def __getitem__(self, name):
        return self._td


class _FakeCFFTable:
    def __init__(self):
        self.cff = _FakeCFFIndex()


class _FakeMtx:
    def __init__(self, metrics):
        self.metrics = dict(metrics)


def _extent_font(*, box=(0, -200, 600, 800), hhea=(600, 10, 20, 500),
                 hmtx=None, vertical=False):
    head = SimpleNamespace(xMin=box[0], yMin=box[1], xMax=box[2], yMax=box[3])
    h = SimpleNamespace(advanceWidthMax=hhea[0], minLeftSideBearing=hhea[1],
                        minRightSideBearing=hhea[2], xMaxExtent=hhea[3])
    font = {"head": head, "hhea": h, "CFF ": _FakeCFFTable(),
            "hmtx": _FakeMtx(hmtx or {})}
    if vertical:
        font["vhea"] = SimpleNamespace(advanceHeightMax=1000,
                                       minTopSideBearing=5,
                                       minBottomSideBearing=15,
                                       yMaxExtent=900)
        font["vmtx"] = _FakeMtx({n: (1000, 5) for n in (hmtx or {})})
    return font


def test_update_bbox_after_widens_the_box_and_the_extents():
    font = _extent_font(hmtx={"icon": (600, 30)})
    assert nerdpatch.update_bbox_after(font, {"icon": (30, -300, 700, 900)}, {})
    head = font["head"]
    assert (head.xMin, head.yMin, head.xMax, head.yMax) == (0, -300, 700, 900)
    assert font["CFF "].cff["T"].FontBBox == [0, -300, 700, 900]
    h = font["hhea"]
    assert h.advanceWidthMax == 600                 # not beaten
    assert h.minLeftSideBearing == 10               # 30 is not smaller
    # size 670, advance 600, sb 30 -> far side -100, which is smaller
    assert h.minRightSideBearing == -100
    assert h.xMaxExtent == 700                      # 30 + 670


def test_update_bbox_after_leaves_extents_a_new_glyph_cannot_beat():
    font = _extent_font(hmtx={"icon": (600, 100)})
    assert nerdpatch.update_bbox_after(font, {"icon": (100, 0, 200, 100)}, {})
    h = font["hhea"]
    assert (h.advanceWidthMax, h.minLeftSideBearing) == (600, 10)
    assert (h.minRightSideBearing, h.xMaxExtent) == (20, 500)
    head = font["head"]
    assert (head.xMin, head.yMin, head.xMax, head.yMax) == (0, -200, 600, 800)


def test_update_bbox_after_refuses_when_a_redrawn_glyph_held_the_box_up():
    """The Latin faces' real case: a Powerline glyph reaching 1060 is
    redrawn to 1000, and the old maximum cannot be taken back out of an
    aggregate. Refusing is the whole point -- the alternative is a face
    declaring ink it no longer has."""
    font = _extent_font(box=(0, -200, 600, 1060), hmtx={"pl": (600, 0)})
    dropped = {"pl": ((0, -200, 600, 1060), (600, 0), None)}
    assert nerdpatch.update_bbox_after(font, {"pl": (0, -200, 600, 1000)},
                                   dropped) is False
    assert font["head"].yMax == 1060                # untouched, caller remeasures


def test_update_bbox_after_refuses_when_a_redrawn_glyph_held_an_extent_up():
    """Its old side bearing of 10 was minLeftSideBearing, and the glyph
    that replaced it sits at 40."""
    font = _extent_font(hhea=(600, 10, 20, 500), hmtx={"pl": (600, 40)})
    dropped = {"pl": ((10, 0, 100, 100), (600, 10), None)}
    assert nerdpatch.update_bbox_after(font, {"pl": (40, 0, 130, 100)},
                                   dropped) is False


def test_update_bbox_after_allows_a_rewrite_that_reaches_as_far():
    """A rewrite takes nothing away while the new outline still holds
    every extreme the old one did — which is what keeps the fast path
    open for the JP faces, whose redrawn glyphs keep their cell."""
    font = _extent_font(hhea=(600, 10, 20, 500), hmtx={"pl": (600, 10)})
    dropped = {"pl": ((10, 0, 100, 100), (600, 10), None)}
    assert nerdpatch.update_bbox_after(font, {"pl": (10, 0, 100, 100)}, dropped)
    assert font["hhea"].minLeftSideBearing == 10


def test_update_bbox_after_checks_the_vertical_extents_too():
    """vhea has the same four, and a face with vmtx has to clear them
    as well as hhea's."""
    font = _extent_font(hmtx={"pl": (600, 40)}, vertical=True)
    font["vmtx"].metrics["pl"] = (1000, 50)         # was 5, which WAS the min
    dropped = {"pl": ((40, 0, 100, 100), (600, 40), (1000, 5))}
    assert nerdpatch.update_bbox_after(font, {"pl": (40, 0, 100, 100)},
                                   dropped) is False


def test_append_glyph_gives_a_zero_width_mark_no_vertical_advance_either():
    """A combining mark must not advance in either direction. Copying
    the donor's vertical advance gave every grafted accent a full cell
    of it, which is not what a mark is."""
    font = _cff_font_with_widths({"A": 600})
    font["vmtx"] = _FakeMtx({"A": (1000, 120)})
    font["vhea"] = SimpleNamespace(ascent=880, descent=-120)
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    pen = T2CharStringPen(0, None)
    pen.moveTo((0, 0))
    pen.lineTo((100, 0))
    pen.lineTo((100, 100))
    pen.closePath()
    cs = pen.getCharString()

    build.append_glyph(font, td, "mark", cs, None, 0, vdonor="A")
    build.append_glyph(font, td, "letter", cs, None, 600, vdonor="A")

    assert font["hmtx"].metrics["mark"][0] == 0
    assert font["vmtx"].metrics["mark"][0] == 0          # not the donor's 1000
    assert font["hmtx"].metrics["letter"][0] == 600
    assert font["vmtx"].metrics["letter"][0] == 1000     # a letter still does


# --- import_donor_base_anchors ---------------------------------------------

def _anchor(x, y):
    a = otTables.Anchor()
    a.Format, a.XCoordinate, a.YCoordinate = 1, x, y
    return a


def _markbase(marks, bases):
    """One MarkBasePos: {mark glyph: (class, anchor)}, {base: [anchors]}."""
    st = otTables.MarkBasePos()
    st.Format = 1
    st.ClassCount = 1
    st.MarkCoverage = otTables.MarkCoverage()
    st.MarkCoverage.glyphs = list(marks)
    st.MarkArray = otTables.MarkArray()
    st.MarkArray.MarkRecord = []
    for cls, anc in marks.values():
        rec = otTables.MarkRecord()
        rec.Class, rec.MarkAnchor = cls, anc
        st.MarkArray.MarkRecord.append(rec)
    st.BaseCoverage = otTables.BaseCoverage()
    st.BaseCoverage.glyphs = list(bases)
    st.BaseArray = otTables.BaseArray()
    st.BaseArray.BaseRecord = []
    for anchor_list in bases.values():
        rec = otTables.BaseRecord()
        rec.BaseAnchor = list(anchor_list)
        st.BaseArray.BaseRecord.append(rec)
    st.BaseArray.BaseCount = len(bases)
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag, lk.SubTable = 4, 0, [st]
    lk.SubTableCount = 1
    return lk


class _GposFont:
    """Enough font for the mark helpers: a GPOS with `mark` over the
    given lookups, a cmap, and a glyph order for getGlyphID."""

    def __init__(self, lookups, cmap, order):
        table = otTables.GPOS()
        table.LookupList = _FakeLookupList(lookups)
        fr = FakeFeatureRecord("mark", FakeFeature(list(range(len(lookups)))))
        table.FeatureList = FakeFeatureList([fr])
        self._tables = {"GPOS": FakeTable(table)}
        self._cmap = dict(cmap)
        self._order = list(order)

    def __contains__(self, key):
        return key in self._tables

    def __getitem__(self, key):
        return self._tables[key]

    def getBestCmap(self):
        return self._cmap

    def getGlyphID(self, name):
        return self._order.index(name)


def test_pair_mark_lookups_matches_on_the_marks_each_one_attaches():
    """Position would be an assumption; the marks they cover are the
    fonts' own statement of what each lookup is for."""
    top = {"acute": (0, _anchor(0, 0))}
    bottom = {"cedilla": (0, _anchor(0, 0))}
    ours = _GposFont([_markbase(bottom, {}), _markbase(top, {})],
                     {0x0301: "acute", 0x0327: "cedilla"},
                     [".notdef", "acute", "cedilla"])
    theirs = _GposFont([_markbase(top, {}), _markbase(bottom, {})],
                       {0x0301: "acute", 0x0327: "cedilla"},
                       [".notdef", "acute", "cedilla"])
    # ours: 0 is bottom, 1 is top; theirs: 0 is top, 1 is bottom
    assert anchors.pair_mark_lookups(ours, theirs) == {0: 1, 1: 0}


def test_pair_mark_lookups_gives_up_rather_than_guess():
    """Two of ours wanting the same one of theirs is not a pairing, and
    writing one class's anchors into another would misplace every accent
    of that class."""
    top = {"acute": (0, _anchor(0, 0))}
    ours = _GposFont([_markbase(top, {}), _markbase(top, {})],
                     {0x0301: "acute"}, [".notdef", "acute"])
    theirs = _GposFont([_markbase(top, {})], {0x0301: "acute"},
                       [".notdef", "acute"])
    assert anchors.pair_mark_lookups(ours, theirs) == {}


def test_pair_mark_lookups_refuses_a_tie():
    """Two of theirs equally close to one of ours: picking either is a
    coin toss, and the anchors of the wrong class land every accent of
    that class somewhere else."""
    top = {"acute": (0, _anchor(0, 0))}
    ours = _GposFont([_markbase(top, {})], {0x0301: "acute"},
                     [".notdef", "acute"])
    theirs = _GposFont([_markbase(top, {}), _markbase(top, {})],
                       {0x0301: "acute"}, [".notdef", "acute"])
    assert anchors.pair_mark_lookups(ours, theirs) == {}


def _cff_font_with_heights(heights):
    """A CFF font whose glyphs are 100 units wide and as tall as given,
    all one cell of advance. Varying heights are what tell a top-mark
    lookup from a below-mark one: an anchor a fixed distance off one
    edge is a varying distance off the other."""
    glyph_order = [".notdef", *heights]
    charstrings = {}
    for g in glyph_order:
        pen = T2CharStringPen(0, None)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, heights.get(g, 100)))
        pen.closePath()
        charstrings[g] = pen.getCharString()
    return make_cff_font(glyph_order, charstrings,
                         {0xE000 + i: g for i, g in enumerate(heights)},
                         {".notdef": (0, 0), **{g: (600, 0) for g in heights}})


def _drawn_gpos_font(heights, cmap, lookups):
    """A real CFF font (so _bounds can measure it) carrying a GPOS with
    `mark` over the given lookups."""
    font = _cff_font_with_heights(heights)
    font["cmap"].tables[0].cmap = dict(cmap)
    table = otTables.GPOS()
    table.LookupList = _FakeLookupList(lookups)
    table.FeatureList = FakeFeatureList(
        [FakeFeatureRecord("mark", FakeFeature(list(range(len(lookups)))))])
    font["GPOS"] = FakeTable(table)
    return font


def _edge_markbase(marks, heights, dy, top):
    """A MarkBasePos whose base anchors sit `dy` off each base's ink top
    (or bottom), centred on its 100-unit width."""
    return _markbase(marks, {g: [_anchor(50, (h if top else 0) + dy)]
                             for g, h in heights.items()})


# heights that differ letter to letter: an anchor 20 above the ink top
# is then a different distance above the ink bottom for each one, which
# is what lets the fit tell the two edges apart
_HEIGHTS = {f"b{i}": 400 + 20 * i for i in range(20)}


def _letters_cmap(names, extra=()):
    return {0x41 + i: g for i, g in enumerate(names)} | dict(extra)


def test_anchor_loose_letters_gives_a_letter_the_rule_its_neighbours_follow():
    """A mark these donors cannot place does not land approximately --
    the shaper zeroes its spacing advance, so it lands a whole cell to
    the right, on the next character. The rule comes from the anchors
    the lookup already carries."""
    heights = {**_HEIGHTS, "loose": 500, "acute": 100}
    marks = {"acute": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        heights,
        _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x5A: "loose"}),
        [_edge_markbase(marks, _HEIGHTS, 20, top=True)])

    assert anchors.anchor_loose_letters(font) == 1
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    assert "loose" in sub.BaseCoverage.glyphs
    assert sub.BaseCoverage.glyphs == sorted(sub.BaseCoverage.glyphs,
                                             key=font.getGlyphID)
    got = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index("loose")]
    # centred on the 100-unit width, 20 above this letter's own ink top
    assert (got.BaseAnchor[0].XCoordinate,
            got.BaseAnchor[0].YCoordinate) == (50, 520)
    assert sub.BaseArray.BaseCount == len(sub.BaseCoverage.glyphs)


def test_anchor_loose_letters_takes_the_x_of_the_letter_it_is_built_on():
    """A letter the donor anchored off centre, and the same drawing with
    something added to it: they are one shape, so the mark belongs in
    one place. Predicted from the ink centre instead, the accent jumped
    between them -- the diaeresis over L's stem and over the empty space
    beside L-with-line-below, 149 units apart in the built face.

    The y still comes off this letter's own ink, which is what puts a
    mark above the accent the letter already carries."""
    # U+1E3A is L with line below: canonically L + U+0331
    heights = {"L": 656, "Lbar": 656, "acute": 100}
    marks = {"acute": (0, _anchor(0, 0))}
    # 20 bases so the rule fits, but L's anchor is 30 left of centre
    filler = {f"b{i}": 400 + 20 * i for i in range(20)}
    covered = _markbase(marks,
                        {**{g: [_anchor(50, h + 20)] for g, h in filler.items()},
                         "L": [_anchor(20, 676)]})
    font = _drawn_gpos_font(
        {**filler, **heights},
        {**{0x41 + i: g for i, g in enumerate(filler)},
         0x004C: "L", 0x1E3A: "Lbar", 0x0301: "acute"},
        [covered])

    assert anchors.anchor_loose_letters(font) == 1      # Lbar only; L is covered
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    got = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index("Lbar")]
    assert got.BaseAnchor[0].XCoordinate == 20        # L's, not the centre 50
    assert got.BaseAnchor[0].YCoordinate == 676       # its own ink top + 20


def test_anchor_loose_letters_does_not_follow_a_compatibility_mapping():
    """A superscript w is not a w with something added to it -- it is a
    different letter drawn somewhere else, and its marks belong where
    they fall, not over the letter it was derived from."""
    filler = {f"b{i}": 400 + 20 * i for i in range(20)}
    marks = {"acute": (0, _anchor(0, 0))}
    covered = _markbase(marks,
                        {**{g: [_anchor(50, h + 20)] for g, h in filler.items()},
                         "w": [_anchor(11, 520)]})
    font = _drawn_gpos_font(
        {**filler, "w": 500, "wsuper": 700, "acute": 100},
        {**{0x41 + i: g for i, g in enumerate(filler)},
         0x0077: "w", 0x02B7: "wsuper", 0x0301: "acute"},
        [covered])
    assert anchors.anchor_loose_letters(font) == 1
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    got = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index("wsuper")]
    assert got.BaseAnchor[0].XCoordinate == 50        # the rule's, not w's 11


def test_anchor_loose_letters_reads_a_below_mark_lookup_off_the_ink_bottom():
    """Which edge the anchors track is the lookup's own statement of
    what it is for. Read off the top instead, a cedilla would be placed
    an ink-height above where it belongs -- and the height differs per
    letter, which is exactly why the wrong edge does not fit."""
    heights = {**_HEIGHTS, "loose": 500, "cedilla": 100}
    marks = {"cedilla": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        heights,
        _letters_cmap(_HEIGHTS, {0x0327: "cedilla", 0x5A: "loose"}),
        [_edge_markbase(marks, _HEIGHTS, -14, top=False)])

    assert anchors.anchor_loose_letters(font) == 1
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    got = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index("loose")]
    # the ink bottom is 0, so -14; read off the top it would be 486
    assert got.BaseAnchor[0].YCoordinate == -14


def test_anchor_loose_letters_leaves_a_lookup_that_follows_no_rule_alone():
    """Anchors scattered against both edges are a lookup placing each
    mark by hand. Predicting one would put it somewhere of this build's
    own invention, which is worse than the donor's answer -- even when
    that answer is nothing."""
    marks = {"acute": (0, _anchor(0, 0))}
    scattered = _markbase(marks, {g: [_anchor(50, 300 + 37 * i)]
                                  for i, g in enumerate(_HEIGHTS)})
    font = _drawn_gpos_font(
        {**_HEIGHTS, "loose": 500, "acute": 100},
        _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x5A: "loose"}),
        [scattered])
    assert anchors.anchor_loose_letters(font) == 0
    assert font["GPOS"].table.LookupList.Lookup[0].SubTable[0] \
        .BaseCoverage.glyphs == list(_HEIGHTS)


def test_anchor_loose_letters_leaves_a_lookup_with_too_few_bases_alone():
    marks = {"acute": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        {"b0": 400, "loose": 500, "acute": 100},
        {0x0301: "acute", 0x41: "b0", 0x5A: "loose"},
        [_markbase(marks, {"b0": [_anchor(50, 420)]})])
    assert anchors.anchor_loose_letters(font) == 0
    assert font["GPOS"].table.LookupList.Lookup[0].SubTable[0] \
        .BaseCoverage.glyphs == ["b0"]


def test_fit_anchor_rules_keys_by_lookup_and_subtable():
    """What a variable font's masters share. The rule is fitted once, on
    the default master, and handed to the others, so the key has to name
    the same subtable in every one of them."""
    marks = {"acute": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        {**_HEIGHTS, "loose": 500, "acute": 100},
        _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x5A: "loose"}),
        [_edge_markbase(marks, _HEIGHTS, 20, top=True)])
    rules = anchors.fit_anchor_rules(font)
    assert list(rules) == [(0, 0)]
    assert rules[(0, 0)] == (True, 0, 20)      # top edge, centred, +20


def test_anchor_loose_letters_uses_the_rule_it_is_handed():
    """Handed a rule, it does not refit: that is what keeps a variable
    font's masters placing the same letters. Here the handed rule says
    something the face's own anchors do not, and the handed one wins."""
    marks = {"acute": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        {**_HEIGHTS, "loose": 500, "acute": 100},
        _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x5A: "loose"}),
        [_edge_markbase(marks, _HEIGHTS, 20, top=True)])
    assert anchors.anchor_loose_letters(font, rules={(0, 0): (True, 7, 99)}) == 1
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    got = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index("loose")]
    assert (got.BaseAnchor[0].XCoordinate,
            got.BaseAnchor[0].YCoordinate) == (57, 599)   # 50+7, 500+99


def test_anchor_loose_letters_handed_nothing_places_nothing():
    """An empty rule set is how the variable path could have degraded in
    silence -- every master agreeing perfectly on having done nothing.
    The builders turn a count of 0 into an error for that reason."""
    marks = {"acute": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        {**_HEIGHTS, "loose": 500, "acute": 100},
        _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x5A: "loose"}),
        [_edge_markbase(marks, _HEIGHTS, 20, top=True)])
    assert anchors.anchor_loose_letters(font, rules={}) == 0
    assert "loose" not in (font["GPOS"].table.LookupList.Lookup[0]
                           .SubTable[0].BaseCoverage.glyphs)


def test_anchor_loose_letters_skips_what_takes_no_accent():
    """A symbol outside the Latin layer's spacing characters (an arrow)
    gets no anchor; the ASCII period does (anchors.accent_bases)."""
    marks = {"acute": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        {**_HEIGHTS, "arrow": 100, "acute": 100},
        _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x2190: "arrow"}),
        [_edge_markbase(marks, _HEIGHTS, 20, top=True)])
    assert anchors.anchor_loose_letters(font) == 0
    font = _drawn_gpos_font(
        {**_HEIGHTS, "period": 100, "acute": 100},
        _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x2E: "period"}),
        [_edge_markbase(marks, _HEIGHTS, 20, top=True)])
    assert anchors.anchor_loose_letters(font) == 1


def test_accent_bases_excludes_space_and_out_of_range_letters():
    """The boundary decisions, not what gets in (that is covered above
    through anchor_loose_letters): U+0020 SPACE is category Zs and below
    the ASCII/Latin-1 branch's 0x21 floor, excluded on both counts; a
    CJK ideograph (U+4E00, category Lo -- a letter by unicodedata) sits
    in none of LETTER_RANGES, which is exactly the point of keying off
    ranges rather than category alone -- LETTER_RANGES's own comment
    says a JP face maps 17,000 such kanji "letters" that take no accent;
    and U+037E GREEK QUESTION MARK falls inside LETTER_RANGES numerically
    but is category Po, not a letter, and sits above 0xFF so the
    ASCII/Latin-1 branch does not rescue it either."""
    cmap = {0x41: "A", 0x20: "space", 0x4E00: "cjk", 0x37E: "greekq"}
    assert anchors.accent_bases(cmap) == {"A"}


def test_import_donor_base_anchors_moves_the_anchor_with_the_outline():
    marks = {"acute": (0, _anchor(0, 0))}
    ours = _GposFont([_markbase(marks, {"z": [_anchor(300, 700)]})],
                     {0x0301: "acute", ord("z"): "z"},
                     [".notdef", "acute", "alpha", "z"])
    theirs = _GposFont([_markbase(marks, {"donor_alpha": [_anchor(400, 500)]})],
                       {0x0301: "acute"}, [".notdef", "acute", "donor_alpha"])

    added = anchors.import_donor_base_anchors(
        ours, theirs, {"donor_alpha": ["alpha"]}, {"alpha": (0.5, 20)})

    assert added == 1
    sub = ours["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    # sorted by glyph id: alpha (2) before z (3), not appended at the end
    assert sub.BaseCoverage.glyphs == ["alpha", "z"]
    assert sub.BaseArray.BaseCount == 2
    got = sub.BaseArray.BaseRecord[0].BaseAnchor[0]
    assert (got.XCoordinate, got.YCoordinate) == (220, 500)   # 400*0.5 + 20
    assert got.Format == 1
    assert sub.BaseArray.BaseRecord[1].BaseAnchor[0].XCoordinate == 300


def test_import_donor_base_anchors_leaves_a_base_the_face_already_has():
    marks = {"acute": (0, _anchor(0, 0))}
    ours = _GposFont([_markbase(marks, {"alpha": [_anchor(300, 700)]})],
                     {0x0301: "acute"}, [".notdef", "acute", "alpha"])
    theirs = _GposFont([_markbase(marks, {"donor_alpha": [_anchor(9, 9)]})],
                       {0x0301: "acute"}, [".notdef", "acute", "donor_alpha"])
    assert anchors.import_donor_base_anchors(
        ours, theirs, {"donor_alpha": ["alpha"]}, {}) == 0
    sub = ours["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    assert sub.BaseArray.BaseRecord[0].BaseAnchor[0].XCoordinate == 300


def test_import_donor_base_anchors_serves_every_codepoint_one_glyph_draws():
    """Source Sans draws U+03C6 and U+03D5 with a single 'phi', so the
    map from donor glyph to ours is one-to-many. Keyed the other way it
    kept the last codepoint only, and phi -- the Greek letter a
    programmer is likeliest to type -- took its accent at offset 0,
    a cell and a half to the right, on top of the next character."""
    marks = {"acute": (0, _anchor(0, 0))}
    ours = _GposFont([_markbase(marks, {})],
                     {0x0301: "acute", 0x03C6: "phi", 0x03D5: "phi_symbol"},
                     [".notdef", "acute", "phi", "phi_symbol"])
    theirs = _GposFont([_markbase(marks, {"donor_phi": [_anchor(300, 500)]})],
                       {0x0301: "acute"}, [".notdef", "acute", "donor_phi"])

    added = anchors.import_donor_base_anchors(
        ours, theirs, {"donor_phi": ["phi", "phi_symbol"]},
        {"phi": (1.0, 0), "phi_symbol": (1.0, 0)})

    assert added == 2
    sub = ours["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    assert sub.BaseCoverage.glyphs == ["phi", "phi_symbol"]


# --- import_donor_decompositions -------------------------------------------

class _GsubFont:
    """A GSUB whose 'ccmp' names `feature` (every lookup by default),
    plus a cmap and a glyph order."""

    def __init__(self, lookups, cmap, feature=None, glyph_order=None):
        table = otTables.GSUB()
        table.LookupList = _FakeLookupList(lookups)
        named = list(range(len(lookups))) if feature is None else list(feature)
        fr = FakeFeatureRecord("ccmp", FakeFeature(named))
        table.FeatureList = FakeFeatureList([fr])
        table.ScriptList = FakeScriptList([])
        self._tables = {"GSUB": FakeTable(table)}
        self._cmap = dict(cmap)
        self._order = list(glyph_order or sorted(cmap.values()))

    def __contains__(self, key):
        return key in self._tables

    def __getitem__(self, key):
        return self._tables[key]

    def getBestCmap(self):
        return self._cmap

    def getGlyphID(self, name):
        return self._order.index(name)


def _multiple(mapping):
    st = otTables.MultipleSubst()
    st.Format, st.mapping = 1, dict(mapping)
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag, lk.SubTable = 2, 0, [st]
    lk.SubTableCount = 1
    return lk


def _chain(inputs, lookahead, callee, backtrack=()):
    """A format-3 chain context calling `callee` at the input glyph."""
    st = otTables.ChainContextSubst()
    st.Format = 3
    st.BacktrackCoverage = [_coverage(c) for c in backtrack]
    st.BacktrackGlyphCount = len(st.BacktrackCoverage)
    st.InputCoverage = [_coverage(inputs)]
    st.InputGlyphCount = 1
    st.LookAheadCoverage = [_coverage(c) for c in lookahead]
    st.LookAheadGlyphCount = len(st.LookAheadCoverage)
    rec = otTables.SubstLookupRecord()
    st.SubstLookupRecord = [rec]
    rec.SequenceIndex, rec.LookupListIndex = 0, callee
    st.SubstCount = 1
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag, lk.SubTable = 6, 0, [st]
    lk.SubTableCount = 1
    return lk


def _yi_donor(feature=(1,)):
    """The shape Source Sans actually ships: the decomposition is a
    callee, and only the chain that names a following acute is in ccmp."""
    return _GsubFont([_multiple({"yi": ["dotlessi", "diaeresis"]}),
                      _chain(["yi"], [["acute"]], 0)],
                     {0x0131: "dotlessi", 0x0308: "diaeresis",
                      0x0457: "yi", 0x0301: "acute"},
                     feature=feature)


def _yi_face(**cmap):
    base = {0x0131: "our_dotlessi", 0x0308: "our_diaeresis",
            0x0457: "our_yi", 0x0301: "our_acute"}
    base.update(cmap)
    return _GsubFont([_single({"a": "b"})], base)


def test_import_donor_decompositions_keeps_the_donor_condition():
    """The letter comes apart into glyphs the face already has at the
    same codepoints -- but only where the donor takes it apart, which is
    before a combining acute and nowhere else."""
    ours, theirs = _yi_face(), _yi_donor()

    assert anchors.import_donor_decompositions(
        ours, theirs, {"yi": ["our_yi"]}) == 1

    table = ours["GSUB"].table
    # at the front, because a shaper runs a stage in LookupList order and
    # this has to happen before the marks are composed
    chain, multi = table.LookupList.Lookup[0], table.LookupList.Lookup[1]
    assert (chain.LookupType, multi.LookupType) == (6, 2)
    assert multi.SubTable[0].mapping == {
        "our_yi": ["our_dotlessi", "our_diaeresis"]}
    st = chain.SubTable[0]
    assert st.InputCoverage[0].glyphs == ["our_yi"]
    assert [c.glyphs for c in st.LookAheadCoverage] == [["our_acute"]]
    assert st.SubstLookupRecord[0].LookupListIndex == 1      # the multi
    # the lookup that was there is renumbered, and ccmp names the chain
    # alone: naming the substitution is what strips the condition
    assert table.LookupList.Lookup[2].LookupType == 1
    assert table.FeatureList.FeatureRecord[0].Feature.LookupListIndex == [0, 2]


def test_import_donor_decompositions_drops_a_rule_no_context_reaches():
    """The regression this guards: copied unconditionally, every bare
    Ukrainian yi in ordinary text was replaced by the Latin dotless i --
    a different letterform, 23% wider in the ink -- plus a floating
    diaeresis, and the yi we had just imported was never reached."""
    ours = _yi_face()
    theirs = _GsubFont([_multiple({"yi": ["dotlessi", "diaeresis"]})],
                       {0x0131: "dotlessi", 0x0308: "diaeresis",
                        0x0457: "yi", 0x0301: "acute"})
    assert anchors.import_donor_decompositions(
        ours, theirs, {"yi": ["our_yi"]}) == 0
    assert len(ours["GSUB"].table.LookupList.Lookup) == 1     # nothing added


def test_import_donor_decompositions_drops_a_context_it_cannot_reproduce():
    """A lookahead we have no glyph for cannot be narrowed away -- the
    rule would fire everywhere instead of before that one mark."""
    ours = _yi_face()
    del ours._cmap[0x0301]                       # no acute in this face
    assert anchors.import_donor_decompositions(
        ours, _yi_donor(), {"yi": ["our_yi"]}) == 0
    assert len(ours["GSUB"].table.LookupList.Lookup) == 1


def test_import_donor_decompositions_leaves_a_rule_we_cannot_resolve():
    """An output the face has no glyph for would have to be grafted, and
    grafting a mark means guessing at its advance and its anchors."""
    ours = _GsubFont([], {0x0457: "our_yi", 0x0301: "our_acute"})
    assert anchors.import_donor_decompositions(
        ours, _yi_donor(), {"yi": ["our_yi"]}) == 0
    assert ours["GSUB"].table.LookupList.Lookup == []


def test_import_donor_decompositions_ignores_a_letter_we_did_not_import():
    ours = _GsubFont([], {0x0131: "our_dotlessi", 0x0308: "our_diaeresis"})
    theirs = _GsubFont([_multiple({"yi": ["dotlessi", "diaeresis"]})],
                       {0x0131: "dotlessi", 0x0308: "diaeresis", 0x0457: "yi"})
    assert anchors.import_donor_decompositions(ours, theirs, {}) == 0


# --- the marks' side of the anchor gap, and the stacked-accent lift ------

def _gdef_marks(font, marks):
    """A GDEF filing `marks` as marks (class 3) on a font that has none."""
    from fontTools.ttLib import newTable
    gdef = newTable("GDEF")
    gdef.table = otTables.GDEF()
    gdef.table.Version = 0x00010000
    gdef.table.GlyphClassDef = otTables.GlyphClassDef()
    gdef.table.GlyphClassDef.classDefs = {g: 3 for g in marks}
    gdef.table.AttachList = gdef.table.LigCaretList = None
    gdef.table.MarkAttachClassDef = gdef.table.MarkGlyphSetsDef = None
    font["GDEF"] = gdef


def _sixteen_marks(anchor=(50, 0)):
    return {f"m{i}": (0, _anchor(*anchor)) for i in range(16)}


def test_anchor_loose_marks_gives_an_uncovered_mark_the_lookups_anchor():
    """Source Code Pro Italic leaves the candrabindu out of the lookup
    the upright has it in, so on every italic face it landed a cell to
    the right of its letter. Within a lookup the donor gives every
    mark one anchor; the median is what the missing one gets, in the
    lookup whose marks' ink sits where its own does. A mark drawn far
    from any lookup's marks (an overlay, a mark below) gets nothing
    from a lookup of above-marks, and a double diacritic is not a mark
    to place on one base."""
    marks = _sixteen_marks()
    heights = {**_HEIGHTS, **dict.fromkeys(marks, 100),
               "candra": 100, "tall": 800, "dbl": 100}
    cmap = _letters_cmap(_HEIGHTS, {0x0300 + i: g for i, g in enumerate(marks)})
    cmap |= {0x0310: "candra", 0x0334: "tall", 0x035F: "dbl"}
    font = _drawn_gpos_font(heights, cmap,
                            [_markbase(marks, {g: [_anchor(50, h + 20)]
                                               for g, h in _HEIGHTS.items()})])
    _gdef_marks(font, [*marks, "candra", "tall", "dbl"])

    assert anchors.anchor_loose_marks(font) == 1
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    assert "candra" in sub.MarkCoverage.glyphs
    assert "tall" not in sub.MarkCoverage.glyphs and "dbl" not in sub.MarkCoverage.glyphs
    assert sub.MarkCoverage.glyphs == sorted(sub.MarkCoverage.glyphs, key=font.getGlyphID)
    rec = sub.MarkArray.MarkRecord[sub.MarkCoverage.glyphs.index("candra")]
    assert (rec.Class, rec.MarkAnchor.XCoordinate, rec.MarkAnchor.YCoordinate) == (0, 50, 0)
    assert sub.MarkArray.MarkCount == len(sub.MarkCoverage.glyphs)


def test_anchor_loose_marks_needs_a_lookup_big_enough_to_speak_for_a_mark():
    """Five marks are a donor's special case, not a rule to extend."""
    marks = {f"m{i}": (0, _anchor(50, 0)) for i in range(5)}
    heights = {**_HEIGHTS, **dict.fromkeys(marks, 100), "candra": 100}
    cmap = _letters_cmap(_HEIGHTS, {0x0300 + i: g for i, g in enumerate(marks)})
    cmap |= {0x0310: "candra"}
    font = _drawn_gpos_font(heights, cmap,
                            [_markbase(marks, {g: [_anchor(50, h + 20)]
                                               for g, h in _HEIGHTS.items()})])
    _gdef_marks(font, [*marks, "candra"])
    assert anchors.anchor_loose_marks(font) == 0


def _markmark(mark1, mark2):
    """One MarkMarkPos: {mark: (class, anchor)} stacking on {mark: [anchors]}."""
    st = otTables.MarkMarkPos()
    st.Format = 1
    st.ClassCount = 1
    st.Mark1Coverage = otTables.Mark1Coverage()
    st.Mark1Coverage.glyphs = list(mark1)
    st.Mark1Array = otTables.Mark1Array()
    st.Mark1Array.MarkRecord = []
    for cls, anc in mark1.values():
        rec = otTables.MarkRecord()
        rec.Class, rec.MarkAnchor = cls, anc
        st.Mark1Array.MarkRecord.append(rec)
    st.Mark2Coverage = otTables.Mark2Coverage()
    st.Mark2Coverage.glyphs = list(mark2)
    st.Mark2Array = otTables.Mark2Array()
    st.Mark2Array.Mark2Record = []
    for anchor_list in mark2.values():
        rec = otTables.Mark2Record()
        rec.Mark2Anchor = list(anchor_list)
        st.Mark2Array.Mark2Record.append(rec)
    st.Mark2Array.MarkCount = len(mark2)
    lk = otTables.Lookup()
    lk.LookupType, lk.LookupFlag, lk.SubTable = 6, 0, [st]
    lk.SubTableCount = 1
    return lk


def _mkmk_font(stack):
    """A font whose one mkmk lookup stacks grave and acute on each
    other: {mark: (Mark1 y, Mark2 y)}."""
    cmap = {0x0300: "grave", 0x0301: "acute"}
    font = _GposFont([_markmark({g: (0, _anchor(50, y1)) for g, (y1, _) in stack.items()},
                                {g: [_anchor(50, y2)] for g, (_, y2) in stack.items()})],
                     cmap, [".notdef", "grave", "acute"])
    font["GPOS"].table.FeatureList.FeatureRecord[0].FeatureTag = "mkmk"
    return font


def _mark2_y(font, name):
    st = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    return st.Mark2Array.Mark2Record[st.Mark2Coverage.glyphs.index(name)].Mark2Anchor[0].YCoordinate


def test_mirror_stack_lift_copies_the_uprights_lift_onto_a_collapsed_anchor():
    """Source Code Pro Italic's grave carries its Mark2 anchor at the
    height its own Mark1 attaches at, so a second accent stacks ON it;
    the upright lifts the second by 111 at Regular. The italic takes
    that lift. A mark whose Mark2 already differs from its Mark1 is the
    designer's and stays."""
    ours = _mkmk_font({"grave": (500, 500), "acute": (500, 640)})
    model = _mkmk_font({"grave": (500, 611), "acute": (500, 700)})
    assert anchors.mirror_stack_lift(ours, model) == 1
    assert _mark2_y(ours, "grave") == 611
    assert _mark2_y(ours, "acute") == 640


def test_mirror_stack_lift_leaves_what_the_model_does_not_lift():
    """At wght 200 the upright collapses too; there is nothing to copy."""
    ours = _mkmk_font({"grave": (500, 500), "acute": (500, 500)})
    model = _mkmk_font({"grave": (500, 500), "acute": (500, 500)})
    assert anchors.mirror_stack_lift(ours, model) == 0
    assert _mark2_y(ours, "grave") == 500


def _with_gsub(font, fea):
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    addOpenTypeFeaturesFromString(font, fea, tables=["GSUB"])
    return font


def test_letter_variants_follows_single_and_alternate_substitutions_two_steps():
    """The shaper substitutes before it positions: an accent on a letter
    locl has swapped attaches to the substitute."""
    heights = {"a": 500, "a.srb": 500, "a.srb2": 500, "b": 500, "b.alt": 500, "c": 500}
    font = _cff_font_with_heights(heights)
    font["cmap"].tables[0].cmap = {0x61: "a", 0x62: "b", 0x63: "c"}
    _with_gsub(font, "feature locl { sub a by a.srb; } locl;\n"
                     "feature ss01 { sub a.srb by a.srb2; } ss01;\n"
                     "feature salt { sub b from [b.alt]; } salt;\n")
    assert anchors._letter_variants(font, {"a", "b", "c"}) == {"a.srb", "a.srb2", "b.alt"}


def test_anchor_loose_letters_covers_what_gsub_makes_of_a_letter():
    """The Serbian locl б was in no BaseCoverage, so under `sr` an
    accent on it landed a cell right, on the next character."""
    heights = {**_HEIGHTS, "z": 500, "z.srb": 520, "acute": 100}
    marks = {"acute": (0, _anchor(0, 0))}
    font = _drawn_gpos_font(
        heights, _letters_cmap(_HEIGHTS, {0x0301: "acute", 0x7A: "z"}),
        [_edge_markbase(marks, _HEIGHTS, 20, top=True)])
    _with_gsub(font, "feature locl { sub z by z.srb; } locl;\n")
    assert anchors.anchor_loose_letters(font) == 2
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    got = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index("z.srb")].BaseAnchor[0]
    assert (got.XCoordinate, got.YCoordinate) == (50, 540)


def test_round_outlines_merges_the_overlaps_the_instancer_leaves():
    """A variable font's masters keep overlapping contours; the static
    faces drew 300 letters with them, and FreeType rendered a seam at
    each join. Two overlapping squares come out as one outline of
    their union's area."""
    import build_latin
    from fontTools.pens.areaPen import AreaPen
    font = _cff_font_with_heights({"a": 100})
    pen = T2CharStringPen(0, None)
    for x0 in (0, 50):
        pen.moveTo((x0, 0))
        pen.lineTo((x0 + 100, 0))
        pen.lineTo((x0 + 100, 100))
        pen.lineTo((x0, 100))
        pen.closePath()
    td = font["CFF "].cff.topDictIndex[0]
    td.CharStrings["a"] = pen.getCharString(private=td.Private)
    build_latin.round_outlines(font)
    area = AreaPen(font.getGlyphSet())
    font.getGlyphSet()["a"].draw(area)
    assert abs(area.value) == 150 * 100
    assert font["hmtx"].metrics["a"] == (600, 0)


def test_anchor_loose_marks_keeps_every_other_marks_anchor_across_two_insertions():
    """The second insertion once paired a record list kept from before
    the first with the fresh coverage, one off: the italic's caron took
    the .cap anchor and drew through b's ascender."""
    marks = _sixteen_marks()
    marks["hi0"] = (0, _anchor(50, 180))       # a higher-drawn mark, its own anchor
    heights = {**_HEIGHTS, **dict.fromkeys(marks, 100), "hi0": 300,
               "candra": 100, "candra.cap": 300}
    cmap = _letters_cmap(_HEIGHTS, {0x0300 + i: g for i, g in enumerate(marks)})
    cmap |= {0x0310: "candra"}
    font = _drawn_gpos_font(heights, cmap,
                            [_markbase(marks, {g: [_anchor(50, h + 20)]
                                               for g, h in _HEIGHTS.items()})])
    _gdef_marks(font, [*marks, "candra", "candra.cap"])
    _with_gsub(font, "feature ccmp { sub candra by candra.cap; } ccmp;\n")
    before = {g: (r.MarkAnchor.XCoordinate, r.MarkAnchor.YCoordinate)
              for g, r in zip(*[(s.MarkCoverage.glyphs, s.MarkArray.MarkRecord)
                                for s in [font["GPOS"].table.LookupList.Lookup[0].SubTable[0]]][0])}
    assert anchors.anchor_loose_marks(font) == 2
    sub = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    after = {g: (r.MarkAnchor.XCoordinate, r.MarkAnchor.YCoordinate)
             for g, r in zip(sub.MarkCoverage.glyphs, sub.MarkArray.MarkRecord)}
    assert all(after[g] == a for g, a in before.items())
    assert after["candra"] == (50, 0) and after["candra.cap"] == (50, 180)


def test_letter_variants_reach_a_lookup_only_a_chain_context_calls():
    """The .cap forms of the marks come out of lookups no feature lists
    (ccmp chains to them): with no feature filter every lookup is
    walked; with the default filter, ccmp's are not letter variants."""
    heights = {"a": 500, "a.cap": 500, "b": 500}
    font = _cff_font_with_heights(heights)
    font["cmap"].tables[0].cmap = {0x61: "a", 0x62: "b"}
    _with_gsub(font, "lookup CAP { sub a by a.cap; } CAP;\n"
                     "feature ccmp { sub b a' lookup CAP; } ccmp;\n")
    assert anchors._letter_variants(font, {"a"}, features=None) == {"a.cap"}
    assert anchors._letter_variants(font, {"a"}) == set()


def test_anchor_loose_marks_leaves_a_mark_no_covered_mark_is_drawn_beside():
    """Within the lookup's band but with no covered mark within `near`
    of its own height, the mark has no anchor to take and is left."""
    marks = _sixteen_marks()
    heights = {**_HEIGHTS, **dict.fromkeys(marks, 100), "odd": 300}
    cmap = _letters_cmap(_HEIGHTS, {0x0300 + i: g for i, g in enumerate(marks)})
    cmap |= {0x0310: "odd"}
    font = _drawn_gpos_font(heights, cmap,
                            [_markbase(marks, {g: [_anchor(50, h + 20)]
                                               for g, h in _HEIGHTS.items()})])
    _gdef_marks(font, [*marks, "odd"])
    assert anchors.anchor_loose_marks(font) == 0


def test_mirror_stack_lift_skips_a_mark_whose_classes_differ_from_the_models():
    ours = _mkmk_font({"grave": (500, 500)})
    model = _mkmk_font({"grave": (500, 611)})
    st = model["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    st.Mark2Array.Mark2Record[0].Mark2Anchor.append(_anchor(50, 700))
    assert anchors.mirror_stack_lift(ours, model) == 0
    assert _mark2_y(ours, "grave") == 500


def test_raise_marks_after_capitals_adds_every_capital_to_the_swap_context():
    """The donor's ccmp names the capitals after which an above-mark is
    swapped for its raised form; the italic named the Latin ones only.
    Every cmapped capital of the Latin scripts joins the backtrack of
    the chain context that calls the swap (a class of twenty capitals
    or more, calling a lookup that takes the encoded marks to unencoded
    forms); a lowercase letter does not."""
    caps = [f"C{i}" for i in range(20)]
    marks = [f"m{i}" for i in range(20)]
    heights = {**dict.fromkeys(caps, 700), "Alpha": 700, "Be": 700, "a": 500,
               "acute.cap": 500, **dict.fromkeys(marks, 500)}
    font = _cff_font_with_heights(heights)
    font["cmap"].tables[0].cmap = {**{0x41 + i: g for i, g in enumerate(caps)},
                                   0x391: "Alpha", 0x411: "Be", 0x61: "a",
                                   **{0x300 + i: g for i, g in enumerate(marks)}}
    _with_gsub(font, "lookup CAP { " + " ".join(f"sub {m} by acute.cap;" for m in marks)
               + " } CAP;\nfeature ccmp { sub [" + " ".join(caps) + "] ["
               + " ".join(marks) + "]' lookup CAP; } ccmp;\n")
    assert anchors.raise_marks_after_capitals(font) == 2
    gsub = font["GSUB"].table
    chain = [st for lk in gsub.LookupList.Lookup for st in lk.SubTable
             if lk.LookupType == 6][0]
    back = set(chain.BacktrackCoverage[0].glyphs)
    assert {"Alpha", "Be", *caps} <= back and "a" not in back
    assert chain.BacktrackCoverage[0].glyphs == sorted(back, key=font.getGlyphID)
    assert anchors.raise_marks_after_capitals(font) == 0


def test_add_feature_where_gives_an_unnamed_language_the_script_default():
    """Source Han Sans keeps a Japanese LangSys under every script; the
    donor's locl names grek/dflt only. A LangSys is complete -- nothing
    cascades to it -- so grek/JAN must get the default list too, or a
    shaper told the text is Japanese sets the Latin acute on beta."""
    class FakeLangSysRecord:
        def __init__(self, tag, langsys):
            self.LangSysTag = tag
            self.LangSys = langsys
    default, japanese, serbian = FakeLangSys([]), FakeLangSys([]), FakeLangSys([])
    script = FakeScript(default, [FakeLangSysRecord("JAN ", japanese),
                                  FakeLangSysRecord("SRB ", serbian)])
    record = FakeScriptRecord(script)
    record.ScriptTag = "cyrl"
    gsub = FakeGSUB([], [record])
    build._add_feature_where(gsub, "locl", {("cyrl", None): [5], ("cyrl", "SRB "): [5, 6]})
    records = gsub.FeatureList.FeatureRecord

    def reach(ls):
        return [records[i].Feature.LookupListIndex for i in ls.FeatureIndex]
    assert reach(default) == [[5]]
    assert reach(japanese) == [[5]]        # the default, not nothing
    assert reach(serbian) == [[5, 6]]      # its own, as named


def test_prune_orphan_features_drops_what_no_langsys_names_and_remaps():
    records = [FakeFeatureRecord(tag, FakeFeature([i])) for i, tag in enumerate(("aalt", "locl", "mark"))]
    default = FakeLangSys([0, 2])
    default.ReqFeatureIndex = 0xFFFF
    script = FakeScript(default)
    gsub = FakeGSUB(records, [FakeScriptRecord(script)])
    assert build.prune_orphan_features(gsub) == 1
    assert [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord] == ["aalt", "mark"]
    assert default.FeatureIndex == [0, 1] and default.FeatureCount == 2
    assert build.prune_orphan_features(gsub) == 0


def test_add_feature_where_leaves_no_orphan_record():
    """The base's own locl record, swapped out of every LangSys, goes."""
    old = FakeFeatureRecord("locl", FakeFeature([1]))
    default = FakeLangSys([0])
    default.ReqFeatureIndex = 0xFFFF
    record = FakeScriptRecord(FakeScript(default))
    record.ScriptTag = "grek"
    gsub = FakeGSUB([old], [record])
    build._add_feature_where(gsub, "locl", {("grek", None): [5]})
    assert [fr.Feature.LookupListIndex for fr in gsub.FeatureList.FeatureRecord] == [[1, 5]]
    assert default.FeatureIndex == [0]


def test_prune_orphan_lookups_roots_at_the_langsys_not_the_feature_list():
    """A FeatureRecord no LangSys names is no route to its lookups."""
    gsub = _gsub_with([_single({"a": "b"}), _single({"c": "d"})], [0])
    gsub.FeatureList.FeatureRecord.append(FakeFeatureRecord("locl", FakeFeature([1])))
    gsub.FeatureList.FeatureCount = 2
    font = {"GSUB": FakeTable(gsub)}
    assert build.prune_orphan_lookups(font) == {"GSUB": 1}
    assert gsub.FeatureList.FeatureRecord[1].Feature.LookupListIndex == []
