#!/usr/bin/env python3
"""Move the upstream pins in .github/actions/fetch-upstreams/action.yml forward.

Asks GitHub for each upstream's latest release and rewrites the pin block with
those tags. Prints a markdown summary of what moved on stdout and writes
`changed=true|false` to $GITHUB_OUTPUT; prints nothing when every pin is
already current.

`releases/latest` deliberately ignores prereleases and drafts - source-code-pro
in particular ships prerelease tags between VF drops that we don't chase. A
single-component tag (a one-off hotfix, no VF drop) leaves the SCP pins at
their current values - noted on stderr and in the summary - while the other
upstreams still move; a slash-joined tag without a -vf part fails loudly.

Every asset is downloaded and hashed before anything is written - the pins
carry a sha256 beside each tag, because a GitHub release asset can be
replaced without the tag moving, and the tag alone therefore does not say
which bytes were built. If an upstream renames an asset, this fails here
with the URL in hand instead of opening a PR whose CI dies twenty minutes
later at the fetch step. If an upstream *replaces* an asset under a tag that
did not move, this fails too, and says so: that is the case the hashes exist
for, and it must not be papered over by writing the new hash.
"""

import hashlib
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ACTION = Path(".github/actions/fetch-upstreams/action.yml")

# The lowest version this code may be released as. The weekly sync cuts
# a PATCH bump of the newest tag, which is right for an upstream refresh
# -- newer sources, nothing in this repo changed but the pins -- and
# wrong the first time after a release that changes what the fonts ARE.
# v5.0.0 shipped the family as Sumi Moji; this code ships it as Gengou,
# with different family names, PostScript names and vendor ID, so the
# next tag is a major one and a human has to cut it. Raise this whenever
# a release changes something a patch bump would misrepresent.
MIN_RELEASE = "6.0.0"

SHS_REPO = "adobe-fonts/source-han-sans"
SCP_REPO = "adobe-fonts/source-code-pro"
SS_REPO = "adobe-fonts/source-sans"
MONA_REPO = "githubnext/monaspace"
NF_REPO = "ryanoasis/nerd-fonts"

PIN_RE = re.compile(r'(?P<head>echo "(?P<key>[A-Z_]+)=)(?P<val>[^"]*)(?P<tail>")')


def latest_tag(repo: str) -> str:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases/latest", "--jq", ".tag_name"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def scp_vf_zip(tag: str) -> str:
    """Derive the VF asset name from source-code-pro's composite release tag.

    The tag is a slash-joined triple, e.g. "2.042R-u/1.062R-i/1.026R-vf"; the
    VF zip is named after the third component alone:
    "VF-source-code-VF-1.026R.zip".

    Raises ValueError when a slash-joined tag has no -vf component - that
    is a renamed convention, not a hotfix, and must fail loudly.
    """
    for part in tag.split("/"):
        if part.endswith("-vf"):
            return f"VF-source-code-VF-{part[: -len('-vf')]}.zip"
    raise ValueError(f"no -vf component in source-code-pro tag {tag!r}")


# Which tag pins select each asset: a hash is allowed to move only when
# one of these moved with it.
SELECTORS = {
    "SHS_SHA": ("SHS_TAG",),
    "SCP_SHA": ("SCP_TAG", "SCP_VF_ZIP"),
    "SS_SHA": ("SS_TAG",),
    "MONA_SHA": ("MONA_TAG",),
    "NF_SHA": ("NF_TAG",),
}


def download_urls(pins: dict[str, str]) -> dict[str, str]:
    mona = pins["MONA_TAG"]
    return {
        "SHS_SHA": f"https://github.com/{SHS_REPO}/releases/download/"
                   f"{pins['SHS_TAG']}/17_SourceHanSansJP.zip",
        # SCP_TAG is stored %2F-encoded, so it drops into the path as-is.
        "SCP_SHA": f"https://github.com/{SCP_REPO}/releases/download/"
                   f"{pins['SCP_TAG']}/{pins['SCP_VF_ZIP']}",
        "SS_SHA": f"https://github.com/{SS_REPO}/releases/download/"
                  f"{pins['SS_TAG']}/VF-source-sans-{pins['SS_TAG']}.zip",
        "MONA_SHA": f"https://github.com/{MONA_REPO}/releases/download/"
                    f"{mona}/monaspace-variable-{mona}.zip",
        "NF_SHA": f"https://github.com/{NF_REPO}/releases/download/"
                  f"{pins['NF_TAG']}/NerdFontsSymbolsOnly.zip",
    }


def digest(url: str) -> str:
    """The asset's sha256, streamed rather than held in memory (the Source
    Han Sans zip is 27 MB). Doubles as the reachability probe a HEAD used
    to be: an upstream that renamed an asset fails here."""
    sha = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=300) as resp:
            if resp.status >= 400:
                raise SystemExit(f"HTTP {resp.status} for {url}")
            read = 0
            for chunk in iter(lambda: resp.read(1 << 20), b""):
                sha.update(chunk)
                read += len(chunk)
            # http.client returns b"" rather than raising when the body
            # ends short of its Content-Length, so a cut transfer would
            # otherwise be hashed as if it were the asset — and reported
            # as an upstream that replaced its release. `length` is what
            # is left to read: anything but 0 means the body stopped early
            if resp.length:
                raise SystemExit(
                    f"{url}\n  transfer ended {resp.length} bytes short "
                    f"of its Content-Length after {read}; not hashing a "
                    f"partial download.")
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach {url}: {exc}") from exc
    return sha.hexdigest()


def hash_pins(current: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """The sha256 of every asset `new` selects, checked against the pins.

    A hash that moved while every tag selecting it stayed put means the
    upstream replaced the asset under a fixed tag. Rewriting the pin then
    would launder exactly what the pin is for, so this stops instead and
    leaves the decision to a person."""
    out = {}
    for key, url in download_urls(new).items():
        got = digest(url)
        moved = any(current[k] != new[k] for k in SELECTORS[key])
        if not moved and current.get(key) and current[key] != got:
            raise SystemExit(
                f"{url}\n"
                f"  was replaced under an unmoved pin: sha256 {got}, "
                f"pinned {current[key]}.\n"
                f"  The tag did not change, so these are different bytes "
                f"under the same name.\n"
                f"  Check the upstream release before touching "
                f"{key} in {ACTION}."
            )
        out[key] = got
    return out


def emit(changed: bool) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")


# every pin main() expects to find, before it reads any of them
PINS = ("SHS_TAG", "SCP_TAG", "SCP_VF_ZIP", "SS_TAG", "MONA_TAG", "NF_TAG",
        *SELECTORS)


def next_release(latest, floor=MIN_RELEASE):
    """The tag an upstream refresh cuts from `latest`: its patch bumped.

    Refuses to return anything below `floor` rather than bumping into
    it, because the sync merges its own PR and dispatches the release
    with no one watching -- so the first sync after a rename would have
    published new family names, new PostScript names and a new vendor ID
    as v5.0.1, generated notes and all. Cut the major tag by hand first.
    """
    parts = latest.lstrip("v").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise SystemExit(f"cannot bump {latest!r}: not a vMAJOR.MINOR.PATCH tag")
    nxt = (int(parts[0]), int(parts[1]), int(parts[2]) + 1)
    want = tuple(int(p) for p in floor.split("."))
    if nxt < want:
        raise SystemExit(
            f"the newest tag is {latest}, so an upstream refresh would cut "
            f"v{'.'.join(map(str, nxt))} -- below this code's MIN_RELEASE of "
            f"v{floor}. This release changes what the fonts are, not just "
            f"which upstream they came from; cut v{floor} by hand, then the "
            f"sync can patch-bump from there.")
    return "v" + ".".join(str(n) for n in nxt)


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--next":
        print(next_release(sys.argv[2]))
        return 0
    text = ACTION.read_text()
    current = {m["key"]: m["val"] for m in PIN_RE.finditer(text)}
    if not current:
        raise SystemExit(f"no pins found in {ACTION}")
    # before anything indexes them: the hotfix branch below reads the SCP
    # pins directly, and a KeyError traceback there would replace the one
    # message written for a pin that went missing
    missing = [k for k in PINS if k not in current]
    if missing:
        raise SystemExit(f"{ACTION} is missing pins: {sorted(missing)}")

    scp_tag = latest_tag(SCP_REPO)
    notes = []
    if "/" not in scp_tag:
        # a single-component tag is the one-off hotfix shape (no VF drop);
        # anything else that fails scp_vf_zip is a renamed convention we
        # must not paper over, so let it raise
        notes.append(f"source-code-pro latest tag `{scp_tag}` has no VF "
                     f"component; SCP pins kept at `{current['SCP_TAG']}`")
        scp_pins = {"SCP_TAG": current["SCP_TAG"],
                    "SCP_VF_ZIP": current["SCP_VF_ZIP"]}
    else:
        scp_pins = {
            "SCP_TAG": scp_tag.replace("/", "%2F"),
            "SCP_VF_ZIP": scp_vf_zip(scp_tag),
        }
    for note in notes:
        print(f"note: {note}", file=sys.stderr)

    new = {
        "SHS_TAG": latest_tag(SHS_REPO),
        **scp_pins,
        "SS_TAG": latest_tag(SS_REPO),
        "MONA_TAG": latest_tag(MONA_REPO),
        "NF_TAG": latest_tag(NF_REPO),
    }
    moved = {k: (current[k], v) for k, v in new.items() if current[k] != v}
    # every run hashes the assets, moved or not: a replacement under a tag
    # that did not move is the case the hashes exist for, and a run that
    # returned early would never see it
    new.update(hash_pins(current, new))
    moved.update({k: (current[k], v) for k, v in new.items()
                  if k in SELECTORS and current.get(k) != v})
    if not moved:
        emit(False)
        return 0

    ACTION.write_text(
        PIN_RE.sub(lambda m: m["head"] + new.get(m["key"], m["val"]) + m["tail"], text)
    )
    emit(True)

    print("| pin | from | to |")
    print("| --- | --- | --- |")
    for key, (old, now) in moved.items():
        print(f"| `{key}` | `{old}` | `{now}` |")
    for note in notes:   # into the PR body, where someone will read it
        print(f"\n> {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
