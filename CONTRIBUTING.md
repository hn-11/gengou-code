# Contributing

[日本語](CONTRIBUTING.ja.md)

The fonts are built from upstream releases: Source Code Pro, Source Sans 3,
Monaspace, Source Han Sans JP and Symbols Nerd Font Mono. No source glyphs
are kept here, so every build needs those files.

## Layout

| Path | What it does |
|------|--------------|
| `scripts/build_latin.py` | The Latin layer's recipe: donor fonts, the graft of Monaspace's punctuation and ligatures, one static donor face per weight and style (in memory) |
| `scripts/build_latin_vf.py` | Gengou Code itself, the variable fonts, from the same recipe |
| `scripts/build.py` | Gengou Code JP and JP Term: builds the Latin donors, then grafts them onto Source Han Sans. Also the shared helpers |
| `scripts/vfsource.py` | Instancing the variable donors and matching Monaspace's weight |
| `scripts/anchors.py` | Mark anchors the Latin layer adds |
| `scripts/nerdpatch.py` | The Nerd Fonts builds |
| `scripts/verify.py` | Runs the checks on built fonts. `verify_jp.py`, `verify_latin_vf.py` and the shared `verifylib.py` hold them |
| `scripts/golden.py` | Compares two builds face by face |
| `scripts/bump_pins.py` | Moves the upstream pins forward (used by `upstream-sync.yml`) |
| `data/mona_ligs.json` | The ligature list |

## Building locally

```sh
pip install -r requirements.txt
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=... NF_SYMBOLS=...
python scripts/build_latin_vf.py              # dist/latin/GengouCode[wght].otf, GengouCode-Italic[wght].otf
python scripts/build.py                       # dist/GengouCodeJP*.otf, both JP families
python scripts/build.py "Regular"             # Regular and Regular Italic only, quicker
python scripts/build.py "Light Upright Term"  # a single face
python scripts/nerdpatch.py                   # dist/nerd/, NF builds of everything above
```

| Variable | Read by | Value |
|----------|---------|-------|
| `SCP_VF_U` | `build.py`, `build_latin_vf.py` | Path to `SourceCodeVF-Upright.otf` ([Source Code Pro releases](https://github.com/adobe-fonts/source-code-pro/releases)) |
| `SCP_VF_I` | same | Path to `SourceCodeVF-Italic.otf` |
| `SS_VF_I` | same | Path to `SourceSans3VF-Italic.otf` ([Source Sans releases](https://github.com/adobe-fonts/source-sans/releases)). Required even for an upright-only build, so an italic build can't silently lose Greek and Cyrillic |
| `MONA_VF` | same | Path to `Monaspace Neon Var.ttf` ([Monaspace releases](https://github.com/githubnext/monaspace/releases)) |
| `SHS_DIR` | `build.py` | Directory with `SourceHanSansJP-<Weight>.otf` ([Source Han Sans releases](https://github.com/adobe-fonts/source-han-sans/releases)) |
| `NF_SYMBOLS` | `nerdpatch.py` | Path to `SymbolsNerdFontMono-Regular.ttf` (`NerdFontsSymbolsOnly.zip` from [Nerd Fonts releases](https://github.com/ryanoasis/nerd-fonts/releases)) |
| `GENGOU_VERSION` | builds and checks, optional | Release version, such as `6.0.0`. Unset leaves the upstream revision in the name table |
| `GENGOU_SKIP_AUTOHINT` | `build.py`, `nerdpatch.py`, optional | `1` skips hinting for quick local builds. The hint checks then fail, which is expected |

The exact upstream tags and download URLs are in
`.github/actions/setup-build/action.yml`, and `.github/workflows/ci.yml`
runs the same commands as above.

A build filter is a list of words, and a face is built when it matches
every kind of word given: weights (`Light` `Regular` `Medium` `SemiBold`
`Bold`), styles (`Upright` `Italic`) and families (`Term`, or `base` for
Gengou Code JP). Several words of one kind mean any of them, so
`"Light Regular base"` is four faces.

## Checking your change

```sh
python -m pytest tests/ -q
python scripts/verify.py dist/GengouCodeJP-Regular.otf
python scripts/verify.py 'dist/*.otf' 'dist/nerd/*.otf' 'dist/latin/*.otf' 'dist/nerd/latin/*.otf'
```

`verify.py` picks the checks from the font itself: a variable font goes to
`verify_latin_vf.py`, a face with Japanese to `verify_jp.py`. They look at
the whole font, not samples: every character's advance against its East
Asian Width, where each glyph sits in its cell, ligature cells and guards,
combining marks, GSUB/GPOS/GDEF, metrics and names. Variable fonts are
checked at the default, both ends of the axis, every named instance and
every master. Run at least the Regular faces before sending a pull request.
CI runs the same checks. The comments at the top of `ci.yml` and
`release.yml` say which job builds what.

When a change alters the output, show that only the intended things moved.
Build the commit before your change into another directory and compare:

```sh
python scripts/golden.py <old dist> dist
python scripts/golden.py <old dist>/latin dist/latin --only '*wght*'
python scripts/golden.py <old dist>/nerd dist/nerd
```

`golden.py` compares cmap, advances, feature tags, shaping of a text
corpus, outlines, metadata and hints, and does not care if glyphs were
renumbered. It does not walk into subdirectories, hence one call per
directory. Put the differences it reports in the pull request, with the
reason for each. It needs two builds, so CI does not run it.

## Adding or changing a ligature

Ligatures are defined in `data/mona_ligs.json`. `build_latin.py` draws them
from Monaspace into the Latin layer, and `build.py` copies the finished
glyphs into the JP faces. An entry looks like this:

```jsonc
"!=": {
  "cells": 2,                  // width in cells (advance = 600 × cells)
  "glyphs": ["exclam_equal"],  // Monaspace glyph names, drawn left to right
  "group": "ss01"              // stylistic set; calt and liga get every group
}
```

The key is the character sequence. An entry is skipped when one of its
characters is missing from the font or a glyph name is missing from
Monaspace. If Monaspace has a `.alt` version of the glyph, it becomes the
`cv99` alternate automatically.

To add one: find the glyph name in Monaspace, add the entry, build Regular,
run `verify.py`, and update the stylistic set table in both READMEs.

## Upstream versions

The upstream releases are pinned in the "Pin upstream releases" step of
`.github/actions/setup-build/action.yml`, each tag with the SHA-256 of its
download. A download that doesn't match its hash stops the build, because a
GitHub release asset can be replaced without the tag changing.

`upstream-sync.yml` runs every Monday:

1. `scripts/bump_pins.py` looks up each upstream's latest release,
   downloads the assets and hashes them. It stops if an asset was renamed,
   or if a hash changed while the tag stayed the same.
2. It opens a pull request on `chore/upstream-sync`.
3. When the CI checks in `REQUIRED_CHECKS` pass, it squash-merges.
4. It runs `release.yml` with the next patch version.

If a new upstream release makes things worse, close the pull request. The
pins stay where they are, and next week's run opens it again. To bump by
hand, edit the tag and its hash together.

## Releases

The git tag is the version. There is no version file. Upstream-only
updates are patch releases and are made automatically. A release that
changes the fonts themselves needs a new tag made by hand first:
`MIN_RELEASE` in `scripts/bump_pins.py` stops automatic releases below it.
The next one is `v6.0.0`.

To time the release workflow without publishing, use Run workflow with
dry-run checked, or push a commit whose message contains `[release-dry]`.

Release notes are generated from merged pull requests, so a pull request's
title becomes a line in the notes. Write it as what changes for someone
using the font. Notes up to v5.0.0 are on their release pages and in
`git show v5.0.0:CHANGELOG.md`.

## Issues and pull requests

Report bugs with the template in `.github/ISSUE_TEMPLATE/`. In a pull
request, say what changed and how you checked it (which faces you ran
`verify.py` on, and the `golden.py` differences if the output changed).

Design notes and measurements from earlier rounds are in the history:
`git show a7c86ec:docs/gengou-plan.md`. Its list of deferred items
("据え置き") records things that were looked at and left alone on purpose.
