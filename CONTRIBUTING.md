# Contributing

Gengou Code JP は上流フォント（Source Han Sans JP / Source Code Pro /
Source Sans 3 / Monaspace）を CI 上で合成して作られています。ソース
グリフを直接同梱していないため、ビルドには毎回それらの上流ファイルが
必要です。

## ローカルビルド

```sh
pip install -r requirements.txt
```

ビルドは2段階です。まず `scripts/build_latin.py` が Source Code Pro VF・
Monaspace VF・Source Sans 3 VF Italic（斜体のギリシャ・キリル）から
欧文レイヤー Gengou Code を `dist/latin` に組み、
次に `scripts/build.py` がそれを Source Han Sans JP に接ぎ木します
（`build.py` は両段階の共通ヘルパーと JP の接ぎ木、`vfsource.py` は
VF のインスタンス化と Monaspace の合成、`anchors.py` は欧文レイヤーが
足す mark アンカー、`nerdpatch.py` は Nerd Fonts の接ぎ木、`verifylib.py`
は 3 本の verifier が共有する検査）。
それぞれが読む環境変数:

| 変数 | 読むスクリプト | 内容 | 入手元 |
|------|------|------|--------|
| `SCP_VF_U` | `build_latin.py` / `build_latin_vf.py` | `SourceCodeVF-Upright.otf` へのパス | [Source Code Pro Releases](https://github.com/adobe-fonts/source-code-pro/releases) |
| `SCP_VF_I` | 同上 | `SourceCodeVF-Italic.otf` へのパス | 同上 |
| `SS_VF_I` | 同上 | `SourceSans3VF-Italic.otf` へのパス（斜体のギリシャ・キリル） | [Source Sans Releases](https://github.com/adobe-fonts/source-sans/releases) |
| `MONA_VF` | 同上 | Monaspace の可変フォント（例: `Monaspace Neon Var.ttf`） | [Monaspace Releases](https://github.com/githubnext/monaspace/releases) |
| `SHS_DIR` | `build.py` | `SourceHanSansJP-<Weight>.otf` が入ったディレクトリ | [Source Han Sans Releases](https://github.com/adobe-fonts/source-han-sans/releases) |
| `NF_SYMBOLS` | `nerdpatch.py` | `SymbolsNerdFontMono-Regular.ttf` へのパス | [Nerd Fonts Releases](https://github.com/ryanoasis/nerd-fonts/releases) の `NerdFontsSymbolsOnly.zip` |
| `LATIN_DIR` | `build.py`（任意、既定 `dist/latin`） | `build_latin.py` の出力先 | — |
| `GENGOU_VERSION` | ビルド 3 本と verify 3 本（任意） | リリース版番号（例 `6.0.0`）。未設定なら上流のリビジョンを name に残す | — |
| `GENGOU_SKIP_AUTOHINT` | `build.py` / `build_latin.py`（任意） | `1` でヒント付けをスキップ（試しビルドの時短用） | — |

取得元の URL パターンや正確なタグは `.github/actions/setup-build/action.yml`
と `.github/workflows/ci.yml` を参照してください（そのまま実行可能な
リファレンスです）。

リリースのタグがバージョンです（バージョンファイルはありません）。上流を
取り込み直すだけのリリースはパッチ上げで、週次の `upstream-sync` が自分で
PR を出して自分でマージし、そのタグで `release.yml` を叩きます。**フォントの
中身そのものが変わるリリースは、先に人間がメジャータグを切る必要があります**
——`scripts/bump_pins.py` の `MIN_RELEASE` がその下限で、下回る自動リリースは
落ちます。改名したこのリリースの場合、次のタグは `v6.0.0` です。

```sh
# export しておく（`VAR=... \` の行継続は直後の 1 コマンドにしか効かない）
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=...
python scripts/build_latin.py           # dist/latin/GengouCode-*.otf（10 面）
python scripts/build_latin.py "Regular" # Regular 系のみ
python scripts/build.py                 # 両ファミリー
python scripts/build.py "Regular"       # Regular 系のみ（動作確認用、速い）
python scripts/build.py "Light Upright Term"   # 1 面だけ
```

フィルタは語の組み合わせで、面がすべての語に合うものを組みます:
ウェイト名（`Light` `Regular` `Medium` `SemiBold` `Bold`）、書体
（`Upright` / `Italic`）、変種（`Term` / 変種なしの基本ファミリーは
`base`。`build_latin.py` は 1 ファミリーなので `base` 以外の変種語には
何も合いません）。同じ種類の語を複数書けばそのいずれか
（`"Light Regular base"` は基本ファミリーの Light と Regular の 4 面）。
`"Regular"` は Regular と Regular Italic の全ファミリー、`"Light Italic"`
はファミリーごとに 1 面、`""`（空文字列）だけなら基本ファミリーです。

可変フォント版の Gengou Code は `python scripts/build_latin_vf.py`
（`build_latin.py` と同じ環境変数）で `dist/latin/GengouCode[wght].otf` /
`GengouCode-Italic[wght].otf` を作ります。

## テスト・検証

```sh
python -m pytest tests/ -q                                  # 単体テスト
python scripts/verify.py dist/GengouCodeJP-Regular.otf          # 面を名指し
python scripts/verify.py "dist/latin/GengouCode[wght].otf"      # 可変版も同じ入口
python scripts/verify.py 'dist/*.otf' 'dist/latin/*.otf' 'dist/nerd/*.otf'
```

グリフの合成漏れやメトリクスの崩れなど、シェイピングまわりの回帰を
チェックします。結合アクセントは `scripts/verifylib.py` の
`check_marks`（feature と GDEF、ルックアップ型で歩いた feature 到達性、
声調ルックアップに字が無いこと、言語システム、全アンカーの構造、マーク主導のカバレッジ、GPOS から読んだ
模型に対するシェーパーの等式、mkmk の等式、アンカーと独立にマークの墨が
字の墨に座っていること（同じ種類の字の中央値との差も）、アセンダー字の
貫通、大文字の後の持ち上げ形、i/j の点、ギリシャのアクセント、タイバー）と
`check_cells`（全文字の送りが East Asian Width どおりでシェイプしても
同じこと、字形が自分のセルの決まった場所にあること）、合字のセルと高さと
ガード、全文字を単独と 2 字の組でシェイプしての同一性、既定で効く置換が
文字を変えないこと、GPOS の型、GDEF の分類、FontMatrix・行メトリクス・
name・家族の cmap、JP の縦組みと VORG（ドナーと突き合わせ）で、サンプルではなく面全体を見ます（可変フォントは既定・両端・
名前付きインスタンス・マスターの各ロケーションに instantiate して
同じゲートを通します）。変更を提出する前に、少なくとも
`Regular` 面で通ることを確認してください。CI（`.github/workflows/ci.yml`）でも push / PR 時に
同じ検証が走ります。どのジョブが何を組むかは `ci.yml` と `release.yml` の
冒頭のコメントにあります（ここには重ねて書きません。書くとずれるので）。
リリースの所要時間を測るだけなら Run workflow の dry-run にチェックを入れるか、
コミットメッセージに `[release-dry]` と書いたコミットをブランチに push します。
どちらもビルドと梱包まで走って Release は作りません。複数の面をまとめて検証するときは
`python scripts/verify.py 'dist/*.otf' 'dist/latin/*.otf'` が面ごとに
プロセスを分けて走らせます（どの門番に掛けるかはフォント自身が決める）。

**フォントの出力が変わる変更では、`scripts/golden.py` で「変わってよい所だけが
変わった」ことを示してください。** 門番が答えるのは「壊れていないか」で、
「狙った所以外は何も動いていないか」には答えません。変更前のコミットで組んだ
`dist` を別の場所に取っておき、変更後に組んだものと突き合わせます:

```sh
python scripts/golden.py <前の dist> dist                 # JP 面
python scripts/golden.py <前の dist>/latin dist/latin     # 欧文の静的面
python scripts/golden.py <前の dist>/nerd dist/nerd       # Nerd Fonts 版
```

cmap・送り幅・GSUB/GPOS の feature tag・コーパスのシェーピング・
アウトライン・メタデータ・ヒントを面ごとに比べ、グリフの番号が振り直されて
いても同じものは同じと見ます（ディレクトリは下へ辿らないので、上のように
1 段ずつ渡す）。出た差分が全部、その変更で動くと分かっているものなら、
それを PR に書きます。ビルドが 2 回要るので CI には載っていません。

NF（Nerd Fonts）変種の生成を試す場合（`NF_SYMBOLS` に Symbols Nerd Font
Mono を渡す。fontTools で接ぎ木するので FontForge も font-patcher も要らず、
1 面 10 秒程度）:

```sh
NF_SYMBOLS=... python scripts/nerdpatch.py [面のパス | 名前の一部]
```

## 合字を追加・変更する（`data/mona_ligs.json`）

合字の定義は `data/mona_ligs.json` にあり、`scripts/build.py` の
`load_ligatures()` が読み込みます。グリフは `build_latin.py` が
`build.add_glyphs()` で Monaspace から Gengou Code に描き、`build.py` は
その完成グリフを `latin_ligatures()` で JP 側へ写し、両方が共通の
`add_gsub()` で calt/liga と stylistic set を組みます。1エントリの形式:

```jsonc
"!=": {
  "cells": 2,                       // 合字が占める半角セル数（送り幅 = CELL * cells）
  "glyphs": ["exclam_equal"],       // Monaspace VF 側のグリフ名（複数可、左から順に並べて描画）
  "group": "ss01"                   // 属する stylistic set（calt/liga には自動的に全グループが載る）
}
```

- **キー**: 合字として認識させたい文字列そのもの（例 `"!="`）。この文字列の
  各文字が出力フォントの cmap に存在しないとスキップされます。
- **`glyphs`**: Monaspace VF 側のグリフ名のリスト。単一グリフなら1要素、
  複数グリフを並べて1つの合字にする場合は複数要素（左詰めで並べて描画）。
  ここに書いたグリフ名が Monaspace 側に存在しないとスキップされます。
- **`cells`**: 合字の見た目上の幅（半角セル単位）。通常は文字列の文字数と
  一致させます。
- **`group`**: `ss01`〜`ss08` のいずれか。README の「合字一覧」表にある
  グループ分け（比較・矢印・マークアップ・パイプ・コロン・ドット・
  コメント・反復論理）に対応し、対応する stylistic set 機能として
  個別に有効化できるようになります。既存グループの内容は README を参照。

新しい合字を追加する手順:

1. 対象の記号列を Monaspace 側の GSUB/グリフ名で確認する（Monaspace の
   ソースまたはフォント自体をのぞいて `xxx_yyy` 形式のグリフ名を探す）。
2. `data/mona_ligs.json` に上記形式でエントリを追加する。
3. `python scripts/build.py "Regular"` でビルドし、`scripts/verify.py`
   で確認する。
4. README の合字一覧・該当する ss テーブル行も実態に合わせて更新する
   （存在しない合字を書かない・書き漏らさないこと）。

`.alt` サフィックス付きグリフ（例 `exclam_exclam.alt`）が Monaspace 側に
存在する場合、`cv99`（演算子の代替デザイン切り替え）として自動的に
取り込まれます。

## 上流のバージョンピンを更新する

上流の固定タグは `.github/actions/setup-build/action.yml` の
「Pin upstream releases」ステップ（`SHS_TAG` / `SCP_TAG` / `SCP_VF_ZIP` /
`SS_TAG` / `MONA_TAG` / `NF_TAG`）に一元化されており、`ci.yml` /
`release.yml` はこのアクションを共有しています。同じステップに各アセットの
SHA-256（`SHS_SHA` / `SCP_SHA` / `SS_SHA` / `MONA_SHA` / `NF_SHA`）も
置いてあり、取得した zip がこれと一致しなければ展開せずにその場で
落ちます。GitHub のリリース資産はタグを変えずに差し替えられるので、
**タグだけではどのバイト列でビルドしたかを言えない**ためです。
キャッシュキーは**タグとハッシュの両方**から作ります。ハッシュだけだと、
タグを手で上げてハッシュを直し忘れたときにキーが変わらず、検証が入って
いる取得ステップごとキャッシュヒットで飛ばされてしまうためです。

通常は手で更新する必要はありません。`upstream-sync.yml`（毎週月曜 実行、
`workflow_dispatch` でも起動可）が検知から出荷までを通しで回します:

1. `scripts/bump_pins.py` が各上流の `releases/latest` を引き、ピンを書き
   換える。書き換える前に 5 つのアセットを実際に取得してハッシュを取るので、
   上流がアセット名を変えた場合はここで落ちる。**タグが動いていないのに
   ハッシュが変わっていた場合も落ちる** —— それは資産が差し替えられたと
   いうことで、ピンを黙って書き換えるとハッシュを置いている意味がなくなる
   ため、人間の判断に委ねる。
2. `chore/upstream-sync` ブランチに PR を作成する。
3. CI の各ジョブ（`upstream-sync.yml` の `REQUIRED_CHECKS`）が緑になるのを待って squash マージする。
4. パッチを 1 つ上げたタグで `release.yml` を dispatch する。

Issue は起票しません。PR 自体が同じ情報に加えて「そのピンでビルドが通る」
証拠を持っているためです。

新しい上流が字形を劣化させている場合は **PR を閉じてください**。ピンは
据え置かれ、翌週の実行で PR が開き直ります。恒久的に追従したくない場合は
`scripts/bump_pins.py` の対象から外します。

見た目に影響しうる変更（合字・ウェイトマッチング・グリフ形状など）が
あった場合は、README の該当箇所（`=`バーの実測値など）も見直してください。
これは自動化の対象外です。

手で追従する場合は `.github/actions/setup-build/action.yml` のピンを
書き換えます（キャッシュキーはピンから自動導出される）。**タグと
SHA-256 は必ず対で書き換えてください**——片方だけ動かすと、ピンの中身と
ビルドに使われるバイト列が食い違ったまま通ってしまいます。

## Issue / Pull Request

バグ報告には `.github/ISSUE_TEMPLATE/` のテンプレートを利用して
ください（上流更新は `upstream-sync.yml` が PR で扱うため、Issue の
テンプレートはありません）。Pull Request は変更内容と動作確認方法（実行した
`verify.py` の対象面など）を簡潔に記載してください。

リリースノートは GitHub がマージ済み PR から生成するので、変更履歴
ファイルはありません（v5.0.0 までの手書きの履歴は各リリースのページと、
`git show v5.0.0:CHANGELOG.md` に残っています）。**PR のタイトルがその
まま公開されるノートの 1 行**になるので、何が変わるのかが分かる題を
付けてください。
