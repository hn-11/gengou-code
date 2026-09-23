# Gengou Code

[English](README.md)

Gengou Code（源合）は、プログラミングとターミナル向けの等幅フォントです。英字は[Source Code Pro](https://github.com/adobe-fonts/source-code-pro)を原寸・原ウェイトのまま使っています。記号と61種の合字は[Monaspace](https://github.com/githubnext/monaspace)から取り込み、ウェイトごとに線の太さをSource Code Proに合わせています。

可変フォント（ウェイト200〜700）として配布しており、名前付きウェイトはLight、Regular、Medium、SemiBold、Boldの5つです。いずれにもイタリック体があります。Nerd Fonts版も用意しています。

日本語を含む**Gengou Code JP**も、関連ファミリーとして配布しています。和文は[Source Han Sans](https://github.com/adobe-fonts/source-han-sans)（源ノ角ゴシック）から取り込んでいます。詳しくは[Gengou Code JP](#gengou-code-jp)の節を参照してください。

## ダウンロード

[Releases](../../releases)からzipファイルを取得してください。どのzipにもライセンスファイルが含まれています。

| ファイル | 内容 |
|----------|------|
| `GengouCode.zip` | Gengou Codeの可変フォント2本（正体と斜体） |
| `GengouCode-NerdFont.zip` | Gengou Code NF（Nerd Fontsのアイコンを追加したもの） |
| `GengouCodeJP.zip` | Gengou Code JPの静的OTF10書体 |
| `GengouCodeJPTerm.zip` | Gengou Code JP Termの静的OTF10書体 |
| `GengouCodeJP-NerdFont.zip`、`GengouCodeJPTerm-NerdFont.zip` | JPファミリーのNerd Fonts版 |

## インストール

- **macOS**: `.otf`ファイルを開いてFont Bookでインストールするか、`~/Library/Fonts/`にコピーします。
- **Windows**: `.otf`ファイルを右クリックして「インストール」を選びます。全ユーザーに入れる場合は「すべてのユーザーに対してインストール」を選びます。
- **Linux**: `~/.local/share/fonts/`にコピーし、`fc-cache -f`を実行します。

インストール後、エディターやターミナルでファミリー名を指定します。

```jsonc
// VS Codeのsettings.json
"editor.fontFamily": "Gengou Code",
"editor.fontLigatures": true
```

```jsonc
// Windows Terminalのsettings.json（プロファイル内）
"font": { "face": "Gengou Code" }
```

日本語を表示する場合は`Gengou Code JP`を指定してください。

旧名称はSumi Moji（v5.0.0まで）とShoyu Code Pro JP（v3.2.0まで）です。ファミリー名が異なるため同時にインストールできます。置き換える場合は旧版をアンインストールしてください。

## 収録文字

- ラテン文字、ギリシャ文字、キリル文字はSource Code Proのものです。ただしSource Code Pro Italicはキリル文字を持たず、ギリシャ文字も1字しかないため、斜体のこの2つはSource Sans 3 Italicから取り込んでいます。Source Code ProはSource Sansを基に作られた書体で、斜体の角度とキャップハイトが一致します。取り込んだ文字はセルの中央に配置し、幅に収まらない文字（Regular Italicで42字）だけを細くしています。
- ASCIIの記号32字はMonaspaceのものです。単独でも合字の中でも同じ字形になります（`-`と`->`、`/`と`//`、`#`と`#[`など）。
- 収録文字はすべて1セル幅（600ユニット）です。矢印`← → ↑ ↓ ⇐ ⇒ ⇔`、`≠ ≤ ≥ …`、罫線素片も1セルです。
- 行の高さはSource Code Proと同じ984/−273（1.257em）で、`USE_TYPO_METRICS`を設定しています。
- 結合アクセントは、付けられるすべての文字で位置が決まるようにしています。Source Code ProとSource Sansが自前でアンカーを持っているのは、ギリシャ文字・キリル文字の3分の1程度です。

## 合字

Monaspaceの合字61種が、`calt`と`liga`で最初から有効になっています。一覧は[`data/mona_ligs.json`](data/mona_ligs.json)にあります。主な合字は次のとおりです。

`!=` `==` `===` `<=` `>=` `->` `<-` `=>` `:=` `::` `|>` `<|` `</>` `//` `...` `&&` `||` `<!--`

Monaspaceと同様に、合字はグループごとのstylistic setにも分けています。`calt`を無効にして、必要なグループだけを有効にできます。

| feature | グループ | 例 |
|---------|----------|----|
| `ss01` | 等価・比較 | `!=` `===` `<=` `>=` `!~` `=~` |
| `ss02` | 矢印 | `->` `<-` `=>` `>>=` `~~>` |
| `ss03` | マークアップ | `</` `/>` `</>` `<>` `<!--` |
| `ss04` | パイプ | `\|>` `<\|` |
| `ss05` | コロン | `::` `:=` `:>` `<:` |
| `ss06` | ドット | `..` `...` `..<` `.=` |
| `ss07` | コメント | `//` `///` |
| `ss08` | 繰り返し・論理演算・その他 | `\|\|` `<<` `>>` `#[` `#(` `&=` `&&` `&&=` `++` |
| `cv99` | Monaspaceの演算子の代替デザイン | |

```jsonc
// 比較の合字だけを無効にし、矢印などは残す
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss04', 'ss05', 'ss06', 'ss07', 'ss08'"
```

stylistic setはグループごとに別のルックアップになっています。そのため`calt`を無効にして複数のグループを有効にすると、あるグループの短い合字が、別のグループの長い合字の先頭を取ってしまうことがあります（ss02の`>>=`の中にあるss01の`>=`など）。Monaspace本家も同じ動作です。`calt`を使う場合はこの問題は起きません。

## 字形の切り替え

Source Code Proのfeatureはそのまま使えます。

- `zero`: スラッシュ付きのゼロ
- `cv01`〜`cv17`: 一階建ての`a`、別の形の`g`などの異体字（斜体では、Source Code Pro Italicが持たないものは使えません）
- `salt`
- Source Code Proのstylistic set: `ss01`〜`ss08`を合字で使っているため、`ss11`〜`ss17`に移しています

`cv14`、`cv15`、`cv16`を有効にすると、`-`、`*`、`$`がSource Code Proの字形に戻ります。Gengou Code（JPではないほう）で`cv14`、`salt`、`ss11`のいずれかを有効にすると、ハイフンを含む合字9種（`->` `<-` `-->` `<--` `<->` `<-->` `<!--` `-~` `~-`）も表示されなくなります。

## ウェイト

| ウェイト | wght | `=`の横棒の太さ（正体/斜体） |
|----------|------|------------------------------|
| Light | 300 | 37/34ユニット |
| Regular | 400 | 62/58 |
| Medium | 500 | 73/67 |
| SemiBold | 600 | 83/78 |
| Bold | 700 | 104/97 |

各ウェイトはSource Code Proの名前付きインスタンスです。Monaspaceのウェイトは、`=`の横棒がこの太さと一致する値を選んでいます。

Monaspaceの最も細いウェイトでも、横棒の太さは53ユニットあります。そのためwght 365付近（斜体は381付近）より細い側では、英字は細くなり続けますが、記号と合字はそれ以上細くなりません。Lightでは英字のインク量がRegularの56%まで減る一方、記号は86〜92%のままなので、記号が太く見えます。Gengou Code JPのLightはMonaspaceの輪郭を削って太さを合わせているため、この差はありません。

## Nerd Fonts版

NF版はNerd Fontsのアイコンを追加したもので、アイコンはすべて1セルに収めています。ファミリー名は`Gengou Code NF`、`Gengou Code JP NF`、`Gengou Code JP Term NF`で、Cascadia CodeのNerd Fonts版と同じ付け方です。本家の命名規則どおり`Nerd Font Mono`を付けると、Windows GDIが扱える31文字を超える名前ができてしまいます（`Gengou Code JP Term Nerd Font Mono SemiBold`は43文字）。そうなると、古いWindowsアプリケーションでは別の名前で表示されます。なお、本家の命名では`NF`は「アイコンがセルからはみ出してもよい版」を意味しますが、このフォントではすべてのアイコンがセルに収まっています。

アイコンは、Nerd Fontsが配布している記号専用フォント`Symbols Nerd Font Mono`から取り込んでいます。収録するアイコンと1セルの送り幅は`font-patcher --complete --mono`で作ったものと同じです。大きさは少し異なり、font-patcherはこのフォントでは600×856の枠に収めますが、こちらは記号フォントの正方形のセル（600×600）のままです。Powerlineの区切り記号と進捗バーは、セル幅と行の高さいっぱいに引き伸ばしています。Source Code Pro自身のPowerline記号は置き換えています。

Gengou Code NFのアイコンは、どのウェイトでも同じ字形です。Nerd Fontsのライセンス（MIT）は、NF版のzipに`LICENSE-NerdFonts`として同梱しています。

## Gengou Code JP

Gengou Code JPは、Gengou CodeにSource Han Sans JPの和文を加えたファミリーです。基準はGengou Codeの側にあり、セル幅600、ウェイト、行の高さはGengou Codeに従います。Gengou Codeが持つ文字はすべて1セル幅のままです。漢字・かななど、Source Han Sansにしかない文字はSource Han Sansの全角幅のままです。

| ファミリー | 半角:全角 | 用途 |
|------------|-----------|------|
| Gengou Code JP | 600:1000（3:5） | エディター向け。和文はSource Han Sans本来の送り幅 |
| Gengou Code JP Term | 600:1200（1:2） | グリッドに沿って描画しないアプリケーションで、ターミナルのように桁を揃えたい場合向け。全角文字は2セルの中央に配置 |

ターミナルでは文字の配置をターミナル側が決めるため、2つのファミリーは同じように表示されます。どちらも5ウェイトの正体と斜体を静的OTFで配布しています。斜体はGengou Codeの斜体に、正体の和文を組み合わせたものです。和文のウェイトには、`＝`の横棒の太さが合うSource Han Sansの書体を使っています。

| ウェイト | Source Han Sansの書体（`＝`の横棒） |
|----------|-------------------------------------|
| Light | ExtraLight（36ユニット） |
| Regular | Normal（63） |
| Medium | Regular（69） |
| SemiBold | Medium（83） |
| Bold | Bold（101） |

文字幅については次のとおりです。

- 半角カナ（`ｱ`）などの半角形は1セル幅です。Source Han Sansで比例幅だった文字（ハングル字母など）は、最も近いグリッド幅の中央に配置しています。
- Unicodeの東アジアの文字幅がWideであるにもかかわらず、このフォントでは1セル幅の文字が13字あります。`☕ 🎵 🎶 💩 🔒 🤖`、ハングルの声調記号2字、注音符号の声調記号5字で、どの元フォントにも全角の字形がありません。ターミナルは2桁分を確保するため、左に寄って表示されます。
- 曖昧幅の文字を2桁として扱うターミナルでは、`①`などが右隣にはみ出します。ターミナルの設定で曖昧幅を2桁にすると解消します。Windows Terminalでは`"compatibility.ambiguousWidth": "wide"`です。
- 半角形と全角形を切り替える機能はありません。`fwid`と`hwid`はv6.0.0で削除しました。エディターはfeatureをバッファー全体に適用するため、`fwid`を有効にすると英字まで全角になっていました。全角の字形が必要な場合は、全角文字そのもの（`＝` `｜` `＋`など）を使ってください。
- Source Han Sansの`kern`、`palt`、`halt`、`pwid`は削除しており、文字がグリッドからずれることはありません。縦書き（`vert`、`vrt2`と縦組み用のメトリクス）はそのまま使えます。

行の高さはGengou Codeと同じ984/−273です。`usWinAscent`と`usWinDescent`は1160と454にしており、GDIを使うアプリケーション（旧conhost、メモ帳、Officeなど）でも和文や罫線が欠けません。ただし、これらのアプリケーションでは行間が広めになります。

## 名称

「源合」は、源ノ角ゴシックが「Source」に当てた「源」と、合字の「合」を組み合わせた名前です。「合」には、複数の元フォントを合わせるという意味も込めています。「Source」はSIL Open Font Licenseの予約フォント名のため、そのままでは使えません。

## ビルド

フォントは各元フォントのリリースからCIでビルドしています。このリポジトリには元のグリフは含まれていません。ローカルでのビルド、テスト、リリースの流れは[CONTRIBUTING.ja.md](CONTRIBUTING.ja.md)を参照してください。

## ライセンス

[SIL Open Font License 1.1](LICENSE)です。元フォントであるSource Code Pro、Source Sans 3、Source Han Sans（Adobe）、Monaspace（GitHub）と同じライセンスです。予約フォント名の規定に従い、ファミリー名には「Source」も「Monaspace」も含めていません。Nerd FontsのアイコンはMITライセンスです。
