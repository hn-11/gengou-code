# Gengou JP

英語圏プログラミングフォントの設計流儀に基づき、日本語環境向けに再構築したフォント。欧文は [Source Code Pro](https://github.com/adobe-fonts/source-code-pro)（原寸・原太、名前付きインスタンスそのまま）に [Monaspace](https://github.com/githubnext/monaspace) の記号および合字 61 種を融合させた **Gengou**、和文は [Source Han Sans](https://github.com/adobe-fonts/source-han-sans) JP を Gengou の太さに適した面から選択して合成している。基準は欧文側に置かれており、セル幅（600）、ウェイト（Light / Regular / Medium / SemiBold / Bold）、行間（984 / −273 = 1.257 em）はすべて Source Code Pro の仕様に準拠している。CI で自動合成し、上流の最新リリースにも自動追従する。

## ファミリー構成

| ファミリー | 半角:全角 | 用途 |
|-----------|-----------|------|
| Gengou JP | 600:1000 (3:5) | エディタ用。和文は Source Han Sans の送り幅を保持 |
| Gengou JP Term | 600:1200 (1:2) | ターミナルのグリッド表示に合わせたいアプリ向け。全角の送り幅を 2 セルに広げてグリフを中央配置 |
| Gengou | 600 | 欧文のみ（可変フォント） |

ターミナル環境内では JP と Term は同様に描画される（全角文字は 2 セルに配置）。
異なる点は全角の送り幅のみであり、Latin・記号・幅の方針は共通である。

各ファミリーは 5 ウェイト × 2 スタイル（Upright / Italic — Italic は Source Code Pro 本来のイタリック、和文は直立のまま）で構成される。ウェイトは Source Code Pro の名前付きインスタンスを採用し、和文は `=` のバー厚が合う Source Han Sans の面を実測して割り当てている:

| ウェイト | usWeightClass | Source Code Pro の `=` バー | Source Han Sans の面（`＝` バー） |
|---------|---------------|-----------------------------|-----------------------------------|
| Light | 300 | 37u | ExtraLight（36u） |
| Regular | 400 | 62u | Normal（63u） |
| Medium | 500 | 73u | Regular（69u） |
| SemiBold | 600 | 83u | Medium（83u） |
| Bold | 700 | 104u | Bold（101u） |

Source Han Sans の Light（49u）と Heavy（120u）、および Source Code Pro の ExtraLight（28u）と Black（120u）はペアとなるウェイトが存在しないため提供していない。

行の高さは `hhea` = `typo`（984 / −273、1.257 em）で、`USE_TYPO_METRICS` を有効化している。`usWinAscent` / `usWinDescent` は 1160 / 454 に設定されている。これはクリッピング境界の役割も兼ねており、Source Han Sans のインクは 984 を超えるため typo に合わせると GDI 環境で下端が欠ける原因となる。そのため、上端は Source Han Sans の宣言値 1160 を維持し、下端は欧文レイヤーの罫線素片（−400）とブロック要素（−454）を覆うため 288 から引き下げている（欧文ファミリーが同じインクに対して宣言している値と同一）。代わりに GDI 環境（旧 conhost、メモ帳、Office の GDI 描画経路等）では行高が 1614u となる。なお、この面のインクは 1808 / −1048 まで存在するが、バウンディングボックス全体を覆うと GDI の行高が 2856u（typo の 2.3 倍）まで肥大化するため、全体は覆っていない。cmap 上で 454 の外側に残るのは U+3031 / U+3032（縦書きの繰り返し記号、−549）の 2 文字のみであり、Source Han Sans 自体も 288 のまま同一の字形を出荷している。

## 幅の方針

**Gengou が含む文字はすべて 1 セル**。Latin、ギリシャ、キリル、アクセント付き文字、罫線素片、`←` `→` `↑` `↓` `⇐` `⇒` `⇔` `≠` `≤` `≥` `…` もすべて 1 セルであり、標準的な欧文ターミナルフォントの仕様と同一である。Source Han Sans にしか存在しない文字（漢字・かな・`①` `※` など）は Source Han Sans の全角のまま保持する。
Unicode の半角ブロック（`ﾡ` など）はターミナルが 1 桁分しか割り当てないため、Source Han Sans が全角の互換字母と同じグリフを割り当てている場合でも 1 セル版を生成して置換している。Source Han Sans がプロポーショナル幅で保持している半角カナ（500）などは、その送り幅に最も近いグリッド（セル幅または全角の倍数）内に中央配置する。
ギリシャ・キリル文字は直立・斜体ともに 234 文字を欧文レイヤー側で保持している。直立は Source Code Pro の字形をそのまま採用（元から 1 セル幅）。**斜体は [Source Sans 3](https://github.com/adobe-fonts/source-sans) Italic から流用している**（Source Code Pro Italic はキリル文字を一切持たず、ギリシャ文字も `π` のみという Adobe の意図的な設計によるため）。Source Code Pro は Source Sans をベースに制作された書体であるため、実測値として italicAngle（−11.0）と cap height が一致し、x-height も 1 ユニット差（wght 400 / 700 の両方）に収まる。ただしプロポーショナル幅であるため、送り幅を 1 セルに設定して中央配置し、インクがセル内に収まらない文字（基準ウェイトで 43 文字）のみセル左右に 8u ずつの余白を残して収めている（`build.cell_fit`）。8u は Source Code Pro が `w` `W` に与えているサイドベアリングであり、過度な凝縮を防ぐため必要な文字にのみ適用している。アクセントの位置指定に関しても Source Sans のベースアンカーを取り込んでいるため、`а́` `И́` `ε̈` のような分解済みの組み合わせでも文字の上に適切に配置される（従来は斜体面のみ位置指定が存在せず、アクセントが隣のセルにはみ出ていた）。等幅フォントが幅広の文字を収める際と同様の処理であり、Source Code Pro 自身の `M` も 600 セル幅に収められている。

この 2 つの文字体系は双方とも東アジア文字幅（EAW）が曖昧（Ambiguous）であり、ターミナルでは 1 桁として扱われるため、欧文レイヤー側で両スタイルとも 1 セルとして保持することが必須要件となる。Source Han Sans 側にも 115 文字が存在するが、それらは Source Code Pro の 234 文字に完全に含まれるため、JP 面においても一切使用されない（`narrow_letters` は上流変更時の安全策として保持しており、現在のビルド出力における `letters=0` がそれを示している）。

例外として、Unicode の東アジア文字幅が Wide でありながら 1 セルで表示される文字が 13 文字存在する（`☕` `🎵` `🎶` `💩` `🔒` `🤖` および Hangul 声調記号 2 文字、注音の入声 5 文字）。これらいずれも片方のフォント（供給元）にしか存在せず（前者の 6 文字は Source Code Pro の 600、注音 5 文字は Source Han Sans の 600、声調記号 2 文字は Source Han Sans の 250 を `fit_to_grid` で 1 セル配置）、ターミナル側が 2 セル分を確保するため左寄りに表示される。Source Code Pro / Source Han Sans 共にこれ以上幅広の字形が存在しないため、`fwid` による代替形式も提供していない。

JIS 慣例の全角字形は `fwid` で復元できる。矢印 7 種は合字グリフ（`->` `=>` `<=>` の鏡像・回転）から Source Han Sans のインク長に合わせて抽出した全角版、`≠` `≤` `≥` `…` や罫線は Source Han Sans 自身の全角グリフ、`A` など Source Han Sans が `fwid` 形を持つ文字はその形状（`Ａ`）が適用される。

```jsonc
// VS Code で矢印や罫線を全角表示にする場合
"editor.fontLigatures": "'fwid'"
```

横方向の送り幅を動かす機能は組み込んでいない。Source Han Sans の `kern`（標準で有効化。`あ`+`て` をセルより 20u 詰める処理）や、代替メトリクスの `halt` / `palt` / `pwid` はビルド時に除去している。縦組み機能（`vert` `vrt2` `vkrn` `vhal` `vpal`）は維持されており、縦書き表示は従来通り動作する。

曖昧幅（EAW=A）の文字を 2 セルとしてカウントするターミナル環境では `①` が右隣のセルにはみ出る。これは HackGen 等と同様の挙動であり、Windows Terminal では `"compatibility.ambiguousWidth": "wide"`、iTerm2 / WezTerm では同等の設定で 2 セル割り当てることで正常に表示できる。

## 合字一覧

**Monaspace 由来の 61 種**を収録（[githubnext/monaspace](https://github.com/githubnext/monaspace) v1.400、OFL）。
代表例: `!=` `==` `===` `!==` `<=` `>=` `->` `<-` `=>` `~>` `:=` `::`
`<<=` `>>=` `=<<` `|>` `<|` `<>` `</>` `//` `#[` `...` `&=` `||` `!~` `=~`
`~~>` `<!--` `&&=` など（全 61 種）。全リストは `data/mona_ligs.json` を参照。

移植対象は合字グリフおよび単独の ASCII 記号全 32 文字（`` !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ ``）。英数字やその他の文字は Source Code Pro のまま保持している。

記号類をすべて Monaspace 側に統一した理由は、合字自体が Monaspace 製であるため、単独文字と合字とで記号の骨格が異なると文字が隣接した際に不自然な継ぎ目が生じるためである（`#` と `#[`、`-` と `->`、`/` と `//` など）。最初に移植した `=` `<` `>` `|` `~` は単独文字と合字で形状自体に食い違いが存在していた（`=` と `==` のバー間隔が SCP 152u / Monaspace 197u、`<` と `<=` のサイズおよび角度、`|` と `||` の高さ、`~` と `~>` の振幅の違い）。残りの記号はおおむね垂直方向のサイズ差であり、Monaspace の cap 高・x-height が SCP より高いため `!` `&` `?` `:` `;` は 16〜67u 上昇し、括弧類や `#` `@` `$` は 60〜150u 高く最大 96u 幅も広くなるが、いずれもセル内に収まりターミナル表示サイズでは 2 ピクセル未満の微差に留まる。`-` は `=` より 110u 短いが、これは Monaspace 本来のデザイン仕様によるものである。SCP の `cv14`/`cv15`/`cv16`（タイポグラフィックなハイフン・アスタリスク・スラッシュ付きドル記号）を有効化すると、`-` `*` `$` は SCP の字形に復元される。なお、欧文単独ファミリー（Gengou）においてハイフンを置換する `cv14`（および `salt` `ss11`）を有効化した場合、`->` `<-` `-->` `<--` `<->` `<-->` `<!--` `-~` `~-` の 9 つの合字は無効化される。これは供給元フォント自身の異体字ルックアップが合字の連鎖処理より前段に配置されているためである。和文ファミリー（Gengou JP / JP Term）では `import_scp_variants` が後段に追加されるため合字が保持され、両ファミリー間で挙動が異なる。

結合記号のうち `U+031A` `U+031B` `U+0334` `U+0344`（イタリックでは `U+0310` も含む）は、Source Code Pro が本来付与される文字（`U+25CC`、オーバーレイは `L` `l`、ホーンは `O` `U` `o`）にのみアンカーを保持している。欧文ファミリーは供給元の字形をそのまま利用するため、それ以外の文字の上ではシェーパーが位置調整を行わず、記号は隣のセルに描画される（供給元フォントと同様の挙動）。和文ファミリーでは移植処理時に結合記号を 1 セル左側に描画するため、同一の組み合わせであっても文字の上に適切に配置される。

線の太さは**フォント面ごとに** Source Code Pro インスタンスの `=` バー厚を実測し、Monaspace VF の wght を二分探索で一致させたインスタンスから取り込んでいる。Italic 面では slnt 軸により傾斜を連動させ（SCP Italic は −11° であり Monaspace の slnt 下限と一致するためシアー処理は発生しない。コード内の −12° は角度非宣言フォント用のフォールバック）、ベースラインは両フォントの `=` 縦中心に揃えている。
Monaspace VF の wght 軸下限（200）は `=` バー厚 53u であり SCP Light の 37u に届かないため、Light では Monaspace 由来のアウトラインを片側 8u 内側に削って（pathops でストローク幅 2d を差し引く）太さを合わせている。
GSUB テーブルには `calt` と `liga` の両方を登録し（すべての合字が標準で有効）、加えて Monaspace 由来の**グループ別 stylistic set** を備えているため、`calt` を無効化して必要なグループのみを個別で有効化できる:

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

さらに **Source Code Pro 自身の字形バリアントもそのまま利用できる**:
`zero`（スラッシュゼロ切替）、`cv01`〜`cv17`（`a` の一階建て、`g` の形状など SCP 純正の異体字）、`salt`、および SCP の stylistic set を 10 ずらして割り当て（ss11〜ss17。ss01〜ss08 は合字グループが使用）。

```jsonc
// 例: !== の一体化が読みにくい場合、比較系だけ無効化して矢印は残す
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss05', 'ss06', 'ss07', 'ss08'"
```
ss01〜08 はグループごとに独立したルックアップのため、`calt` を無効化したまま複数のグループを同時に有効化すると、短めのパターン（ss01 の `>=`）が長めのパターン（ss02 の `>>=`）の前半部に干渉する場合がある。これは Monaspace 本家と同様の仕様である。複数のグループを組み合わせる際、安全性を重視する場合は `calt` の使用を推奨する。

`:=` と `::` は Monaspace 内でも文脈依存の字形切替（`colon.case`）で実現されているため、同様のグリフ合成処理を行っている（実レンダリング結果と誤差 1 ユニット未満で一致）。同一手法により `&&` `++`（`&` `+` の init/fina 変種）、`..<` `.=`（ピリオドの位置を引き上げた変種）、`:>` `<:`（コロンの位置を引き上げた変種）も合成して導入している。

## Nerd Fonts 版

すべての面において Nerd Fonts のアイコングリフを追加したバリエーションを生成する。アイコンを 1 セル内に収めるため、Nerd Fonts 本家の命名規則では **Mono** に該当し、ファミリー名は `Gengou JP Nerd Font Mono` / `Gengou JP Term Nerd Font Mono` / `Gengou Nerd Font Mono`（PostScript 名: `GengouJPNFM-*` 等。`JetBrainsMono Nerd Font Mono` と同様の形式）となる。

ただし、そのままの名称では Windows GDI の `LOGFONT.lfFaceName` 制限（31 文字）を超過する面が発生する（非 RIBBI 面は名前にウェイト名が付加されるため `Gengou JP Term Nerd Font Mono SemiBold` で 38 文字となる）。そのため、**nameID 1 に限り `NFM` と短縮表記している**（`Gengou JP NFM` / `Gengou JP Term NFM` / `Gengou NFM`。最長の `Gengou JP Term NFM SemiBold` で 27 文字）。nameID 16 / 4 は正式名称を維持しているため、Windows Terminal・VS Code・macOS・Linux のフォント選択一覧には `Gengou JP Term Nerd Font Mono` が表示され、**旧 conhost・メモ帳・Office 等の GDI 描画経路にのみ短縮名 `Gengou JP Term NFM` が表示される**。設定の際は使用環境のピッカーに表示されている名称を指定する。これは本家 font-patcher の `--windows` オプションと同様の手法である。

アイコンの追加は font-patcher を介さず、Nerd Fonts が配布している記号専用フォント `Symbols Nerd Font Mono`（`NerdFontsSymbolsOnly.zip`）から fontTools を用いて直接移植している。これにより `--complete --mono` でパッチを適用した場合と同一の記号集合・同一の 1 セル送り幅を実現し、FontForge による変換処理（CID 構造の平坦化、STAT 情報の消失、メタデータの再構築）を回避して 1 面あたり 10 秒程度で処理を完了できる。寸法は本家と一部異なり、`docs/gengou-plan.md` に測定値を記載している（本家は縦長の領域 600 × 856 に収めるが、本フォントでは記号フォント自体の正方セルサイズのまま 600 × 600 としている）。
寸法は font-patcher 自身のグループ別規則に準拠している（`icon_transform`）。

| グループ | font-patcher の指定 | 寸法 |
| --- | --- | --- |
| 通常のアイコン | `pa` | セル幅 / 記号フォントの em（600 / 2048）で一律設定。行ボックスの中央に配置。この縮尺でセルや行の外にはみ出るもののみ、セルと行に収まるよう調整して中央配置 |
| 拡張グループ（`SEPARATORS` および `PROGRESS`。Powerline 区切り 32 文字と進捗バー 6 文字） | `^xy` | インク領域をセル幅と行高全体いっぱいに拡大。記号フォントに設定された食み出し量（font-patcher の `overlap`）は比率を維持。両端が食み出しているもの（進捗バーの中間要素）は両端とも保持 |
| 行ボックス基準で描画されるその他（U+E0A0〜E0A3 のブランチ・鍵アイコン等、U+E0CE〜E0D1 の行番号・桁番号） | `^pa` | 縦横比を維持したまま、セル幅と行高のうち先に境界に達する側に収める（桁番号 U+E0CE は幅基準で行高の 45%、ブランチ U+E0A0 は行高全体にフィット） |

記号フォント自体は正方形セル（2048 × 2048）用に設計されているため、区切り記号は font-patcher の `xy-ratio`（0.7 等）で上限が設定された幅（2048 中 1447）のみを保持する。本フォントのセルは 600 × 1257 と縦長で上限値に達しないため、インクはセル全体に拡大される。Source Code Pro 自身が保持する Powerline 記号（U+E0A0〜E0A3、E0B0〜E0B3）は記号フォント側のグリフで置換している。
アイコンにはヒント情報を付与していない（font-patcher の出力仕様と同様）。Nerd Fonts 自身のライセンス（MIT）は NF 版 zip 内に `LICENSE-NerdFonts` として同梱している。

## Gengou（欧文単体版）

Gengou JP で使用される欧文レイヤーを、可変フォント（VF）から直接ビルドした和文なしの単体フォント。JP 側（`build.py`）はこのフォントを Source Han Sans に合成する構成をとっており、欧文に関する設計構成が一元化されている。

ベースは Source Code Pro VF の名前付きインスタンス（wght 300 / 400 / 500 / 600 / 700）を、fontTools の CFF2ToCFF で静的 CID-keyed CFF に変換したものを使用している。SCP 自身のアウトライン・アライメントゾーン・GSUB（`cv01`〜`cv17` `zero` `salt`、SCP の stylistic set は `ss11`〜`ss17` に移動）・GPOS（マーク位置決め）はそのまま保持される。インスタンス化の際にヒント情報が失われるため、SCP 自身のゾーンに対して otfautohint で全体を再ヒント処理している。その上に Monaspace 由来の合字 61 種・ASCII 記号 32 文字・1 セル矢印（SCP 未収録の `⇔` も追加）を太さおよびベースラインを揃えて合成し、cffsubr でサブルーチン化している。結合文字は SCP の標準仕様（スペーシング設計、GPOS mark による位置決め）を維持しているが、**位置決めはすべての文字に行き渡るよう補正されている**。SCP と Source Sans はどちらもギリシャ・キリル文字の 3 分の 1 程度にしかベースアンカーを含んでおらず、アンカーの存在しない文字ではスペーシング設計の結合文字が送り幅を 0 に調整された結果、**次の文字の上にずれて表示される**問題が存在していた。そのため、各 mark ルックアップが保持するアンカーの規則を適用し、カバーされていない文字に対しても同様の規則でアンカーを自動付与している（`build.anchor_loose_letters`）。

Regular は 1,632 グリフ、Italic は 1,585 グリフで構成される（cmap 収録数はどちらも 1,335 で同一。SCP Italic VF のグリフ数が少ないことによる差異であり、ギリシャ・キリル文字および拡張領域は Source Sans 3 Italic から補完しているため符号位置の網羅性は直立と一致する）。垂直メトリクスは SCP 自身の hhea（984 / -273）を基準とし、OS/2 typo を hhea と同値に設定して `USE_TYPO_METRICS` を有効化し、win メトリクスはファミリー全体のバウンディングボックスを覆う値（1060 / 454）に調整している。

**可変フォント**: 配布用 Gengou は `scripts/build_latin_vf.py` により同一レシピを CFF2 可変フォントとしてビルドした `Gengou[wght].otf`（Upright）および `Gengou-Italic[wght].otf`（Italic）である。wght 軸は usWeightClass の値であり、名前付きインスタンスは静的面と同様に 300 / 400 / 500 / 600 / 700（既定値 400 = Regular）となる。ユーザー wght は SCP の wght そのものであり、その中間値は SCP 自身の avar 折れ線を通して補間される。SCP の VF はユーザー wght に対して非線形であるため、この補間を引き継ぐことで中間ウェイトにおける SCP との整合性を維持している。マスターは SCP VF 自身のマスター位置（wght 200 / 400 — CFF2 VarStore より実測）に Bold の位置（軸上限）および Monaspace の下限位置（Monaspace の wght 200 バー厚が SCP バー厚と一致する SCP wght。約 365）を加えた 4 つで構成される。SCP 側のマスターは fontTools instancer の整数丸めを無効化して生成している。重なり除去およびヒント付与・サブルーチン化はマスター間のポイント対応崩壊を防ぐため行わない（ヒント付けは静的面側で実施）。軽量側では Monaspace 由来の記号・合字が下限の太さで停止するため、可変フォントの Light インスタンス（wght 300）では `=` バー厚が 53u（静的 Light の 37u に対し直立 +43%・斜体 +56%）となり、ASCII 記号 32 文字・矢印・不等号および合字 63 文字の計 106 グリフの黒み面積が 43〜56% 太くなる。同一インスタンス内で文字領域が Regular の 56% まで軽くなる一方で記号領域は 86〜92% に留まるため、**Light においては文字と記号の黒み濃度が完全には一致しない**。静的 Light では erosion 処理によって双方の太さを適合させている。なお、静的面は JP 面の合成ドナーおよび Nerd Fonts 版の入力用であり、単体での配布は行わない。

名称の**源合**（げんごう）は、源ノ角ゴシックおよび Source Code Pro が共有する `Source` の訳字「源」と、合字の「合」（および 4 つの上流フォントを組み合わせる「合成」の合）を組み合わせたものである。OFL の Reserved Font Name 規定により英語の `Source` が制限されているため、漢字表現に置き換えている。詳細な由来・衝突調査・欧文層分離の経緯については [docs/gengou-plan.md](docs/gengou-plan.md) を参照。

## インストール

[Releases](../../releases) より用途に合わせてアセットを選択する。すべての zip に OFL ライセンス全文（LICENSE）を同梱している。

- **`GengouJP.zip` / `GengouJPTerm.zip`**: 各ファミリーの zip ファイル（5 ウェイト × 2 スタイルの 10 面、個別 OTF）。必要なファミリーおよびウェイトを選択してインストール可能。
- **`GengouJP-NerdFont.zip` / `GengouJPTerm-NerdFont.zip`**: 同一構成の Nerd Fonts 対応版（ファミリー名: `Gengou JP Nerd Font Mono` 等）。ターミナルのプロンプト装飾（アイコン表示）に使用する場合はこちらを選択する。
- **`Gengou.zip`**: 和文を含まない欧文単体版 Gengou。可変フォント 2 面（`Gengou[wght].otf` / `Gengou-Italic[wght].otf`）。
- **`Gengou-NerdFont.zip`**: Gengou の Nerd Fonts 対応版（`Gengou Nerd Font Mono`）。可変フォントへの合成は行わないため、こちらは 5 ウェイト × 2 スタイルの静的 10 面構成となる。

ダウンロード後、システムにインストールしエディタ等で設定する:

```jsonc
{
  "editor.fontFamily": "Gengou JP",
  "editor.fontLigatures": true
}
```

旧版（`Sumi Moji JP` や `Shoyu Code Pro JP`）とはファミリー名が異なるため共存可能である。置き換える場合は旧版をアンインストールする。

- **macOS**: OTF をダブルクリックして「Font Book」でインストール、または `~/Library/Fonts/` にコピー。
- **Windows**: OTF を右クリックして「インストール」を選択（全ユーザー適用は「すべてのユーザー用にインストール」）。
- **Linux**: `~/.local/share/fonts/`（ユーザー単位）または `/usr/local/share/fonts/`（全ユーザー）にコピーし、`fc-cache -f` を実行。

ビルドや合字の追加・改造については [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ビルド

4 つの上流フォント（Source Han Sans JP / Source Code Pro VF / Source Sans 3 VF / Monaspace VF）および Nerd Fonts 版用の `Symbols Nerd Font Mono` を取得し、環境変数でパスを指定する。ビルドは 2 段階で進行し、まず `scripts/build_latin.py` が VF から Gengou（`dist/latin`）を生成し、その生成物を `scripts/build.py` が Source Han Sans に合成する。具体的なビルドコマンドは `.github/workflows/ci.yml` を参照。

```sh
pip install -r requirements.txt
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=...
python scripts/build_latin.py           # dist/latin/Gengou-*.otf（10 面）
python scripts/build_latin_vf.py        # dist/latin/Gengou[wght].otf, -Italic[wght].otf
python scripts/build.py                 # 両ファミリー（JP / Term × 10 面）
python scripts/build.py "Regular"       # Regular系のみ（動作確認用）
python scripts/verify_latin.py dist/latin/Gengou-Regular.otf        # Gengou の回帰テスト
python scripts/verify_latin_vf.py "dist/latin/Gengou[wght].otf"     # 可変版（SCP と突き合わせ）
python scripts/verify.py dist/GengouJP-Regular.otf   # JP の回帰テスト
python scripts/golden.py <前の dist> dist                  # 2つのビルド出力の比較
NF_SYMBOLS=... python scripts/nerdpatch.py                 # Nerd Fonts 版
```

`SCP_VF_U` / `SCP_VF_I` / `SS_VF_I` / `MONA_VF` は欧文ビルド用の 2 つのスクリプト（`build_latin.py` および `build_latin_vf.py`）で使用し、それぞれ Source Code Pro VF / Source Sans 3 VF / Monaspace VF の Releases から取得する。`SS_VF_I` は斜体のギリシャ・キリル文字にのみ使用されるが、直立のみをビルドする場合でも指定が必須となる（未指定の場合、斜体ビルド時に文字が欠落するため）。`build.py` は Source Code Pro / Monaspace の VF に直接アクセスせず、代わりに `SHS_DIR`（Source Han Sans JP）および `LATIN_DIR`（標準: `dist/latin`、`build_latin.py` の出力先）を参照する。`verify.py` および `verify_latin_vf.py` は `SCP_VF_U` / `SCP_VF_I` が存在する場合に `=` バー厚を Source Code Pro インスタンスと照合する。
`GENGOU_VERSION`（例: `6.0.0`）を指定すると name テーブルに版番号が記録される（リリースワークフローがタグから指定。未指定時は上流のリビジョン番号を維持）。

`requirements.txt` には AFDKO（`otfautohint` による再描画グリフへのヒント付与用）が含まれる。ローカルでのテストビルド時間を短縮したい場合は `GENGOU_SKIP_AUTOHINT=1` を指定することでヒント付けをスキップできる。Term の全角グリフ約 1.7 万個は再描画を行わず charstring 内で 100 ユニット右移動（`shift_charstring`）させるため、Source Han Sans 自身のヒントが維持され、ヒント再付与処理は各面で再描画された約 2,250〜2,650 グリフ（欧文レイヤー、`fwid` 全角形、再配置されたプロポーショナル文字、Term 拡張罫線等）のみで完了する。ヒント付与後は cffsubr（AFDKO の `tx`）を用いて CFF をサブルーチン化している。

## 仕組み

- 欧文レイヤーは Gengou（`scripts/build_latin.py` により VF から生成され `dist/latin` に出力）から供給される。Source Han Sans JP（CID-keyed CFF）を土台とし、Gengou が保持する全コードポイント（Regular で 1,335）に対しそのグリフを 1 セル幅で合成して cmap を差し替える。Source Han Sans が保持していた全角グリフは `fwid` 代替として残す。追加 CID は空き領域へ昇順で割り当てている（サブセット OTF の CID が不連続なため）。
- 太さの整合性は Gengou 側（`build_latin.py`）で完結している。各面は SCP の名前付きインスタンスそのものであり、その `=` バー厚に Monaspace VF の wght を二分探索で適合させ、Italic 面は SCP Italic VF に合わせ slnt 軸を連動させている。`build.py` は Gengou を無変換で適用し、和文側はバー厚の適合する Source Han Sans の面を使用している（`build.FACES`）。
- 合字機能は LigatureSubst を使用。`calt`/`liga` は結合ルックアップ 1 つおよび文脈ガード（各合字の入力列全体をカバーするトリガールールを最長一致順に配置）で構成され、ss01〜08 はグループ別ルックアップ、cv99 は .alt 切り替えを担当する。
- 欧文供給元の `locl` 機能も移植している（`import_scp_locl`）。ギリシャ文字ではアクセント（トノス）を除去して気息記号が合成される。登録は供給元と同一のスクリプト・言語ペアに対してのみ実行する。
- 欧文供給元の GPOS（`mark` / `mkmk` / `ccmp`）も移植している（`import_scp_marks`）。Source Code Pro は結合記号の位置調整を GPOS で定義しているため、これがない場合アクセントが `b d f h k l` 等の上伸部を貫通する現象が発生する。
- 欧文供給元の `ccmp`（標準で有効）も JP 面へ移植している（`import_scp_ccmp` がグリフ名と入れ子ルックアップ番号を書き換えて適用し、機能上必要でありながら移植データに含まれないグリフを追加 — 正体 62 文字・斜体 46 文字）。`i` + U+0307 は点なしの `ı` に置き換わり、`g̃` `ê̆` `ї́` 等は合成される。
- 行間は Source Code Pro の設定値（hhea = typo = 984 / −273 / 0、`USE_TYPO_METRICS`）を採用。win メトリクスは 1160 / 454（上端は Source Han Sans 宣言値、下端は欧文の罫線・ブロック要素を覆う値）。等幅メタデータ（`post.isFixedPitch` / PANOSE bProportion=9 / xAvgCharWidth）は各面ごとに独自に計算・実測し、Windows Terminal 等の選択一覧に正しく表示されるよう設定している。
- 欧文・合字・（Term における）拡張全角グリフ等、T2CharStringPen で描画されたグリフは、最終アウトラインに基づくアライメントゾーン付き専用 CID FontDict を割り当てた上で AFDKO otfautohint によりヒントを付与している（Source Han Sans 由来のグリフは元のヒントを維持）。

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-sans/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は `Source` および `Monaspace` を含まない `Gengou JP` / `Gengou` としている。
