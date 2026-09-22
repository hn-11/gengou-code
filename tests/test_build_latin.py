"""Unit tests for scripts/build_latin.py that need no font files.

build_latin.py no longer cuts the Latin layer out of the 35 faces; it
assembles Gengou from the Source Code Pro and Monaspace variable
fonts directly (see the module docstring). These tests cover the pure
logic left behind: zone-order repair on a CFF FDArray, the typo/win
metrics helpers, the pinned Latin win metrics, donor credits, the SCP
stylistic-set remap, and the two weight profiles / constants.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402
import build_latin  # noqa: E402
import test_build as tb  # noqa: E402 -- reuse its GSUB fakes
from conftest import make_cff_font, make_font  # noqa: E402

# --- fix_zone_order -------------------------------------------------------

class _FakeTopDict:
    def __init__(self, fdarray):
        self.FDArray = fdarray


class _FakeCFF:
    def __init__(self, fdarray, font_name="X"):
        self.fontNames = [font_name]
        self._top_dict = _FakeTopDict(fdarray)

    def __getitem__(self, name):
        return self._top_dict


class _FakeCFFTable:
    def __init__(self, cff):
        self.cff = cff


def _zone_font(*privates):
    """A fake CID-keyed CFF font: one FontDict per Private given."""
    fdarray = [SimpleNamespace(Private=p) for p in privates]
    return {"CFF ": _FakeCFFTable(_FakeCFF(fdarray))}


def test_fix_zone_order_sorts_an_inverted_pair():
    private = SimpleNamespace(OtherBlues=[-217, -222])
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.OtherBlues == [-222, -217]


def test_fix_zone_order_sorts_pairs_out_of_order_and_within_a_pair():
    # (486, 490) is already ascending, (-12, 0) is fine, but (582, 566) is
    # inverted and the three pairs are not sorted by first value
    private = SimpleNamespace(BlueValues=[486, 490, -12, 0, 582, 566])
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.BlueValues == [-12, 0, 486, 490, 566, 582]


def test_fix_zone_order_leaves_none_and_missing_attributes_alone():
    private = SimpleNamespace(OtherBlues=[-217, -222], FamilyBlues=None)
    # FamilyOtherBlues is not set on this Private at all
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.FamilyBlues is None
    assert not hasattr(private, "FamilyOtherBlues")


def test_fix_zone_order_leaves_empty_list_alone():
    private = SimpleNamespace(BlueValues=[])
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.BlueValues == []


def test_fix_zone_order_covers_every_fontdict():
    p0 = SimpleNamespace(OtherBlues=[-217, -222])
    p1 = SimpleNamespace(OtherBlues=[10, 5])
    font = _zone_font(p0, p1)

    build_latin.fix_zone_order(font)

    assert p0.OtherBlues == [-222, -217]
    assert p1.OtherBlues == [5, 10]


# --- typo / win metrics ---------------------------------------------------

def _metrics_font(ascent=800, descent=-200, line_gap=0,
                  win_ascent=0, win_descent=0):
    return make_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600},
                     ascent=ascent, descent=descent, line_gap=line_gap,
                     os2={"usWinAscent": win_ascent, "usWinDescent": win_descent})


def test_use_typo_metrics_matches_hhea_and_sets_fsselection_bit7():
    # SCP-shaped mismatch: hhea 984/-273, typo starts out somewhere else
    font = _metrics_font(ascent=984, descent=-273, line_gap=50)
    font["OS/2"].sTypoAscender = 750
    font["OS/2"].sTypoDescender = -250
    font["OS/2"].sTypoLineGap = 0
    font["OS/2"].fsSelection = 0x40   # regular, bit 7 not yet set

    build_latin.use_typo_metrics(font)

    os2, hhea = font["OS/2"], font["hhea"]
    assert (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap) == (
        hhea.ascent, hhea.descent, hhea.lineGap)
    assert os2.fsSelection & 0x80
    assert os2.fsSelection & 0x40   # untouched bits survive


def test_pin_win_metrics_sets_the_pinned_pair():
    font = _metrics_font(win_ascent=10, win_descent=10)
    font["head"].yMax = 20
    font["head"].yMin = -20

    build_latin.pin_win_metrics(font)

    os2 = font["OS/2"]
    assert (os2.usWinAscent, os2.usWinDescent) == build_latin.LATIN_WIN_METRICS


def test_pin_win_metrics_overwrites_whatever_the_face_already_declared():
    # a face that came in already covering more than the pin: pinning
    # brings it down rather than taking the max, the way fit_win_metrics
    # used to
    font = _metrics_font(win_ascent=2000, win_descent=2000)
    font["head"].yMax = 100
    font["head"].yMin = -100

    build_latin.pin_win_metrics(font)

    os2 = font["OS/2"]
    assert (os2.usWinAscent, os2.usWinDescent) == build_latin.LATIN_WIN_METRICS


def test_pin_win_metrics_raises_naming_the_extents_when_ascent_is_exceeded():
    font = _metrics_font(win_ascent=0, win_descent=0)
    font["head"].yMax = 1061
    font["head"].yMin = -100

    with pytest.raises(RuntimeError, match="1061"):
        build_latin.pin_win_metrics(font)


def test_pin_win_metrics_raises_naming_the_extents_when_descent_is_exceeded():
    font = _metrics_font(win_ascent=0, win_descent=0)
    font["head"].yMax = 100
    font["head"].yMin = -455

    with pytest.raises(RuntimeError, match="455"):
        build_latin.pin_win_metrics(font)


# --- credits_from ---------------------------------------------------------

class _FakeName:
    def __init__(self, names):
        self._names = names

    def getDebugName(self, name_id):
        return self._names.get(name_id)


def _donor(names):
    return {"name": _FakeName(names)}


def test_credits_from_returns_scp_then_monaspace():
    scp = _donor({0: "SCP Copyright", 9: "Paul D. Hunt, Teo Tuominen"})
    mona = _donor({0: "Mona Copyright", 9: "Riley Cran"})

    credits = build_latin.credits_from(("Source Code Pro", scp), ("Monaspace", mona))

    assert credits == [
        ("Source Code Pro", "SCP Copyright", "Paul D. Hunt, Teo Tuominen"),
        ("Monaspace", "Mona Copyright", "Riley Cran"),
    ]


def test_credits_from_monaspace_falls_back_to_nameid7_when_nameid0_absent():
    scp = _donor({0: "SCP Copyright", 9: "Paul D. Hunt"})
    mona = _donor({0: None, 7: "Trademark: Monaspace", 9: "Riley Cran"})

    credits = build_latin.credits_from(("Source Code Pro", scp), ("Monaspace", mona))

    label, copyright_, designer = credits[1]
    assert label == "Monaspace"
    assert copyright_ == "Trademark: Monaspace"
    assert designer == "Riley Cran"


# --- remap_scp_stylistic_sets ---------------------------------------------

def test_remap_scp_stylistic_sets_shifts_ss_and_sorts_the_feature_list():
    tags_in = ("ss01", "ss03", "cv01", "zero", "calt")
    records = [tb.FakeFeatureRecord(tag, tb.FakeFeature([]))
               for tag in tags_in]
    ls = tb.FakeLangSys(list(range(len(records))))
    gsub = tb.FakeGSUB(records, [tb.FakeScriptRecord(tb.FakeScript(ls))])
    font = {"GSUB": tb.FakeTable(gsub)}

    build_latin.remap_scp_stylistic_sets(font)

    tags_out = [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord]
    assert tags_out == ["calt", "cv01", "ss11", "ss13", "zero"]
    assert tags_out == sorted(tags_out)
    # every record is still reachable from the LangSys, just renumbered
    assert ls.FeatureCount == len(records)
    assert set(ls.FeatureIndex) == set(range(len(records)))


# --- the family --------------------------------------------------------------

def test_family_is_the_latin_family_build_reads_back():
    assert (build_latin.FAMILY, build_latin.PS_FAMILY) == build.LATIN_FAMILY
    assert build_latin.PS_FAMILY == "Gengou"


# --- CELL / MONA_K constants ----------------------------------------------

def test_cell_is_scp_cell():
    assert build_latin.CELL == 600
    assert build_latin.CELL == build.CELL


def test_mona_k_scales_from_scp_cell_to_monaspace_cell():
    assert build_latin.MONA_K == 600 / build.MONA_CELL


def test_fix_zone_order_rounds_the_zones_and_stems():
    """Instancing a CFF2 blends each zone edge on its own, and the build
    sorted them but never rounded them: eight of the ten static faces
    shipped blues like 733.9999999 and StdHW 115.33964. The spec stores
    these as integer deltas and a reader that truncates takes them a
    unit low, under the overshoot the zone is there to suppress."""
    private = SimpleNamespace(
        BlueValues=[-12.0, 0.4, 496.1008301, 582.0000001000001,
                    671.9999999, 733.9999999],
        OtherBlues=[-222.0, -196.076874],
        StdHW=115.33964, StdVW=147.76939,
        StemSnapH=[67.4, 115.33964], BlueScale=0.0375)
    font = _zone_font(private)

    build_latin.fix_zone_order(font)
    assert private.BlueValues == [-12, 0, 496, 582, 672, 734]
    assert private.OtherBlues == [-222, -196]
    assert (private.StdHW, private.StdVW) == (115, 148)
    assert private.StemSnapH == [67, 115]
    assert private.BlueScale == 0.0375     # the one real number, untouched


# --- add_missing_from_sans ------------------------------------------------

def _cff_with_greek(inks, *, cmap_extra=()):
    """A CFF font whose Greek glyphs are rectangles of the given ink
    widths, keyed by codepoint. 'A' comes along because append_context
    keys the FD and its Private dict off it."""
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    names = {cp: f"uni{cp:04X}" for cp in inks}
    order = [".notdef", "A", *names.values()]
    charstrings = {}
    for g, w in [("A", 400)] + [(names[cp], w) for cp, w in inks.items()]:
        pen = T2CharStringPen(0, None)
        pen.moveTo((10, 0))
        pen.lineTo((10 + w, 0))
        pen.lineTo((10 + w, 500))
        pen.closePath()
        charstrings[g] = pen.getCharString()
    charstrings[".notdef"] = T2CharStringPen(0, None).getCharString()
    font = make_cff_font(order, charstrings,
                         {ord("A"): "A", **{cp: names[cp] for cp in names},
                          **dict(cmap_extra)},
                         {g: (600, 0) for g in order})
    font.master = False          # what a VFSource instance carries (vfsource.Instance)
    return font


def test_add_missing_from_sans_takes_the_block_inside_the_upright_set():
    """Three rules at once: a codepoint the face already has is taken
    over anyway, so the block comes from one donor; one the upright
    faces do not draw is not taken even though the donor has it; and
    what is taken is one cell wide.

    The replacement is what fixes pi: Source Code Pro Italic draws it
    and does not anchor it, and leaving the face's own glyph in place
    left that one letter of the block behind its own donor."""
    face = _cff_with_greek({0x03B1: 300})              # alpha already drawn
    donor = _cff_with_greek({0x03B1: 300, 0x03B2: 700,
                             0x03B3: 300, 0x03B4: 300})
    before = face.getBestCmap()[0x03B1]
    added, condensed, anchors = build_latin.add_missing_from_sans(
        face, donor, {0x03B1, 0x03B2, 0x03B4})        # gamma withheld
    assert (added, condensed) == (3, 1)                # beta's 700 does not fit
    assert anchors == 0                                # this donor has no GPOS
    cmap = face.getBestCmap()
    assert 0x03B3 not in cmap                          # not in the upright set
    assert cmap[0x03B1] != before                      # the donor's now
    assert {cmap[0x03B1], cmap[0x03B2], cmap[0x03B4]} <= set(face.getGlyphOrder())
    for cp in (0x03B1, 0x03B2, 0x03B4):
        assert face["hmtx"].metrics[cmap[cp]][0] == build_latin.CELL


def test_add_missing_from_sans_seats_the_ink_in_the_cell():
    """What is added is centred, and condensed only as far as the cell
    less a bearing at each side — cell_fit's rule, reaching the glyph."""
    face = _cff_with_greek({})
    donor = _cff_with_greek({0x03B2: 700, 0x03B4: 300})
    build_latin.add_missing_from_sans(face, donor, {0x03B2, 0x03B4})
    cmap, gs = face.getBestCmap(), face.getGlyphSet()
    wide = build._bounds(gs, cmap[0x03B2])
    narrow = build._bounds(gs, cmap[0x03B4])
    bearing = build.LETTER_BEARING
    assert (round(wide[0]), round(wide[2])) == (bearing,
                                                build_latin.CELL - bearing)
    assert round(narrow[2] - narrow[0]) == 300         # not condensed
    assert round(narrow[0]) == round((build_latin.CELL - 300) / 2)
