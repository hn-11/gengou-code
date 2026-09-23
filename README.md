# Gengou Code

[日本語](README.ja.md)

Gengou Code is a monospaced font for code and terminals. The letters are
[Source Code Pro](https://github.com/adobe-fonts/source-code-pro) at its own
size and weights. The punctuation and 61 ligatures come from
[Monaspace](https://github.com/githubnext/monaspace), redrawn at each weight
so their strokes match Source Code Pro's.

It ships as a variable font (weight 200 to 700) with five named weights:
Light, Regular, Medium, SemiBold and Bold, each with a true italic. A Nerd
Fonts build is available too.

**Gengou Code JP** is a companion family that adds Japanese from
[Source Han Sans](https://github.com/adobe-fonts/source-han-sans). See
[Gengou Code JP](#gengou-code-jp) below.

## Download

Get the zips from [Releases](../../releases). Every zip includes the license.

| File | Contents |
|------|----------|
| `GengouCode.zip` | Gengou Code, two variable fonts (upright and italic) |
| `GengouCode-NerdFont.zip` | Gengou Code NF, the same with Nerd Fonts icons |
| `GengouCodeJP.zip` | Gengou Code JP, 10 static OTFs |
| `GengouCodeJPTerm.zip` | Gengou Code JP Term, 10 static OTFs |
| `GengouCodeJP-NerdFont.zip`, `GengouCodeJPTerm-NerdFont.zip` | The JP families with Nerd Fonts icons |

## Install

- **macOS**: open the `.otf` files and click Install in Font Book, or copy
  them to `~/Library/Fonts/`.
- **Windows**: right-click the `.otf` files and choose Install (or
  "Install for all users").
- **Linux**: copy them to `~/.local/share/fonts/` and run `fc-cache -f`.

Then pick the family in your editor or terminal:

```jsonc
// VS Code settings.json
"editor.fontFamily": "Gengou Code",
"editor.fontLigatures": true
```

```jsonc
// Windows Terminal settings.json, in a profile
"font": { "face": "Gengou Code" }
```

For Japanese, use `Gengou Code JP` instead.

Older releases were called Sumi Moji (up to v5.0.0) and Shoyu Code Pro JP
(up to v3.2.0). The names differ, so they can be installed side by side.
Uninstall them if you are replacing them.

## Character set

- Latin, Greek and Cyrillic come from Source Code Pro. Source Code Pro
  Italic draws no Cyrillic and only one Greek letter, so the italic takes
  both scripts from Source Sans 3 Italic, which Source Code Pro was derived
  from. The italic angle and cap height are the same. The letters are
  centred in the cell, and the few that are too wide for it (42 in Regular
  Italic) are narrowed.
- The 32 ASCII punctuation marks are Monaspace's, so a mark looks the same
  alone and inside a ligature (`-` and `->`, `/` and `//`, `#` and `#[`).
- Everything the font draws is one cell wide (600 units), including the
  arrows `← → ↑ ↓ ⇐ ⇒ ⇔`, `≠ ≤ ≥ …` and box drawing.
- Line height is Source Code Pro's: ascent 984, descent −273 (1.257 em),
  with `USE_TYPO_METRICS` set.
- Combining accents are positioned on every letter that can take them, not
  only on the third or so of Greek and Cyrillic letters that Source Code
  Pro and Source Sans anchor themselves.

## Ligatures

All 61 Monaspace ligatures are on by default through `calt` and `liga`.
The full list is in [`data/mona_ligs.json`](data/mona_ligs.json). A few:
`!=` `==` `===` `<=` `>=` `->` `<-` `=>` `:=` `::` `|>` `<|` `</>` `//`
`...` `&&` `||` `<!--`.

The ligatures are also split into stylistic sets, as in Monaspace, so you
can turn `calt` off and enable only the groups you want:

| Feature | Group | Examples |
|---------|-------|----------|
| `ss01` | Equality and comparison | `!=` `===` `<=` `>=` `!~` `=~` |
| `ss02` | Arrows | `->` `<-` `=>` `>>=` `~~>` |
| `ss03` | Markup | `</` `/>` `</>` `<>` `<!--` |
| `ss04` | Pipes | `\|>` `<\|` |
| `ss05` | Colons | `::` `:=` `:>` `<:` |
| `ss06` | Dots | `..` `...` `..<` `.=` |
| `ss07` | Comments | `//` `///` |
| `ss08` | Repeats, logic and the rest | `\|\|` `<<` `>>` `#[` `#(` `&=` `&&` `&&=` `++` |
| `cv99` | Monaspace's alternate operator designs | |

```jsonc
// Arrows and the rest, but no comparison ligatures
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss04', 'ss05', 'ss06', 'ss07', 'ss08'"
```

Each stylistic set is its own lookup. With `calt` off and several sets on,
a shorter sequence from one set can take the start of a longer one from
another (`>=` from ss01 inside `>>=` from ss02). Monaspace behaves the same
way. `calt` does not have this problem.

## Character variants

Source Code Pro's own features are kept:

- `zero`: slashed zero
- `cv01` to `cv17`: alternate letters, such as a single-storey `a` and
  other forms of `g` (the italic lacks the ones Source Code Pro Italic
  lacks)
- `salt`
- Source Code Pro's stylistic sets, moved to `ss11` to `ss17` because
  `ss01` to `ss08` hold the ligature groups

`cv14`, `cv15` and `cv16` bring back Source Code Pro's `-`, `*` and `$`.
In Gengou Code (not in Gengou Code JP), turning on `cv14`, `salt` or
`ss11` also switches off the nine ligatures that contain a hyphen (`->`
`<-` `-->` `<--` `<->` `<-->` `<!--` `-~` `~-`).

## Weights

| Weight | wght | `=` bar, upright / italic |
|--------|------|---------------------------|
| Light | 300 | 37 / 34 units |
| Regular | 400 | 62 / 58 |
| Medium | 500 | 73 / 67 |
| SemiBold | 600 | 83 / 78 |
| Bold | 700 | 104 / 97 |

These are Source Code Pro's named instances. At each one, Monaspace's
weight is chosen so its `=` has the same bar thickness.

Monaspace's lightest weight has a 53-unit bar. Below about wght 365 (381
in the italic), the punctuation and ligatures stop getting lighter while
the letters keep going. At Light the letters have 56% of Regular's ink but
the symbols keep 86 to 92%, so they look heavier. Gengou Code JP does not
have this problem: its Light thins the Monaspace outlines to match.

## Nerd Fonts

The NF builds add the Nerd Fonts icons, each fitted to one cell. The
families are named `Gengou Code NF`, `Gengou Code JP NF` and
`Gengou Code JP Term NF`, the way Cascadia Code names its Nerd Fonts build.
The usual `Nerd Font Mono` suffix would make some names longer than the 31
characters Windows GDI allows (`Gengou Code JP Term Nerd Font Mono
SemiBold` is 43), and those faces would show up under a different name in
older Windows apps. In Nerd Fonts' own naming `NF` means the icons may
overflow the cell. That is not the case here: every icon stays in its cell.

The icons are copied from `Symbols Nerd Font Mono`, the symbols-only font
Nerd Fonts publishes. You get the same icon set and the same one-cell
advance as a `font-patcher --complete --mono` build. The sizes differ
slightly: font-patcher fits icons into a 600 × 856 box on this font, and
here they keep the symbols font's square cell (600 × 600). Powerline
separators and progress bars are stretched to the full cell and line
height. Source Code Pro's own Powerline glyphs are replaced.

In Gengou Code NF the icons are the same at every weight. The Nerd Fonts
license (MIT) ships in the NF zips as `LICENSE-NerdFonts`.

## Gengou Code JP

Gengou Code JP is Gengou Code with Japanese added from Source Han Sans JP.
Gengou Code sets the rules: the 600-unit cell, the weights and the line
height. Every character Gengou Code has stays one cell wide. Kanji, kana
and anything else only Source Han Sans has keep Source Han Sans's full
width.

| Family | Half : full width | Use |
|--------|-------------------|-----|
| Gengou Code JP | 600 : 1000 (3:5) | Editors. Japanese at Source Han Sans's own width |
| Gengou Code JP Term | 600 : 1200 (1:2) | Apps that don't lay text on a grid but should line up like a terminal. Full-width glyphs get two cells, centred |

Inside a terminal the two look the same, since the terminal places each
character itself. Both come in the five weights, upright and italic, as
static OTFs. The italic is Gengou Code Italic with upright Japanese. The
Japanese weight is the Source Han Sans weight whose `＝` bar matches:

| Weight | Source Han Sans weight (`＝` bar) |
|--------|-----------------------------------|
| Light | ExtraLight (36 units) |
| Regular | Normal (63) |
| Medium | Regular (69) |
| SemiBold | Medium (83) |
| Bold | Bold (101) |

Width details:

- Half-width katakana (`ｱ`) and other half-width forms are one cell.
  Source Han Sans's proportional leftovers, such as Hangul jamo, are centred
  on the nearest grid width.
- Thirteen characters are East Asian Wide but only one cell here, because
  no source has a wider form: `☕ 🎵 🎶 💩 🔒 🤖`, two Hangul tone marks and
  five Bopomofo tone letters. A terminal gives them two columns, so they
  sit to the left.
- If your terminal treats ambiguous-width characters as wide, `①` and
  similar characters spill into the next cell. Set the terminal to wide
  ambiguous width to give them two columns: in Windows Terminal,
  `"compatibility.ambiguousWidth": "wide"`.
- There is no switch between half-width and full-width forms. `fwid` and
  `hwid` were removed in v6.0.0: an editor applies features to the whole
  buffer, so `fwid` turned every letter full width. For a full-width form,
  use the full-width character itself (`＝` `｜` `＋`).
- Source Han Sans's `kern`, `palt`, `halt` and `pwid` are removed, so
  nothing moves off the grid. Vertical writing (`vert`, `vrt2` and the
  vertical metrics features) is kept.

Line height is Gengou Code's (984 / −273). `usWinAscent` and
`usWinDescent` are 1160 and 454, so Japanese and box drawing are not
clipped in GDI apps (old conhost, Notepad, Office). In those apps the line
is taller.

## The name

源合 (Gengou) combines 源, the character Source Han Sans uses for
"Source", with 合 from 合字 (ligature), which also means putting things
together. The SIL Open Font License reserves the name "Source", so it
could not be used directly.

## Building

The fonts are built in CI from the upstream releases. No source glyphs are
kept in this repository. See [CONTRIBUTING.md](CONTRIBUTING.md) for local
builds, tests and how the release works.

## License

[SIL Open Font License 1.1](LICENSE), the same as the upstream fonts:
Source Code Pro, Source Sans 3, Source Han Sans (Adobe) and Monaspace
(GitHub). The family names contain neither "Source" nor "Monaspace", as the
Reserved Font Names require. The Nerd Fonts icons are under the MIT
license.
