"""Unit tests for scripts/verify.py (the single entry point that picks
a font's gate set from the font itself and runs it in its own process)
and the cheap, font-file-free pieces of scripts/verify_jp.py it
dispatches to."""

import importlib
import sys
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import verify  # noqa: E402
from conftest import make_font  # noqa: E402


def _import_verify_jp():
    """verify_jp.py reads sys.argv[1] into a module-level FONT at import
    time; pin argv for the one-time import so it does not pick up
    pytest's own, then restore it."""
    saved = sys.argv
    sys.argv = ["verify_jp.py"]
    try:
        return importlib.import_module("verify_jp")
    finally:
        sys.argv = saved


verify_jp = _import_verify_jp()

HIRAGANA_A = 0x3042


# --- gates_for: the dispatch ------------------------------------------------

def _vf_font():
    font = make_font([".notdef", "a"], {0x61: "a"}, {"a": 600})
    FontBuilder(font=font).setupFvar([("wght", 200, 400, 900, "Weight")], [])
    return font


def _jp_font():
    return make_font([".notdef", "a"], {HIRAGANA_A: "a"}, {"a": 600})


def _latin_font():
    return make_font([".notdef", "a"], {0x61: "a"}, {"a": 600})


def test_gates_for_sends_a_variable_font_to_verify_latin_vf(tmp_path):
    path = tmp_path / "Gengou[wght].otf"
    _vf_font().save(path)
    assert verify.gates_for(path) == "verify_latin_vf.py"


def test_gates_for_sends_a_font_that_draws_hiragana_to_verify_jp(tmp_path):
    path = tmp_path / "GengouJP-Regular.otf"
    _jp_font().save(path)
    assert verify.gates_for(path) == "verify_jp.py"


def test_gates_for_sends_everything_else_to_verify_latin(tmp_path):
    path = tmp_path / "Gengou-Regular.otf"
    _latin_font().save(path)
    assert verify.gates_for(path) == "verify_latin.py"


def test_gates_for_ignores_the_path_a_jp_font_under_a_latin_directory_still_gets_jp(tmp_path):
    """The rule this replaced was "'latin' somewhere in the path", which
    made dist/nerd/latin/ work by accident and would have handed a JP
    face dropped there the Latin gates. The answer is the font's own
    tables, not where it sits."""
    latin_dir = tmp_path / "latin"
    latin_dir.mkdir()
    path = latin_dir / "GengouJP-Regular.otf"
    _jp_font().save(path)
    assert verify.gates_for(path) == "verify_jp.py"


def test_gates_for_ignores_the_path_a_latin_font_outside_any_latin_directory_still_gets_latin(tmp_path):
    outside = tmp_path / "dist"
    outside.mkdir()
    path = outside / "Gengou-Regular.otf"
    _latin_font().save(path)
    assert verify.gates_for(path) == "verify_latin.py"


# --- main(): argument handling ----------------------------------------------

def test_main_a_missing_literal_path_names_the_font_not_a_silent_skip(monkeypatch):
    """A caller that names a face means that face verified; a silently
    dropped argument reported a missing one as a full pass -- which is
    how the release job, naming a single Nerd Fonts face, could have
    checked no patched face at all."""
    missing = "dist/NoSuchFace-Regular.otf"
    monkeypatch.setattr(sys, "argv", ["verify.py", missing])
    with pytest.raises(SystemExit) as exc:
        verify.main()
    assert missing in str(exc.value)


def test_main_a_pattern_matching_nothing_is_skipped_not_an_error(monkeypatch, tmp_path):
    real = tmp_path / "Gengou-Regular.otf"
    real.write_bytes(b"")
    seen = []
    monkeypatch.setattr(verify, "run",
                        lambda path: (seen.append(path), (path, "gate", 0, ""))[1])
    monkeypatch.setattr(sys, "argv",
                        ["verify.py", str(real), str(tmp_path / "*.nosuchext")])
    verify.main()          # no SystemExit: something else matched
    assert seen == [str(real)]


def test_main_nothing_matched_at_all_is_a_usage_error(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["verify.py", str(tmp_path / "*.nosuchext")])
    with pytest.raises(SystemExit) as exc:
        verify.main()
    assert "usage" in str(exc.value)


def test_main_takes_an_existing_bracketed_path_as_itself_not_a_pattern(monkeypatch, tmp_path):
    """Gengou[wght].otf is a character class matching nothing: naming one
    used to verify nothing silently. An existing path is taken as itself
    before it is read as a glob."""
    vf = tmp_path / "Gengou[wght].otf"
    vf.write_bytes(b"")
    seen = []
    monkeypatch.setattr(verify, "run",
                        lambda path: (seen.append(path), (path, "gate", 0, ""))[1])
    monkeypatch.setattr(sys, "argv", ["verify.py", str(vf)])
    verify.main()
    assert seen == [str(vf)]


def test_main_exits_nonzero_when_any_run_failed(monkeypatch, tmp_path):
    ok = tmp_path / "a.otf"
    ok.write_bytes(b"")
    bad = tmp_path / "b.otf"
    bad.write_bytes(b"")

    def fake_run(path):
        return path, "gate", (1 if path == str(bad) else 0), ""

    monkeypatch.setattr(verify, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["verify.py", str(ok), str(bad)])
    with pytest.raises(SystemExit) as exc:
        verify.main()
    assert exc.value.code != 0


def test_main_exits_zero_when_every_run_passed(monkeypatch, tmp_path):
    ok = tmp_path / "a.otf"
    ok.write_bytes(b"")
    monkeypatch.setattr(verify, "run", lambda path: (path, "gate", 0, ""))
    monkeypatch.setattr(sys, "argv", ["verify.py", str(ok)])
    verify.main()          # falls off the end: no SystemExit, exit code 0


# --- verify_jp.py: the pieces that need no whole font -----------------------

def _named_font(family, style):
    return make_font([".notdef", "a"], {0x61: "a"}, {"a": 600},
                     family=family, style=style)


def test_family_name_prefers_nameid_16_over_1():
    font = _named_font("Gengou JP", "Regular")
    assert verify_jp.family_name(font) == "Gengou JP"
    font["name"].setName("Gengou JP Term", 16, 3, 1, 0x409)
    assert verify_jp.family_name(font) == "Gengou JP Term"


def test_subfamily_name_prefers_nameid_17_over_2():
    font = _named_font("Gengou JP", "Bold")
    assert verify_jp.subfamily_name(font) == "Bold"
    font["name"].setName("SemiBold", 17, 3, 1, 0x409)
    assert verify_jp.subfamily_name(font) == "SemiBold"


def test_expected_metrics_defaults_for_the_base_family():
    font = _named_font("Gengou JP", "Regular")
    assert verify_jp.expected_metrics(font) == verify_jp.DEFAULT_METRICS


def test_expected_metrics_widens_the_term_family():
    font = _named_font("Gengou JP Term", "Regular")
    assert verify_jp.expected_metrics(font) == (600, 1200)


def test_expected_metrics_matches_term_as_a_whole_word_only():
    """FAMILY_METRICS is keyed by family-name tokens: 'Term' is a
    separate word in 'Gengou JP Term', never a substring of another
    word."""
    font = _named_font("Gengou JP Terminal", "Regular")
    assert verify_jp.expected_metrics(font) == verify_jp.DEFAULT_METRICS


def test_family_reference_asks_this_faces_own_family_not_gengoujp(tmp_path, monkeypatch):
    """family_reference derives the sibling to compare against from
    nameID 6's PostScript family, so a Term face asks for ITS family's
    Regular, not GengouJP-Regular -- a hard-coded lookup was a no-op for
    both Term and Nerd Font faces (round 11)."""
    sibling = make_font([".notdef", "a"], {0x61: "a"}, {"a": 600},
                        family="Gengou JP Term", style="Regular")
    sibling.save(tmp_path / "GengouJPTerm-Regular.otf")
    # a decoy under the old hard-coded name: if family_reference ever
    # regressed to "GengouJP-Regular.otf" this is what it would read
    decoy = make_font([".notdef"], {}, {}, family="Gengou JP", style="Regular")
    decoy.save(tmp_path / "GengouJP-Regular.otf")

    face = _named_font("Gengou JP Term", "Bold")
    face["name"].setName("GengouJPTerm-Bold", 6, 3, 1, 0x409)
    monkeypatch.setattr(verify_jp, "FONT", tmp_path / "GengouJPTerm-Bold.otf")

    ref = verify_jp.family_reference(face)
    assert ref is not None
    assert ref.getBestCmap() == {0x61: "a"}   # the Term sibling, not the decoy


def test_family_reference_does_not_fall_back_to_the_hardcoded_family(tmp_path, monkeypatch):
    """Only a decoy under the old hard-coded GengouJP-Regular name
    exists; the fixed function must return None rather than read it."""
    decoy = make_font([".notdef"], {}, {}, family="Gengou JP", style="Regular")
    decoy.save(tmp_path / "GengouJP-Regular.otf")

    face = _named_font("Gengou JP Term", "Bold")
    face["name"].setName("GengouJPTerm-Bold", 6, 3, 1, 0x409)
    monkeypatch.setattr(verify_jp, "FONT", tmp_path / "GengouJPTerm-Bold.otf")

    assert verify_jp.family_reference(face) is None


def test_family_reference_is_none_for_the_regular_itself(tmp_path, monkeypatch):
    face = _named_font("Gengou JP", "Regular")
    face["name"].setName("GengouJP-Regular", 6, 3, 1, 0x409)
    monkeypatch.setattr(verify_jp, "FONT", tmp_path / "GengouJP-Regular.otf")
    assert verify_jp.family_reference(face) is None


def test_family_reference_is_none_without_a_postscript_name(tmp_path, monkeypatch):
    face = _named_font("Gengou JP", "Regular")
    monkeypatch.setattr(verify_jp, "FONT", tmp_path / "GengouJP-Regular.otf")
    assert verify_jp.family_reference(face) is None
