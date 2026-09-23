# Gengou Code JP

英語圏のターミナルフォントの流儀で組んだ、日本語入りのプログラミング
フォント。欧文は [Source Code Pro](https://github.com/adobe-fonts/source-code-pro)
（原寸・原太、名前付きインスタンスそのまま）に
[Monaspace](https://github.com/githubnext/monaspace) の記号と合字 61 種を
載せた **Gengou Code**、和文は [Source Han Sans](https://github.com/adobe-fonts/source-han-sans)
JP を、Gengou Code の太さに合う面から取る。基準は欧文側で、セル幅（600）、
ウェイト（Light / Regular / Medium / SemiBold / Bold）、行間
（984 / −273 = 1.257 em）はすべて Source Code Pro のもの。和文がそれに
従う。CI で合成し、上流の新リリースにも追従する。

## ファミリー構成

| ファミリー | 半角:全角 | 用途 |
|-----------|-----------|------|
| Gengou Code JP | 600:1000 (3:5) | エディタ。和文は Source Han Sans の送りのまま |
| Gengou Code JP Term | 600:1200 (1:2) | ターミナルのグリッドに乗せたい非グリッドのアプリ向け。全角の送りを 2 セルに広げてグリフを中央配置 |
| Gengou Code | 600 | 欧文のみ（可変フォント） |

ターミナルの中では JP と Term は同じに描かれる（全角は 2 セルに置かれる）。
違うのは全角の送り幅だけで、Latin・記号・幅の方針は共通。

各ファミリー 5 ウェイト × 2 スタイル（Upright / Italic。Italic は Source
Code Pro の本物のイタリック、和文は直立のまま）。ウェイトは Source Code
Pro の名前付きインスタンスで、和文は `=` のバー厚が合う Source Han Sans
の面を実測で選ぶ:

| ウェイト | usWeightClass | Source Code Pro の `=` バー（直立 / 斜体） | Source Han Sans の面（`＝` バー） |
|---------|---------------|-----------------------------|-----------------------------------|
| Light | 300 | 37u / 34u | ExtraLight（36u） |
| Regular | 400 | 62u / 58u | Normal（63u） |
| Medium | 500 | 73u / 67u | Regular（69u） |
| SemiBold | 600 | 83u / 78u | Medium（83u） |
| Bold | 700 | 104u / 97u | Bold（101u） |

Source Han Sans の Light（49u）と Heavy（120u）、Source Code Pro の
ExtraLight（28u）と Black（120u）は相手がいないので作らない。

行の高さは `hhea` = `typo`（984 / −273、1.257 em）で、`USE_TYPO_METRICS`
を立ててある。`usWinAscent` / `usWinDescent` は 1160 / 454: これは
クリッピング境界でもあり、Source Han Sans のインクは 984 を超えるので
typo に合わせると GDI 系で欠ける。上は Source Han Sans の宣言値 1160 の
まま、下は欧文レイヤーの罫線素片（−400）とブロック要素（−454）を
覆うために 288 から下げてある（欧文ファミリーが同じインクに対して
declare している値と同じ）。代わりに GDI 系（旧 conhost、メモ帳、
Office の GDI 経路）だけは行が 1614u になる。この面のインクは
1808 / −1048 まであり、bbox を全部覆うと GDI の行が 2856u（typo の
2.3 倍）になるので覆っていない。cmap 上で 454 の外に残るのは
U+3031 / U+3032（縦書きの繰り返し記号、−549）の 2 字だけで、
Source Han Sans 自身も 288 のまま同じ字形を出荷している。

## 幅の方針

**Gengou Code が持つ文字はすべて 1 セル**。Latin、ギリシャ、キリル、
アクセント付き文字、罫線素片、`←` `→` `↑` `↓` `⇐` `⇒` `⇔` `≠` `≤` `≥` `…`
も 1 セルで、英語のターミナルフォントと同じ。Source Han Sans にしかない
文字（漢字・かな・`①` `※` など）は Source Han Sans の全角のまま。
Unicode の半角ブロック（`ﾡ` など）はターミナルが 1 桁しか空けないので、
Source Han Sans が全角の互換字母と同じグリフを割り当てていても 1 セル版を
作って差し替える。Source Han Sans が比例幅で持つ半角カナ（500）などは、
その送り幅がいちばん近いグリッド（セルか全角の倍数）に中央配置する。
ギリシャ・キリルは直立・斜体とも 234 字を欧文レイヤーが持つ。直立は
Source Code Pro の字形そのまま（元から 1 セル）。**斜体は
[Source Sans 3](https://github.com/adobe-fonts/source-sans) Italic から
取る**——Source Code Pro Italic はキリルを 1 字も持たず、ギリシャも `π`
だけだからで、Adobe が手で描き起こしたイタリックの意図的な線引き。
Source Code Pro は Source Sans から起こされた書体なので、実測で
italicAngle（−11.0）と cap height が一致し、x-height も 1 ユニット差
（wght 400 / 700 の両方）。ただし比例幅なので、送り幅を 1 セルにして
中央に置き、インクがセルに収まらない字（Regular Italic で 42 字）だけ、
セルから左右 8u ずつ空けたところまで詰める（`build.cell_fit`）。8u は
Source Code Pro が `w` `W` に与えているサイドベアリングで、詰めると線が
細くなるぶん、詰める字は必要な字だけにしてある。アクセントの位置指定も
Source Sans のベースアンカーを取り込んでいるので、`а́` `И́` `ε̈` のような
分解済みの組み合わせも字の上に乗る（それまでは斜体面だけ位置指定が無く、
アクセントが隣のセルに落ちていた）。等幅フォントが幅広の字に
するのと同じ扱いで、Source Code Pro 自身の `M` も 600。

この 2 文字体系はどちらも東アジア文字幅が曖昧（A）でターミナルは 1 桁
しか空けないので、欧文レイヤーが両スタイルとも 1 セルで持つことが要件。
Source Han Sans にも 115 字あるが、それは Source Code Pro の 234 字に
完全に含まれるため、JP 面でも 1 字も使われない。

例外は、Unicode の東アジア文字幅が Wide なのに 1 セルで出る 13 字
（`☕` `🎵` `🎶` `💩` `🔒` `🤖` と Hangul 声調記号 2 字、注音の入声 5 字）。
どれも片方のドナーにしか無く（前 6 字は Source Code Pro の 600、注音 5 字は
Source Han Sans の 600、声調記号 2 字は Source Han Sans の 250 を
`fit_to_grid` が 1 セルに置く）、ターミナルは 2 桁分を空けるので
左寄りに見える。

**幅を切り替える機能は持たない。** JIS 流の全角の矢印や罫線に戻す
`fwid`、半角に寄せる `hwid` は、v6.0.0 でどちらも落とした。VS Code などの
エディタは feature をバッファ全体にしか掛けられないので、`fwid` を
有効にすると 1 セルの字が全部全角になり（`A` まで `Ａ` になる）、
「罫線だけ全角に」はそもそも頼めない。ターミナルは feature を掛けない。
全角の形が要るなら、Unicode が全角として別に持つ文字（`＝` `｜` `＋` など）を
使う。それらは Source Han Sans の全角のまま入っている。

横方向の送りを動かす機能も入れていない。Source Han Sans の `kern`
（横組みでは既定 ON。`あ`+`て` をセルより 20u 詰める）と、代替メトリクスの
`halt` / `palt` / `pwid` はビルド時に落としてある。縦組みの機能（`vert` `vrt2` `vkrn` `vhal` `vpal`）は
残してあり、縦書きは従来どおり。Term 面は、全角化で動いた字に付く
結合マークの位置を横組み専用の `dist` で補正する。

曖昧幅（EAW=A）を 2 セルとして数えるターミナルでは `①` が右隣に食み出す。
これは HackGen と同じ挙動で、Windows Terminal なら
`"compatibility.ambiguousWidth": "wide"`、iTerm2 / WezTerm なら相当の設定で
2 セル取らせる。

## 合字一覧

**Monaspace 由来の61種**を収録（[githubnext/monaspace](https://github.com/githubnext/monaspace) v1.400、OFL）。
主要どころ: `!=` `==` `===` `!==` `<=` `>=` `->` `<-` `=>` `~>` `:=` `::`
`<<=` `>>=` `=<<` `|>` `<|` `<>` `</>` `//` `#[` `...` `&=` `||` `!~` `=~`
`~~>` `<!--` `&&=` ほか（全61種）。全リストは `data/mona_ligs.json` を参照。

移植するのは合字グリフと、単独の ASCII 記号 32字全部
（`` !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ ``）。英数字やそれ以外の文字は
Source Code Pro のまま。

記号を丸ごと Monaspace に揃えたのは、合字自体が Monaspace 製である以上、
同じ記号が単独字と合字とで違う骨格を持つと隣り合わせたときに継ぎ目が
見えてしまうため（`#` と `#[`、`-` と `->`、`/` と `//` など）。最初に
移した `=` `<` `>` `|` `~` は形そのものが合字と違っていた（`=` と `==` で
バーの間隔が SCP 152u / Monaspace 197u、`<` と `<=` で大きさと角度、`|` と
`||` で上下の伸び、`~` と `~>` で振幅）。残りの記号はおおむね縦のサイズ
違いで、Monaspace の cap 高・x-height が SCP より高いぶん `!` `&` `?` `:`
`;` は 16〜67u 持ち上がり、括弧類や `#` `@` `$` は 60〜150u 高く最大 96u
幅も広い — いずれもセル内に収まり、ターミナルサイズでは2ピクセル未満の
差。`-` は `=` より 110u 短いが、これは Monaspace 自身がそういう字形の
ため。SCP の `cv14`/`cv15`/`cv16`（タイポグラフィックなハイフン・
アスタリスク・スラッシュ付きドル記号）を有効にすると、`-` `*` `$` は
SCP の字形に戻る。なお欧文単独ファミリー（Gengou Code）でハイフンを
差し替える `cv14`（および `salt` `ss11`）を有効にすると、`->` `<-`
`-->` `<--` `<->` `<-->` `<!--` `-~` `~-` の 9 つの合字は出なくなる
——ドナー自身の異体字ルックアップが合字の連鎖より前に並ぶため。
和文ファミリー（Gengou Code JP / JP Term）では
`import_scp_variants` が後ろに足すので合字が残り、両者の挙動は
ここだけ食い違う。

結合記号のうち `U+031A` `U+031B` `U+0334` `U+0344`（イタリックでは
`U+0310` も）は、Source Code Pro が本来付く字（`U+25CC`、オーバーレイ
なら `L` `l`、ホーンなら `O` `U` `o`）にしかアンカーを持たない。
欧文ファミリーはドナーの字形をそのまま使うので、それ以外の字の上では
シェーパーが動かさず、記号は次のセルに描かれる（ドナー自身と同じ挙動）。
和文ファミリーは接ぎ木が結合記号を 1 セル左に描くため、同じ組み合わせ
でも土台の上に乗る。

線の太さは**面ごとに** Source Code Pro のインスタンスの `=` のバー厚を
実測し、Monaspace VF の wght を二分探索で一致させたインスタンスから
取り込む。Italic 面には slnt 軸で傾斜も追随させ（SCP Italic は −11°
——`post.italicAngle` も実測のステム角 11.38° もそう——で、Monaspace の
slnt の下限と一致するため、シアーは掛からない。コード中の −12° は角度を
申告しないドナーへのフォールバック）、ベースラインは両フォントの `=` の
縦中心を揃える。
Monaspace VF の wght 下限（200）は `=` バー厚 53u で SCP Light の 37u に
届かないため、Light では Monaspace 由来のアウトラインを片側 8u 内側に
削って（pathops でストローク幅 2d を差し引く）太さを合わせている。
GSUB は `calt` / `liga` 両登録（全合字が既定で有効）。加えて Monaspace 流の
**グループ別 stylistic set** を備え、`calt` を切って必要な群だけ有効化できる:

| feature | 内容 | 例 |
|---------|------|----|
| ss01 | 比較・等価 | `!=` `===` `<=` `>=` `!~` `=~` |
| ss02 | 矢印 | `->` `<-` `=>` `>>=` `~~>` |
| ss03 | マークアップ | `</` `/>` `</>` `<>` `<!--` |
| ss04 | パイプ | `\|>` `<\|` |
| ss05 | コロン | `::` `:=` `:>` `<:` |
| ss06 | ドット | `..` `...` `..<` `.=` |
| ss07 | コメント | `//` `///` |
| ss08 | 反復・論理・その他 | `\|\|` `<<` `>>` `#[` `#(` `&=` `&&` `&&=` `++` |
| cv99 | 演算子の代替デザイン（Monaspace の .alt） | |

さらに **Source Code Pro 自身の字形バリアントを貫通**させている:
`zero`（スラッシュゼロ切替）、`cv01`〜`cv17`（`a` の一階建て、`g` の形など
SCP 純正の文字変異。cv03 / cv05 / cv13 は SCP 自身に無く、斜体は SCP
Italic が出荷しない cv04・cv07〜cv11 も欠く）、`salt`、SCP の stylistic set は ss11〜ss17 に +10 で
マウント（ss01〜ss08 は合字グループが使用）。

```jsonc
// 例: !== の一体化が読みにくい場合、比較系だけ切って矢印は残す
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss05', 'ss06', 'ss07', 'ss08'"
```
ss01〜08 はグループごとに別のルックアップなので、`calt` を切ったまま複数
グループを同時に有効にすると、片方の短い列（ss01 の `>=`）がもう片方の
長い列（ss02 の `>>=`）の頭を食ってしまうことがある。Monaspace 本家の
stylistic set も同じ挙動なので許容している。グループを跨いだ安全性が
欲しい場合は `calt` を使うこと。

`:=` と `::` は Monaspace 内でも文脈変異（`colon.case`）で実現されているため、
同グリフの合成として取り込んでいる（実レンダリングと誤差1ユニット未満で一致）。
同じ手法で `&&` `++`（`&` `+` の init/fina 変異）、`..<` `.=`（ピリオドを
上げた変異）、`:>` `<:`（コロンを上げた変異）も合成して取り込んでいる。

## Nerd Fonts 版

全面に Nerd Fonts のアイコングリフを追加した変種も生成する。アイコンは
1 セルに収める。ファミリー名は `Gengou Code JP NF` / `Gengou Code JP Term NF` /
`Gengou Code NF`（PostScript 名 `GengouCodeJPNF-*` など。`Cascadia Mono NF` と
同じ流儀）。欧文の Gengou Code NF は可変フォントで、アイコンは
CFF2 の中にウェイトで変化しないグリフとして入っている（Nerd Fonts の
アイコン 10,396 個はウェイトでも斜体でも輪郭が同一なので、変化させる
データが要らない）。

本家の命名（`Gengou Code JP Term Nerd Font Mono`）にしないのは、Windows GDI の
`LOGFONT.lfFaceName`（31 文字）に入らない面が出るため（ファミリー名だけで
34 文字、非 RIBBI は名前にウェイト名が付くので
`Gengou Code JP Term Nerd Font Mono SemiBold` で 43 文字）。`NF` なら最長 `Gengou Code JP Term NF SemiBold` で 31 文字ちょうどに収まり、
Windows Terminal・VS Code・macOS・Linux のピッカーにも、旧 conhost・
メモ帳・Office の GDI 経路にも同じ名前が出る。本家の命名では `NF` は
アイコンがセルからはみ出してよい変種を指すが、このフォントの Nerd Fonts
版はこれ一つで、アイコンはすべて 1 セル。

アイコンは font-patcher で掛けるのではなく、Nerd Fonts が配っている記号
だけのフォント `Symbols Nerd Font Mono`（各リリースの
NerdFontsSymbolsOnly.zip。font-patcher の全記号集合と群ごとの寸法を空の
フォントに適用したもの）から fontTools で接ぎ木する。`--complete --mono`
でパッチしたのと同じ記号集合・同じ 1 セル送りになり、FontForge の往復
（CID 構造の平坦化、STAT の消失、メタデータの復元）が要らず、1 面 10 秒
程度。寸法だけは本家と差があり、`docs/gengou-plan.md` に測定値がある
（本家は縦長の箱 600 × 856 に収めるが、こちらは記号フォント自身の正方
セルのまま 600 × 600）。
寸法は font-patcher 自身の群ごとの規則に合わせる（`icon_transform`）。

| 群 | font-patcher の指定 | 寸法 |
| --- | --- | --- |
| 通常のアイコン | `pa` | セル幅 / 記号フォントの em（600 / 2048）で一律。行ボックスの中央に置く。この縮尺でセルや行の外に出てしまうものだけ、セルと行に収めて中央へ |
| 引き伸ばす群（`SEPARATORS` と `PROGRESS`。Powerline の区切り 32 字と進捗バー 6 字） | `^xy` | インクをセル幅と行の全高いっぱいに引き伸ばす。記号フォントが付けている食み出し（font-patcher の `overlap`）は比率のまま残す。両端が食み出しているもの（進捗バーの中間）は両側とも残す |
| 行ボックスに対して描くその他（U+E0A0〜E0A3 のブランチ・鍵など、U+E0CE〜E0D1 の行番号・桁番号） | `^pa` | 縦横比を保ったまま、セル幅と行の全高のうち先に当たるほうに収める（桁番号 U+E0CE は幅で決まって行の 45%、ブランチ U+E0A0 は行いっぱい） |

記号フォント自体は正方形のセル（2048 × 2048）向けなので、区切りは
font-patcher の `xy-ratio`（0.7 など）で頭打ちになった幅（2048 中 1447）
しか持たない。こちらのセルは 600 × 1257 と縦長で頭打ちに掛からないため、
インクはセルいっぱいに広がる。Source Code Pro 自身が持つ Powerline
（U+E0A0〜E0A2、E0B0〜E0B3）は記号フォントのもので置き換える。
アイコンはヒント無し（font-patcher の出力も同じ）。Nerd Fonts 自身のライセンス（MIT）は NF の zip に `LICENSE-NerdFonts`
として同梱する。各アイコンセットのライセンスは Nerd Fonts のリポジトリに
あり、zip には入らない。

## Gengou Code（欧文のみ）

Gengou Code JP が使う欧文レイヤーを、VF から直接組み上げた和文なしの
単独フォント。JP 側（`build.py`）はこのフォントを Source Han Sans に
そのまま接ぎ木するだけになっており、欧文の設計判断は 1 か所に集まっている。

ベースは Source Code Pro VF の名前付きインスタンス（wght 300 / 400 / 500 /
600 / 700）を、fontTools の CFF2ToCFF で静的な CID-keyed CFF に変換した
もの——SCP 自身のアウトライン・アライメントゾーン・GSUB（`cv01`〜`cv17`
`zero` `salt`、SCP の stylistic set は `ss11`〜`ss17` に移動）・GPOS
（マーク位置決め）はそのまま生きている。その上に
Monaspace 由来の合字61種・ASCII 記号32字・1セル矢印（SCP に無い `⇔` も
追加）を、太さとベースラインを揃えて接ぎ木する。静的面はヒント付けも
サブルーチン化もせずに保存する（JP 面が取り込むグリフを描き直して自分で
ヒントを付けるため）。結合文字は SCP が出荷する形（スペーシング、GPOS mark で位置決め）
のまま——ただし**位置決めは全文字に行き渡らせてある**。SCP と Source Sans
はどちらもギリシャ・キリルの 3 分の 1 程度にしかベースアンカーを持たず、
アンカーの無い文字ではスペーシング設計の結合文字が送りをゼロにされた結果
**まるごと 1 セル右、次の文字の上**に落ちていた。各 mark ルックアップが
自分のアンカーから従っている規則を当てはめて、覆われていない文字に同じ
規則でアンカーを与えている（`build.anchor_loose_letters`）。

Regular は1,632グリフ、Italic は1,585グリフ（cmap はどちらも1,335で同一。
SCP Italic VF のグリフ数が少ないぶんの差で、ギリシャ・キリルとギリシャ
拡張は Source Sans 3 Italic から補っているので符号位置の網羅は直立と
揃っている）。縦メトリクスは SCP 自身の hhea（984 / -273）を
基準に、OS/2 の typo を hhea と同値にして `USE_TYPO_METRICS` を立て、win
はファミリー全面のバウンディングボックスを覆う値（1060 / 454）。

**可変フォント**: 配布する Gengou Code は `scripts/build_latin_vf.py` が
同じレシピを CFF2 可変フォントとして組んだ `GengouCode[wght].otf`
（Upright）と `GengouCode-Italic[wght].otf`（Italic）。wght 軸は
usWeightClass の値で、名前付きインスタンスは静的面と同じ 300 / 400 /
500 / 600 / 700、既定値 400 = Regular。ユーザー wght は SCP の wght
そのもの（SCP のユーザー wght が usWeightClass）で、その間は SCP 自身の
avar の折れ点を通して補間する——SCP の VF はユーザー wght に対して線形
ではないので、これを引き継がないと中間ウェイトが SCP と一致しない。
マスターは SCP VF 自身のマスター位置（wght 200 / 400——CFF2 の VarStore
から実測）に Bold の位置（軸の上限。SCP の 900 マスターは上限の外なので
使わず、SCP が 400〜900 で線形なことを利用して Bold 位置でインスタンス化
する）と Monaspace の下限位置（Monaspace の wght 200 のバーが SCP の
バーと一致する SCP wght、およそ 365。これより細い側では Monaspace が
下限でクランプされる）を加えた 4 つ。SCP 側のマスターは fontTools の
instancer の整数丸めを切ってインスタンス化する。重なり除去とヒント付け・
サブルーチン化はしない（マスター間で点の対応が壊れるため。ヒントは
JP 面の側で付ける）。軽量側では Monaspace 側の記号・合字が下限の太さで
止まる。その差は小さくない: 可変フォントの Light インスタンス（wght 300）
では `=` のバーが 53u——静的 Light の 37u に対して直立 +43%・斜体 +56%——
で、ASCII の記号 32 字・矢印/不等号/省略記号 11 字・合字 61 字の計 104
グリフが墨面積で 24〜71%（中央値 45%。斜体は 30〜84%、中央値 56%）太い。同じインスタンスの中で、文字は Regular の 56% まで軽くなる
のに記号は 86〜92% に留まるので、**Light では文字と記号の濃さが揃わない**。
静的 Light は erosion で両方を揃えている。静的面は JP 面のドナーで、
単体では配布しない。

**源合**（げんごう）は、源ノ角ゴシックと Source Code Pro が共有する
`Source` の訳字「源」と、合字の「合」——4 つの上流を合わせる「合成」の
合でもある——を合わせた名前。OFL の Reserved Font Name が英語の `Source`
を塞いでいるので、漢字で言い換えている。詳しい由来・衝突調査・欧文層を
切り出した経緯は [docs/gengou-plan.md](docs/gengou-plan.md) を参照。

## インストール

[Releases](../../releases) から用途に応じてアセットを選ぶ。いずれの zip にも
OFL のライセンス全文（LICENSE）を同梱している。

- **`GengouCodeJP.zip` / `GengouCodeJPTerm.zip`**: ファミリーごとの zip
  （5 ウェイト × 2 スタイルの 10 面、面ごとの OTF）。使うファミリーだけ
  落として、必要な面だけ入れる（TTC は配らない: リリースの単位は
  インストールするファイルの単位）。
- **`GengouCodeJP-NerdFont.zip` / `GengouCodeJPTerm-NerdFont.zip`**: 同じ
  ファミリー分けの Nerd Fonts 版（ファミリー名 `Gengou Code JP NF` など）。ターミナルのプロンプト装飾（アイコン表示）に使う場合は
  こちら。
- **`GengouCode.zip`**: 和文を含まない欧文のみの Gengou Code。可変フォント
  2面（`GengouCode[wght].otf` / `GengouCode-Italic[wght].otf`）。
- **`GengouCode-NerdFont.zip`**: Gengou Code の Nerd Fonts 版（`Gengou Code NF`）。
  `GengouCode.zip` と同じく可変フォント 2 面（`GengouCodeNF[wght].otf` /
  `GengouCodeNF-Italic[wght].otf`）。アイコンはどのウェイトでも同じ形。

ダウンロードしてインストールし、

```jsonc
{
  "editor.fontFamily": "Gengou Code JP",
  "editor.fontLigatures": true
}
```

v5.0.0 までの `Sumi Moji JP`（v4.0.0 までは 2:3 の基本ファミリーと
35 / Term）や v3.2.0 までの `Shoyu Code Pro JP` とはファミリー名が
違うので共存する。置き換えるなら旧版をアンインストールする。

- **macOS**: OTF をダブルクリックして「フォントブック」でインストール、または
  `~/Library/Fonts/` にコピー。
- **Windows**: OTF を右クリックして「インストール」を選択（全ユーザー適用は
  「すべてのユーザー用にインストール」）。
- **Linux**: `~/.local/share/fonts/`（ユーザー単位）または
  `/usr/local/share/fonts/`（全ユーザー）にコピーし、`fc-cache -f` を実行。

ビルドやリガチャの追加・改造に興味がある場合は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ビルド

4つの上流（Source Han Sans JP / Source Code Pro VF / Source Sans 3 VF /
Monaspace VF）と、Nerd Fonts 版のための `Symbols Nerd Font Mono` を
取得して環境変数で場所を渡す。`scripts/build.py` が VF から Gengou Code の
静的面をメモリ上で組み（`build_latin.py`、ファイルには出さない）、それを
Source Han Sans に接ぎ木する。具体的なコマンドは
`.github/workflows/ci.yml` の手順がそのまま実行可能なリファレンス。

```sh
pip install -r requirements.txt
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=...
python scripts/build_latin_vf.py        # dist/latin/GengouCode[wght].otf, -Italic[wght].otf
python scripts/build.py                 # 両ファミリー（JP / Term × 10 面）
python scripts/build.py "Regular"       # Regular系のみ（動作確認用）
python scripts/verify.py dist/GengouCodeJP-Regular.otf          # 回帰テスト（面ごと）
python scripts/verify.py 'dist/*.otf' 'dist/nerd/*.otf'    # まとめて（配る面だけ）
python scripts/verify.py "dist/latin/GengouCode[wght].otf"     # 可変版（SCP と突き合わせ）
python scripts/golden.py <前の dist> dist                  # 出力が変わる変更の前後比較（CONTRIBUTING）
NF_SYMBOLS=... python scripts/nerdpatch.py                 # Nerd Fonts 版
```

`SCP_VF_U` / `SCP_VF_I` / `SS_VF_I` / `MONA_VF` は欧文を組む
`build.py`（`build_latin.py` 経由）と `build_latin_vf.py` が使い、それぞれ
Source Code Pro VF / Source Sans 3 VF / Monaspace VF の Releases から
取得する。`SS_VF_I` は斜体のギリシャ・キリルにしか使わないが、直立だけを
組む場合も必須（欠けたまま斜体を組むと 2 文字体系が黙って抜けるため）。
`build.py` はほかに `SHS_DIR`（Source Han Sans JP）を見る。`verify_jp.py` と `verify_latin_vf.py` は
`SCP_VF_U` / `SCP_VF_I` があれば `=` のバーを Source Code Pro の
インスタンスと突き合わせる。
`GENGOU_VERSION`（例 `6.0.0`）を立てると name テーブルにその版番号を刻む
（リリースワークフローがタグから渡す。未設定なら上流のリビジョンをそのまま
残す）。

`requirements.txt` には AFDKO（`otfautohint` で描き直したグリフにヒントを
付ける）も含まれる。ローカルでの試しビルドで時間を節約したい場合は
`GENGOU_SKIP_AUTOHINT=1` を立てるとスキップできる。Term の全角グリフ約1.7万個
は描き直さず charstring の中で 100 ユニット右へ動かす（`shift_charstring`）
ので、Source Han Sans 自身のヒントがそのまま残り、ヒント付けは各面で
描き直したおよそ 2,340〜2,440 グリフ（欧文レイヤー、グリッドに
乗せ直した比例幅の残り、Term で伸ばした罫線など）だけで済む。ヒント付与後は cffsubr（AFDKO の
`tx`、`requirements.txt` に同梱）で CFF をサブルーチン化している。

## 仕組み

- 欧文レイヤーは Gengou Code（`scripts/build_latin.py`、VF から先に
  メモリ上で組む）から来る。Source Han Sans JP（CID-keyed CFF）を
  土台に、Gengou Code が持つ全コードポイント（Regular で 1,335）へその
  グリフを 1 セルで接ぎ木し cmap を差し替える。Source Han Sans が持って
  いた全角グリフはフォントに残り、縦組みの `vert` がそこから回転形を
  引く（`repoint_features`）。追加 CID は疎な空間の空きを
  昇順割当（サブセット OTF の CID は不連続なため）
- 太さの一致は Gengou Code 側（`build_latin.py`）で完結している——各面は
  SCP の名前付きインスタンスそのもので、その `=` バー厚に Monaspace VF の
  wght を二分探索で合わせ、Italic は SCP Italic VF + slnt 追随。`build.py`
  は Gengou Code を無変換で載せ、和文はバーの合う Source Han Sans の面を
  使う（`build.FACES`）
- 合字は LigatureSubst。`calt`/`liga` は結合ルックアップ1つ＋文脈ガード
  （各合字の入力列全体をカバーするトリガールールを最長一致順に並べる。
  一致範囲を1文字だけにしてネストした LigatureSubst に残りを委ねる形は
  一致範囲外の消費が OpenType 未定義動作で DirectWrite が非対応だった
  ため）、ss01〜08 はグループ別ルックアップ、cv99 が .alt 切替
- 欧文ドナーの `locl` も移す（`import_scp_locl`）。ギリシャ文字は
  ギリシャのアクセント（トノス）を取り、気息記号が合成される。登録は
  ドナーと同じスクリプト・言語の組にだけ行う
- 欧文ドナーの GPOS（`mark` / `mkmk` / `ccmp`）も移す（`import_scp_marks`）。
  Source Code Pro は結合記号の位置を GPOS に置いているので、これが無いと
  アクセントが `b d f h k l` の上伸部を突き抜ける
- 欧文ドナーの `ccmp`（既定オン）は JP 面にも丸ごと移す（`import_scp_ccmp`
  がグリフ名と入れ子ルックアップ番号を書き換えて写し、機能が描くのに
  接ぎ木に無いグリフを足す——正体 62 字・斜体 46 字。フィーチャに載せる
  のはドナーのフィーチャが挙げていたルックアップだけで、連鎖文脈が呼ぶ
  側は文脈ごしにしか走らない）。`i` + U+0307 は点のない `ı` に替わり、
  `g̃` `ê̆` `ї́` は合成される
- 行間は Source Code Pro の値（hhea = typo = 984 / −273 / 0、
  `USE_TYPO_METRICS`）。win は 1160 / 454（上は Source Han Sans の
  宣言値、下は欧文の罫線・ブロック要素を覆う値）。
  等幅メタデータ（`post.isFixedPitch` / PANOSE bProportion=9 /
  xAvgCharWidth）は各面で独自に設定・実測し、Windows Terminal 等の
  フォント選択に出るようにする
- 欧文・合字・（Term では）拡幅した全角グリフなど T2CharStringPen で
  描いたグリフは、最終アウトラインで測ったアライメントゾーン付きの
  専用 CID FontDict を割り当てたうえで AFDKO の otfautohint によりヒント
  を付与（Source Han Sans 由来のグリフは元のヒントのまま）

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-sans/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は `Source` も `Monaspace` も含まない `Gengou Code JP` / `Gengou Code`（v5.0.0 までは `Sumi Moji JP` / `Sumi Moji`、v3.2.0 までは `Shoyu Code Pro JP`）。
