# Gengou Code

[English](README.md)

Gengou Code（源合）は、コードとターミナル向けの等幅フォント。文字は
[Source Code Pro](https://github.com/adobe-fonts/source-code-pro) を原寸・
原ウェイトのまま使い、記号と合字 61 種は
[Monaspace](https://github.com/githubnext/monaspace) から取って、ウェイト
ごとに線の太さを Source Code Pro に合わせてある。

配布は可変フォント（ウェイト 200〜700）で、名前付きウェイトは Light /
Regular / Medium / SemiBold / Bold の 5 つ。それぞれに本物のイタリックが
ある。Nerd Fonts 版もある。

日本語入りの **Gengou Code JP** も同梱ファミリーとして配っている。和文は
[Source Han Sans](https://github.com/adobe-fonts/source-han-sans)（源ノ角
ゴシック）から取る。詳しくは下の [Gengou Code JP](#gengou-code-jp) を参照。

## ダウンロード

[Releases](../../releases) から zip を取る。どの zip にもライセンスが入っている。

| ファイル | 中身 |
|----------|------|
| `GengouCode.zip` | Gengou Code の可変フォント 2 本（直立と斜体） |
| `GengouCode-NerdFont.zip` | Gengou Code NF。上に Nerd Fonts のアイコンを足したもの |
| `GengouCodeJP.zip` | Gengou Code JP の静的 OTF 10 面 |
| `GengouCodeJPTerm.zip` | Gengou Code JP Term の静的 OTF 10 面 |
| `GengouCodeJP-NerdFont.zip`、`GengouCodeJPTerm-NerdFont.zip` | JP ファミリーの Nerd Fonts 版 |

## インストール

- **macOS**: `.otf` を開いて Font Book でインストールするか、
  `~/Library/Fonts/` にコピーする。
- **Windows**: `.otf` を右クリックして「インストール」（全ユーザーなら
  「すべてのユーザーに対してインストール」）。
- **Linux**: `~/.local/share/fonts/` にコピーして `fc-cache -f`。

あとはエディタやターミナルでファミリー名を指定する。

```jsonc
// VS Code の settings.json
"editor.fontFamily": "Gengou Code",
"editor.fontLigatures": true
```

```jsonc
// Windows Terminal の settings.json（プロファイルの中）
"font": { "face": "Gengou Code" }
```

日本語も使うなら `Gengou Code JP` を指定する。

以前の名前は Sumi Moji（v5.0.0 まで）と Shoyu Code Pro JP（v3.2.0 まで）。
名前が違うので並べて入れられる。置き換えるなら古いほうをアンインストール
する。

## 文字

- ラテン・ギリシャ・キリルは Source Code Pro のもの。Source Code Pro
  Italic はキリルを持たず、ギリシャも 1 字しかないので、斜体のこの 2 つは
  Source Sans 3 Italic から取る。Source Code Pro は Source Sans から
  起こされた書体で、イタリックの角度とキャップハイトが同じ。セルの中央に
  置き、幅に収まらない字（Regular Italic で 42 字）だけ細める。
- ASCII の記号 32 字は Monaspace のもの。単独でも合字の中でも同じ形に
  なる（`-` と `->`、`/` と `//`、`#` と `#[`）。
- 収録している字はすべて 1 セル（600 ユニット）。矢印 `← → ↑ ↓ ⇐ ⇒ ⇔`、
  `≠ ≤ ≥ …`、罫線も 1 セル。
- 行の高さは Source Code Pro と同じ 984 / −273（1.257 em）で、
  `USE_TYPO_METRICS` を立ててある。
- 結合アクセントは付けられる字すべてに位置を持たせてある。Source Code Pro
  と Source Sans が自前でアンカーを持つのは、ギリシャ・キリルの 3 分の 1
  ほどしかない。

## 合字

Monaspace の合字 61 種が `calt` と `liga` で最初から効く。一覧は
[`data/mona_ligs.json`](data/mona_ligs.json)。主なもの:
`!=` `==` `===` `<=` `>=` `->` `<-` `=>` `:=` `::` `|>` `<|` `</>` `//`
`...` `&&` `||` `<!--`。

Monaspace と同じく、合字はグループごとの stylistic set にも分けてある。
`calt` を切って、欲しいグループだけ有効にできる。

| feature | グループ | 例 |
|---------|----------|----|
| `ss01` | 等価・比較 | `!=` `===` `<=` `>=` `!~` `=~` |
| `ss02` | 矢印 | `->` `<-` `=>` `>>=` `~~>` |
| `ss03` | マークアップ | `</` `/>` `</>` `<>` `<!--` |
| `ss04` | パイプ | `\|>` `<\|` |
| `ss05` | コロン | `::` `:=` `:>` `<:` |
| `ss06` | ドット | `..` `...` `..<` `.=` |
| `ss07` | コメント | `//` `///` |
| `ss08` | 繰り返し・論理・その他 | `\|\|` `<<` `>>` `#[` `#(` `&=` `&&` `&&=` `++` |
| `cv99` | Monaspace の演算子の別デザイン | |

```jsonc
// 比較の合字だけ切って、矢印などは残す
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss04', 'ss05', 'ss06', 'ss07', 'ss08'"
```

stylistic set はグループごとに別のルックアップなので、`calt` を切って
複数のグループを同時に有効にすると、短い列が別グループの長い列の頭を
取ってしまうことがある（ss02 の `>>=` の中の ss01 の `>=`）。Monaspace
本家も同じ。`calt` ならこれは起きない。

## 字形の切り替え

Source Code Pro の feature はそのまま使える。

- `zero`: スラッシュ付きのゼロ
- `cv01`〜`cv17`: 一階建ての `a`、別の形の `g` など（斜体は Source Code
  Pro Italic に無いものを持たない）
- `salt`
- Source Code Pro の stylistic set。`ss01`〜`ss08` を合字が使うので
  `ss11`〜`ss17` に移してある

`cv14`、`cv15`、`cv16` で `-` `*` `$` が Source Code Pro の形に戻る。
Gengou Code（JP ではない方）では、`cv14`、`salt`、`ss11` を有効にすると
ハイフンを含む合字 9 種（`->` `<-` `-->` `<--` `<->` `<-->` `<!--` `-~`
`~-`）も出なくなる。

## ウェイト

| ウェイト | wght | `=` の横棒（直立 / 斜体） |
|----------|------|---------------------------|
| Light | 300 | 37 / 34 ユニット |
| Regular | 400 | 62 / 58 |
| Medium | 500 | 73 / 67 |
| SemiBold | 600 | 83 / 78 |
| Bold | 700 | 104 / 97 |

どれも Source Code Pro の名前付きインスタンス。Monaspace のウェイトは、
その `=` の横棒と太さが同じになる値を選んでいる。

Monaspace のいちばん細いウェイトでも横棒は 53 ユニットある。そのため
wght 365 あたり（斜体は 381）より細い側では、文字は細くなり続けても
記号と合字はそこで止まる。Light では文字の墨の量が Regular の 56% まで
減るのに、記号は 86〜92% のままなので、記号が太く見える。Gengou Code JP
の Light は Monaspace の輪郭を削って合わせてあるので、この差は出ない。

## Nerd Fonts 版

NF 版は Nerd Fonts のアイコンを足したもので、アイコンはすべて 1 セルに
収めてある。ファミリー名は `Gengou Code NF`、`Gengou Code JP NF`、
`Gengou Code JP Term NF` で、Cascadia Code の Nerd Fonts 版と同じ付け方。
本家の `Nerd Font Mono` を付けると、Windows の GDI が扱える 31 文字を
超える名前が出る（`Gengou Code JP Term Nerd Font Mono SemiBold` は 43
文字）。そうなると古い Windows アプリでは別の名前で見えてしまう。
本家の命名では `NF` は「アイコンがセルからはみ出してよい版」を指すが、
ここではどのアイコンもセルに収まっている。

アイコンは Nerd Fonts が配っている記号だけのフォント
`Symbols Nerd Font Mono` から写している。アイコンの集合と 1 セルの送りは
`font-patcher --complete --mono` と同じ。大きさは少し違い、font-patcher
はこのフォントでは 600 × 856 の箱に収めるが、こちらは記号フォントの
正方形のセル（600 × 600）のまま。Powerline の区切りと進捗バーはセルと
行の高さいっぱいに伸ばす。Source Code Pro 自身の Powerline の字は
置き換える。

Gengou Code NF のアイコンはどのウェイトでも同じ形。Nerd Fonts のライセンス
（MIT）は NF の zip に `LICENSE-NerdFonts` として入っている。

## Gengou Code JP

Gengou Code JP は、Gengou Code に Source Han Sans JP の和文を足した
ファミリー。基準は Gengou Code の側にあり、セル幅 600、ウェイト、行の
高さはそちらに従う。Gengou Code が持つ字はすべて 1 セルのまま。漢字・
かなや、Source Han Sans にしかない字は Source Han Sans の全角のまま。

| ファミリー | 半角 : 全角 | 向いている用途 |
|------------|-------------|----------------|
| Gengou Code JP | 600 : 1000（3:5） | エディタ。和文は Source Han Sans の送り幅のまま |
| Gengou Code JP Term | 600 : 1200（1:2） | グリッドに並べないアプリで、ターミナルのように桁を揃えたいとき。全角は 2 セルの中央に置く |

ターミナルの中では、文字の置き場所をターミナルが決めるので、2 つは同じに
見える。どちらも 5 ウェイト × 直立・斜体の静的 OTF。斜体は Gengou Code
の斜体に、直立の和文を組み合わせたもの。和文のウェイトは、`＝` の横棒の
太さが合う Source Han Sans の面を使う。

| ウェイト | Source Han Sans の面（`＝` の横棒） |
|----------|-------------------------------------|
| Light | ExtraLight（36 ユニット） |
| Regular | Normal（63） |
| Medium | Regular（69） |
| SemiBold | Medium（83） |
| Bold | Bold（101） |

幅について:

- 半角カナ（`ｱ`）などの半角形は 1 セル。Source Han Sans で比例幅だった字
  （ハングルの字母など）は、いちばん近いグリッドの幅の中央に置く。
- 東アジアの文字幅が Wide なのに、ここでは 1 セルの字が 13 ある。
  `☕ 🎵 🎶 💩 🔒 🤖`、ハングルの声調記号 2 字、注音の声調記号 5 字で、
  どの上流にも広い形が無い。ターミナルは 2 桁空けるので、左に寄って
  見える。
- 曖昧幅の字を 2 桁で数えるターミナルでは、`①` などが右隣にはみ出す。
  ターミナル側で曖昧幅を 2 桁にすれば直る。Windows Terminal なら
  `"compatibility.ambiguousWidth": "wide"`。
- 半角と全角を切り替える機能は無い。`fwid` と `hwid` は v6.0.0 で外した。
  エディタは feature をバッファ全体に掛けるので、`fwid` を入れると
  英字まで全角になっていた。全角の形が欲しいときは、全角の文字そのもの
  （`＝` `｜` `＋`）を使う。
- Source Han Sans の `kern`、`palt`、`halt`、`pwid` は外してあり、字が
  グリッドからずれることはない。縦書き（`vert`、`vrt2` と縦組み用の
  メトリクス）はそのまま使える。

行の高さは Gengou Code と同じ 984 / −273。`usWinAscent` と
`usWinDescent` は 1160 と 454 にしてあり、GDI のアプリ（旧 conhost、
メモ帳、Office）でも和文や罫線が欠けない。その代わり、それらのアプリ
では行が広めになる。

## 名前

源合は、源ノ角ゴシックが「Source」に当てた「源」と、合字の「合」を
合わせたもの。「合」には、上流のフォントを合わせるという意味もある。
「Source」は SIL Open Font License の予約フォント名なので、そのままでは
使えない。

## ビルド

フォントは上流のリリースから CI で組んでいる。このリポジトリに元の
グリフは入っていない。ローカルでのビルドやテスト、リリースの流れは
[CONTRIBUTING.ja.md](CONTRIBUTING.ja.md) にある。

## ライセンス

[SIL Open Font License 1.1](LICENSE)。上流の Source Code Pro、
Source Sans 3、Source Han Sans（Adobe）、Monaspace（GitHub）と同じ。
予約フォント名に従い、ファミリー名には「Source」も「Monaspace」も
含めていない。Nerd Fonts のアイコンは MIT ライセンス。
