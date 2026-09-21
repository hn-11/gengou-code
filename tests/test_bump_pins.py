"""Unit tests for scripts/bump_pins.py — the weekly upstream sync's pin
rewriter. Nothing here touches the network: `latest_tag` and `digest`
are the two seams, and both are monkeypatched."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import bump_pins  # noqa: E402

TAGS = {bump_pins.SHS_REPO: "2.005R",
        bump_pins.SCP_REPO: "2.042R-u/1.062R-i/1.026R-vf",
        bump_pins.SS_REPO: "3.052R",
        bump_pins.MONA_REPO: "v1.400",
        bump_pins.NF_REPO: "v3.4.0"}
SHAS = {"SHS_SHA": "a" * 64, "SCP_SHA": "b" * 64, "SS_SHA": "9" * 64,
        "MONA_SHA": "c" * 64, "NF_SHA": "d" * 64}


def _action(tmp_path, **over):
    pins = {"SHS_TAG": "2.005R",
            "SCP_TAG": "2.042R-u%2F1.062R-i%2F1.026R-vf",
            "SCP_VF_ZIP": "VF-source-code-VF-1.026R.zip",
            "SS_TAG": "3.052R",
            "MONA_TAG": "v1.400",
            "NF_TAG": "v3.4.0",
            **SHAS, **over}
    body = "".join(f'        echo "{k}={v}" >> "$GITHUB_ENV"\n'
                   for k, v in pins.items())
    p = tmp_path / "action.yml"
    p.write_text("name: x\nruns:\n  steps:\n    - run: |\n" + body)
    return p


def test_scp_vf_zip_reads_the_vf_component():
    assert (bump_pins.scp_vf_zip("2.042R-u/1.062R-i/1.026R-vf")
            == "VF-source-code-VF-1.026R.zip")


def test_scp_vf_zip_refuses_a_slash_tag_without_a_vf_part():
    with pytest.raises(ValueError, match="no -vf component"):
        bump_pins.scp_vf_zip("2.042R-u/1.062R-i")


def test_download_urls_names_one_asset_per_hash_pin():
    pins = {"SHS_TAG": "2.005R", "SCP_TAG": "T", "SCP_VF_ZIP": "z.zip",
            "SS_TAG": "3.052R", "MONA_TAG": "v1.400", "NF_TAG": "v3.4.0"}
    urls = bump_pins.download_urls(pins)
    assert set(urls) == set(bump_pins.SELECTORS)
    assert urls["SCP_SHA"].endswith("/T/z.zip")          # tag drops in as-is
    assert "monaspace-variable-v1.400.zip" in urls["MONA_SHA"]


def test_hash_pins_takes_the_new_hash_when_the_tag_moved(monkeypatch):
    current = {"MONA_TAG": "v1.400", **SHAS,
               "SHS_TAG": "2.005R", "SCP_TAG": "T", "SCP_VF_ZIP": "z.zip",
               "SS_TAG": "3.052R", "NF_TAG": "v3.4.0"}
    new = dict(current, MONA_TAG="v1.500")
    monkeypatch.setattr(bump_pins, "digest",
                        lambda url: "9" * 64 if "v1.500" in url
                        else SHAS[next(k for k, u in
                                       bump_pins.download_urls(new).items()
                                       if u == url)])
    got = bump_pins.hash_pins(current, new)
    assert got["MONA_SHA"] == "9" * 64
    assert got["SHS_SHA"] == SHAS["SHS_SHA"]


def test_hash_pins_refuses_an_asset_replaced_under_an_unmoved_tag(monkeypatch):
    """The case the hashes exist for. Rewriting the pin here would launder
    exactly what it guards, so it has to stop."""
    current = {"SHS_TAG": "2.005R", "SCP_TAG": "T", "SCP_VF_ZIP": "z.zip",
               "SS_TAG": "3.052R", "MONA_TAG": "v1.400", "NF_TAG": "v3.4.0", **SHAS}
    new = dict(current)                      # nothing moved
    monkeypatch.setattr(bump_pins, "digest",
                        lambda url: "f" * 64 if "source-han-sans" in url
                        else SHAS[next(k for k, u in
                                       bump_pins.download_urls(new).items()
                                       if u == url)])
    with pytest.raises(SystemExit, match="replaced under an unmoved pin"):
        bump_pins.hash_pins(current, new)


def test_hash_pins_accepts_an_unmoved_tag_whose_asset_is_unchanged(monkeypatch):
    current = {"SHS_TAG": "2.005R", "SCP_TAG": "T", "SCP_VF_ZIP": "z.zip",
               "SS_TAG": "3.052R", "MONA_TAG": "v1.400", "NF_TAG": "v3.4.0", **SHAS}
    monkeypatch.setattr(bump_pins, "digest",
                        lambda url: SHAS[next(k for k, u in
                                              bump_pins.download_urls(current).items()
                                              if u == url)])
    assert bump_pins.hash_pins(current, dict(current)) == SHAS


def test_main_leaves_the_file_alone_when_nothing_moved(monkeypatch, tmp_path,
                                                       capsys):
    action = _action(tmp_path)
    before = action.read_text()
    monkeypatch.setattr(bump_pins, "ACTION", action)
    monkeypatch.setattr(bump_pins, "latest_tag", lambda repo: TAGS[repo])
    monkeypatch.setattr(bump_pins, "digest",
                        lambda url: SHAS[next(
                            k for k, u in bump_pins.download_urls(
                                {"SHS_TAG": "2.005R",
                                 "SCP_TAG": "2.042R-u%2F1.062R-i%2F1.026R-vf",
                                 "SCP_VF_ZIP": "VF-source-code-VF-1.026R.zip",
                                 "SS_TAG": "3.052R",
                                 "MONA_TAG": "v1.400",
                                 "NF_TAG": "v3.4.0"}).items() if u == url)])
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert bump_pins.main() == 0
    assert action.read_text() == before
    assert "changed=false" in out.read_text()
    assert capsys.readouterr().out == ""


def test_main_writes_the_moved_tag_and_its_new_hash(monkeypatch, tmp_path,
                                                    capsys):
    action = _action(tmp_path)
    monkeypatch.setattr(bump_pins, "ACTION", action)
    monkeypatch.setattr(bump_pins, "latest_tag",
                        lambda repo: "v1.500" if repo == bump_pins.MONA_REPO
                        else TAGS[repo])
    old_urls = bump_pins.download_urls(
        {"SHS_TAG": "2.005R", "SCP_TAG": "2.042R-u%2F1.062R-i%2F1.026R-vf",
         "SCP_VF_ZIP": "VF-source-code-VF-1.026R.zip",
         "SS_TAG": "3.052R", "MONA_TAG": "v1.400", "NF_TAG": "v3.4.0"})
    monkeypatch.setattr(bump_pins, "digest",
                        lambda url: "9" * 64 if "v1.500" in url
                        else SHAS[next(k for k, u in old_urls.items() if u == url)])
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert bump_pins.main() == 0
    text = action.read_text()
    assert 'echo "MONA_TAG=v1.500"' in text
    assert f'echo "MONA_SHA={"9" * 64}"' in text
    assert f'echo "SHS_SHA={SHAS["SHS_SHA"]}"' in text      # untouched
    assert "changed=true" in out.read_text()
    summary = capsys.readouterr().out
    assert "`MONA_TAG`" in summary and "`MONA_SHA`" in summary
