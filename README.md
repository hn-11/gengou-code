# Shoyu Code Pro JP

Source Han Code JP の設計思想に基づき、最新の上流フォントを組み合わせて再構築したプログラミングフォント。
[Source Han Sans](https://github.com/adobe-fonts/source-han-sans)（和文）+
[Source Code Pro](https://github.com/adobe-fonts/source-code-pro)（欧文、10/9 拡大で 667 幅 — Adobe による SHCJ 作成手順を再現）+
[Monaspace](https://github.com/githubnext/monaspace)（合字 50 種）を
CI で自動合成し、上流の最新リリースに追従する。

ウェイトの対応付けは名前ではなく実測値に基づき、各面で `=` のバー厚を測って SCP / Monaspace のバリアブルフォントの wght を二分探索で一致させている。
基準は [Source Han Code JP](https://github.com/adobe-fonts/source-han-code-jp)（ペアリング参照、行間メトリクス、SCP 未収録の半角カナなどの補填元）としているため、従来の SHCJ の見た目や使用感を維持できる。

## 合字一覧

**Monaspace 由来の 50 種**を収録（[githubnext/monaspace](https://github.com/githubnext/monaspace) v1.400、OFL）。
代表例: `!=` `==` `===` `!==` `<=` `>=` `->` `<-` `=>` `~>` `:=` `::`
`<<=` `>>=` `=<<` `|>` `<|` `<>` `</>` `//` `#[` `...` `&=` `||` など（全 50 種）。
全リストは `data/mona_ligs.json` を参照。

移植対象は合字グリフと、単独の `=` `<` `>` `|` `~` のみ。英数字やその他の記号は
SHCJ（= Source Code Pro）のまま保持する。SHCJ に未収録の SCP の約 600 文字（`ł` `ğ` `ş` `ı` `ř`
`₽` などポーランド語・トルコ語・チェコ語等の文字）も SCP から半角で取り込み、
SHCJ に含まれず SHS にプロポーショナル幅で存在していた `ς` `⁴` などは SCP の半角版に置き換えている。
SHCJ が全角に割り当てている `→` `①` などはその方針を維持し、SHS 側のグリフが
プロポーショナル幅のもの（`−` `ˇ` `˙`）は SHCJ の全角グリフを流用してセルグリッドに収めている。
なお、単独グリフと合字でデザインの食い違い（`=` と `==` のバー間隔の違い、`<` と `<=` のサイズ・角度の違い、
`|` と `||` の高さの違い、`~` と `~>` の振幅の違い）が生じる 5 文字については、合字と同じインスタンスから抽出して統一感を保っている。
文字幅や縦方向の中心位置は SCP と数ユニット〜数十ユニットの精度で一致し、セル内に綺麗に収まる。
`-`（Monaspace は 132u 短く `=` と揃わない）、`!`（Monaspace の cap 高が SCP の大文字より高い）、
`:`（合字側は点を上げた `colon.case` なので置換しても揃わない）、`/`（`\` も必要なため）などは導入していない。

線の太さは**面ごとに** SHCJ の `=` のバー厚を実測し、Monaspace VF の wght を
二分探索で一致させたインスタンスから取り込む。Italic 面では slnt 軸で傾斜も
連動させ（SCP Italic の −12° に対し Monaspace の slnt 下限が −11° のため、
残り 1° はアウトラインのシアー処理で調整）、ベースラインは両フォントの
`=` の縦中心に揃えている。
GSUB テーブルには `calt` と `liga` の両方を登録しており（すべての合字が既定で有効）、加えて Monaspace 由来の
**グループ別 stylistic set** を備えているため、`calt` を無効化して必要なグループのみを個別で有効化できる:

| feature | 内容 | 例 |
|---------|------|----|
| ss01 | 比較・等価 | `!=` `===` `<=` `>=` |
| ss02 | 矢印 | `->` `<-` `=>` `>>=` |
| ss03 | マークアップ | `</` `/>` `</>` `<>` |
| ss04 | パイプ | `\|>` `<\|` |
| ss05 | コロン | `::` `:=` |
| ss06 | ドット | `..` `...` |
| ss07 | コメント | `//` `///` |
| ss08 | 反復・論理・その他 | `\|\|` `<<` `>>` `#[` `#(` `&=` |
| cv99 | 演算子の代替デザイン（Monaspace の .alt） | |

さらに **Source Code Pro 自身の字形バリアントもそのまま利用できる**:
`zero`（スラッシュゼロ切替）、`cv01`〜`cv17`（`a` の一階建て、`g` の形状など
SCP 純正の異体字）、`salt`、および SCP の stylistic set を 10 ずらして割当（ss11〜ss17。ss01〜ss08 は合字グループが使用）。
等幅メタデータ（`post.isFixedPitch` / PANOSE / xAvgCharWidth）と行間は SHCJ の宣言値をそのまま引き継いでいる。

```jsonc
// 例: !== の一体化が読みにくい場合、比較系だけ無効化して矢印は残す
"editor.fontLigatures": "'calt' off, 'ss02', 'ss03', 'ss05', 'ss06', 'ss07', 'ss08'"
```
ss01〜08 はグループごとに独立したルックアップのため、`calt` を無効化したまま複数の
グループを同時に有効化すると、短めのパターン（ss01 の `>=`）が長めのパターン（ss02 の `>>=`）の前半部に
干渉するケースがある。これは Monaspace 本家と同様の仕様である。複数のグループを組み合わせる際、
安全性を重視する場合は `calt` の使用を推奨する。

`:=` と `::` は Monaspace 内でも文脈依存の字形切替（`colon.case`）で実現されているため、
同様のグリフ合成処理を行っている（実レンダリング結果と誤差 1 ユニット未満で一致）。

## ファミリー構成

| ファミリー | 半角:全角 | `=`バー | 用途 |
|-----------|-----------|--------|------|
| Shoyu Code Pro JP | 667:1000 (2:3) | 69 | エディタ用（SHCJ の見た目を維持） |
| Shoyu Code Pro JP Term | 600:1200 (1:2) | 69 | ターミナル用 |
| Shoyu Code Pro JP 35 | 600:1000 (3:5) | 62 | SCP 原寸・原太（本家に忠実） |

`=`バーの値は現在ピン留めしている上流タグでの実測値（目安）。上流が
更新され再ビルドが行われると、太さマッチング処理の結果として多少変動する場合がある。

**Term** は欧文を縮小せず、**全角の送り幅を 1200（=600×2）に広げてグリフを中央配置**する 1:2 アプローチを採用している。
欧文は SCP 原寸（600）に太さ補正（SHCJ の CJK ペアリング 69/1000em に一致）を適用したもの。
ターミナルのセルグリッドに厳密に一致し、罫線も自然に繋がる。全角/半角の扱いが曖昧な文字（EAW=A）は
HackGen Console / PlemolJP Console / Moralerspace HW と同じ方針で分類している:
合字と対になる `←` `→` `↑` `↓` `⇐` `⇒` `⇔` `≠` `≤` `≥` `…` は **Monaspace の
半角グリフ**（`<-` `!=` `<=` `...` と同じ太さ・矢印形状）、SCP に含まれる `×` `÷` `■`
ギリシャ文字・アクセント付きラテン文字・キリル文字・罫線素片は **SCP 自身の
半角グリフ**（1 セル。罫線は上下に食み出る設計のため行間に関わらず繋がる）、
どちらにも存在しない `①` `※` などは**全角のまま**保持している。曖昧幅を
半角扱いするターミナルでは `①` が右隣のセルにはみ出るが、これは HackGen と同様の
挙動であり、Windows Terminal では `"compatibility.ambiguousWidth": "wide"`、
iTerm2 / WezTerm では相当の設定で 2 セル割り当てれば JP ファミリーと同じサイズで表示できる。

なお、35 の太さ補正版（35W、バー69）も試作したが、実用サイズ（14px）では
視認できる差がなかったため不採用とした。Term は全角文字と常時並ぶ前提であるため、
理論的に適切な補正済みの値を採用している。

以前試作した 1:2 の Console バリエーションは廃止した。SCP のゆったりとした骨格を
500 セルに収めるには、等方縮小（欧文が 25% 小さく細くなる）か約 17% のコンデンス化
（線のコントラストが歪む）のいずれかしかなく、両方を実際にビルドして目視評価した結果、
どちらも SCP の字形の特徴が大きく損なわれると判断したためである。1:2 の比率が必要な場合は、
Sarasa Gothic（Iosevka）など細身設計の欧文を採用したフォントの使用を推奨する（内部処理の
`rescale(ky=)` / `narrow_ambiguous()` 機構自体は保持している）。

各ファミリーは 6 ウェイト（Light / Normal / Regular / Medium / Bold / Heavy）× 2 スタイル
（Upright / Italic — Italic は SCP 本来のイタリック、和文は SHCJ と同様に直立のまま）で構成される。
Monaspace VF の wght 軸下限（200）は `=` バー厚 59u であり、SHCJ Light の 47u に届かないため、
Light では Monaspace 由来のアウトラインを片側 6u 内側に削って（pathops でストローク幅 2d を差し引く）
太さを合わせている。SHCJ の ExtraLight（31u）は片側 14u 削る必要があり、
`:=` や `...` の点が痩せすぎるため提供していない。

35 は半角グリフを 600/667 に等方縮小したもの（オリジナルの SCP の原寸復元）。
半角カナ（`ｱ` `｡` `｢` など）は SHCJ が 500 幅（1000 の半分）で持っており、667 にも
600 にも適合しないため、35 / Term では 600 セル内に中央配置してグリッドに揃えている
（2:3 の JP は SHCJ の見た目を優先してそのまま維持）。全バリエーションで Nerd Fonts
パッチ適用済みのフォントも生成する。NF ファミリー名は日本語プログラミングフォントの
慣習（HackGen / PlemolJP / UDEV Gothic 等と同様）に合わせ、**バリエーション名の末尾**に付加される:
`Shoyu Code Pro JP NF` / `Shoyu Code Pro JP Term NF` / `Shoyu Code Pro JP 35 NF`。CID-keyed CFF のままでは
font-patcher がグリフを Unicode で検索できないため、パッチ処理の前に FontForge の
`cidFlatten()` で平坦化を行っている（アウトラインは無変換）。

## インストール

[Releases](../../releases) から用途に応じてアセットを選択する。いずれの zip にも
OFL のライセンス全文（LICENSE）を同梱している。

- **`ShoyuCodeProJP.zip`**: 個別の OTF ファイル群。特定のウェイトやスタイルのみを
  選択してインストールしたい場合に適している。
- **`ShoyuCodeProJP.ttc` / `ShoyuCodeProJP35.ttc` / `ShoyuCodeProJPTerm.ttc`**:
  各ファミリー 12 面（6 ウェイト×2 スタイル）を 1 ファイルにまとめた TTC。
  1 ファイルですべてのウェイト・スタイルをインストールできる（ファイルサイズは OTF 合計と 3% しか
  違わないため、個別インストールと比べて手間を大幅に削減できる）。
- **`ShoyuCodeProJP-NerdFont.zip`**: Nerd Fonts のアイコングリフを追加した
  NF バリエーション（ファミリー名の末尾に `NF` が付加される。例: `Shoyu Code Pro JP NF`）。
  ターミナルのプロンプト装飾（アイコン表示）に使う場合はこちらを選択する。

ダウンロードしてインストールし、エディタ等で設定する:

```jsonc
{
  "editor.fontFamily": "Shoyu Code Pro JP",
  "editor.fontLigatures": true
}
```

フォントファミリー名が `Shoyu Code Pro JP` に変更されているため、
オリジナル版の Source Han Code JP と共存可能である。

- **macOS**: OTF をダブルクリックして「Font Book」でインストール、または
  `~/Library/Fonts/` にコピー。
- **Windows**: OTF を右クリックして「インストール」を選択（全ユーザー適用は
  「すべてのユーザー用にインストール」）。
- **Linux**: `~/.local/share/fonts/`（ユーザー単位）または
  `/usr/local/share/fonts/`（全ユーザー）にコピーし、`fc-cache -f` を実行。

ビルドやリガチャの追加・改造については [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ビルド

4 つの上流フォント（Source Han Sans JP / Source Code Pro VF / Monaspace VF /
Source Han Code JP）を取得し、環境変数でパスを指定する。具体的なビルド手順は
`.github/workflows/ci.yml` を参照。

```sh
pip install -r requirements.txt
SHS_DIR=... SCP_VF_U=... SCP_VF_I=... MONA_VF=... SHCJ_TTC=upstream/SourceHanCodeJP.ttc \
  python scripts/build.py            # 全ファミリー（2:3 / 35 / Term × 12面）
  python scripts/build.py "Regular"  # Regular系のみ（動作確認用）
python scripts/verify.py dist/ShoyuCodeProJP-Regular.otf   # 回帰テスト
python scripts/nerdpatch.py <FontPatcher dir>              # NF 変種
python scripts/makeotc.py                                  # .ttc 化
```

`SHCJ_TTC` は [Source Han Code JP の GitHub Releases](https://github.com/adobe-fonts/source-han-code-jp/releases)
から `SourceHanCodeJP.ttc` をダウンロードしたファイルのパスを指定する（`.github/workflows/ci.yml`
と同じ取得元・同じ手順）。他の 3 変数（`SHS_DIR` / `SCP_VF_U` / `SCP_VF_I` /
`MONA_VF`）も同様に、それぞれ Source Han Sans JP / Source Code Pro VF /
Monaspace VF の Releases から取得する。

## 仕組み

- Source Han Sans JP（CID-keyed CFF）をベースに、SHCJ が半角にしている
  477 コードポイントへ SCP VF 由来のグリフを移植・合成し cmap を差し替える
  （SCP に未収録の半角カナ等は SHCJ から流用）。追加 CID は空き領域へ
  昇順で割り当てている（サブセット OTF の CID が不連続なため）
- 各面の `=` バー厚を実測し、SCP / Monaspace VF の wght を二分探索して
  太さを一致させる。Italic は SCP Italic VF に合わせ slnt 軸を調整
- 合字は LigatureSubst。`calt`/`liga` は結合ルックアップ 1 つ（最長一致保証のため）、
  ss01〜08 はグループ別ルックアップ、cv99 は .alt 切替
- 行間・等幅メタデータは SHCJ の宣言値を引き継ぎ、レンダリング上の連続性を保持

## ライセンス

フォント本体は上流と同じ [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-code-jp/blob/master/LICENSE.txt)。
OFL の Reserved Font Name 規定に基づき、ファミリー名は変更済み（Source→Shoyu、nerd-fonts の SauceCodePro と同様の名称変更）。
