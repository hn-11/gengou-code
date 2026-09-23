# Contributing

[English](CONTRIBUTING.md)

フォントは上流のリリース（Source Code Pro、Source Sans 3、Monaspace、
Source Han Sans JP、Symbols Nerd Font Mono）から組みます。元のグリフは
このリポジトリに入っていないので、ビルドには毎回それらのファイルが
必要です。

## 構成

| パス | 役割 |
|------|------|
| `scripts/build_latin.py` | 欧文レイヤーの作り方。材料のフォント、Monaspace の記号と合字の接ぎ木、ウェイト・スタイルごとの静的な材料面（メモリ上） |
| `scripts/build_latin_vf.py` | Gengou Code 本体（可変フォント）。同じ作り方で組む |
| `scripts/build.py` | Gengou Code JP と JP Term。欧文の材料面を組んでから Source Han Sans に接ぎ木する。共通の関数もここ |
| `scripts/vfsource.py` | 可変フォントのインスタンス化と、Monaspace のウェイト合わせ |
| `scripts/anchors.py` | 欧文レイヤーが足す結合記号のアンカー |
| `scripts/nerdpatch.py` | Nerd Fonts 版 |
| `scripts/verify.py` | 組んだフォントの検査の入口。中身は `verify_jp.py`、`verify_latin_vf.py` と共通の `verifylib.py` |
| `scripts/golden.py` | 2 つのビルドを面ごとに比べる |
| `scripts/bump_pins.py` | 上流のピンを進める（`upstream-sync.yml` が使う） |
| `data/mona_ligs.json` | 合字の一覧 |

## ローカルでのビルド

```sh
pip install -r requirements.txt
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=... NF_SYMBOLS=...
python scripts/build_latin_vf.py              # dist/latin/GengouCode[wght].otf, GengouCode-Italic[wght].otf
python scripts/build.py                       # dist/GengouCodeJP*.otf（JP 2 ファミリー）
python scripts/build.py "Regular"             # Regular と Regular Italic だけ（速い）
python scripts/build.py "Light Upright Term"  # 1 面だけ
python scripts/nerdpatch.py                   # dist/nerd/ に上の全部の NF 版
```

| 変数 | 読むスクリプト | 値 |
|------|----------------|----|
| `SCP_VF_U` | `build.py`、`build_latin_vf.py` | `SourceCodeVF-Upright.otf` のパス（[Source Code Pro のリリース](https://github.com/adobe-fonts/source-code-pro/releases)） |
| `SCP_VF_I` | 同上 | `SourceCodeVF-Italic.otf` のパス |
| `SS_VF_I` | 同上 | `SourceSans3VF-Italic.otf` のパス（[Source Sans のリリース](https://github.com/adobe-fonts/source-sans/releases)）。直立だけ組むときも必須。斜体のギリシャ・キリルが黙って抜けるのを防ぐため |
| `MONA_VF` | 同上 | `Monaspace Neon Var.ttf` のパス（[Monaspace のリリース](https://github.com/githubnext/monaspace/releases)） |
| `SHS_DIR` | `build.py` | `SourceHanSansJP-<Weight>.otf` があるディレクトリ（[Source Han Sans のリリース](https://github.com/adobe-fonts/source-han-sans/releases)） |
| `NF_SYMBOLS` | `nerdpatch.py` | `SymbolsNerdFontMono-Regular.ttf` のパス（[Nerd Fonts のリリース](https://github.com/ryanoasis/nerd-fonts/releases)の `NerdFontsSymbolsOnly.zip`） |
| `GENGOU_VERSION` | ビルドと検査（任意） | リリースの版番号（例 `6.0.0`）。未設定なら name テーブルに上流のリビジョンが残る |
| `GENGOU_SKIP_AUTOHINT` | `build.py`、`nerdpatch.py`（任意） | `1` でヒント付けを飛ばす（手元で速く組みたいとき）。その場合ヒントの検査は落ちるが、それで正常 |

上流の正確なタグと取得元の URL は `.github/actions/setup-build/action.yml`
にあります。`.github/workflows/ci.yml` も上と同じコマンドを実行しています。

ビルドのフィルタは語の並びで、書いた種類の語すべてに合う面を組みます。
種類はウェイト（`Light` `Regular` `Medium` `SemiBold` `Bold`）、
スタイル（`Upright` `Italic`）、ファミリー（`Term`、Gengou Code JP は
`base`）の 3 つです。同じ種類の語を複数書くとそのどれか、という意味に
なるので、`"Light Regular base"` は 4 面です。

## 変更の確認

```sh
python -m pytest tests/ -q
python scripts/verify.py dist/GengouCodeJP-Regular.otf
python scripts/verify.py 'dist/*.otf' 'dist/nerd/*.otf' 'dist/latin/*.otf' 'dist/nerd/latin/*.otf'
```

`verify.py` はフォントを見てどの検査に掛けるかを決めます。可変フォントは
`verify_latin_vf.py`、和文を持つ面は `verify_jp.py` です。検査は見本では
なくフォント全体を対象にします。全文字の送り幅と東アジアの文字幅、
グリフがセルのどこにあるか、合字のセルと誤爆防止、結合記号、
GSUB/GPOS/GDEF、メトリクス、名前などです。可変フォントは既定値、軸の
両端、名前付きインスタンス、マスターの各位置で調べます。プルリクエストを
出す前に、少なくとも Regular の面で通してください。CI でも同じ検査が
走ります。どのジョブが何を組むかは `ci.yml` と `release.yml` の冒頭の
コメントにあります。

出力が変わる変更では、狙ったところだけが変わったことを示してください。
変更前のコミットで組んだものを別のディレクトリに置いて比べます。

```sh
python scripts/golden.py <前の dist> dist
python scripts/golden.py <前の dist>/latin dist/latin --only '*wght*'
python scripts/golden.py <前の dist>/nerd dist/nerd
```

`golden.py` は cmap、送り幅、feature のタグ、コーパスのシェーピング、
アウトライン、メタデータ、ヒントを比べます。グリフの番号が振り直されて
いても構いません。サブディレクトリには降りないので、ディレクトリごとに
実行します。出た差分とその理由をプルリクエストに書いてください。ビルドが
2 回要るので、CI では走らせていません。

## 合字の追加・変更

合字は `data/mona_ligs.json` で定義します。`build_latin.py` が Monaspace
から欧文レイヤーに描き、`build.py` がその完成したグリフを JP の面に
写します。1 項目の形:

```jsonc
"!=": {
  "cells": 2,                  // 幅（セル数。送り幅 = 600 × cells）
  "glyphs": ["exclam_equal"],  // Monaspace 側のグリフ名。左から順に並べる
  "group": "ss01"              // stylistic set。calt と liga には全グループが入る
}
```

キーは文字の並びそのものです。文字のどれかがフォントに無いか、グリフ名が
Monaspace に無ければ、その項目は飛ばされます。Monaspace にそのグリフの
`.alt` 版があれば、自動で `cv99` の別形になります。

追加の手順: Monaspace でグリフ名を調べ、項目を足し、Regular を組んで
`verify.py` を通し、両方の README の stylistic set の表を直します。

## 上流のバージョン

上流のリリースは `.github/actions/setup-build/action.yml` の
「Pin upstream releases」ステップで固定しています。タグと一緒に、取得する
ファイルの SHA-256 も置いてあり、一致しなければビルドはそこで止まります。
GitHub のリリースのファイルは、タグを変えずに差し替えられるからです。

`upstream-sync.yml` が毎週月曜に次のことをします。

1. `scripts/bump_pins.py` が各上流の最新リリースを調べ、ファイルを取得して
   ハッシュを取る。ファイル名が変わっていたり、タグが同じなのにハッシュが
   変わっていたりしたら止まる。
2. `chore/upstream-sync` ブランチでプルリクエストを出す。
3. `REQUIRED_CHECKS` の CI が通ったら squash マージする。
4. パッチ番号を 1 つ上げて `release.yml` を実行する。

新しい上流で見た目が悪くなったら、そのプルリクエストを閉じてください。
ピンは据え置かれ、翌週また開きます。手でピンを上げるときは、タグと
ハッシュを必ず一緒に書き換えます。

## リリース

git のタグがバージョンです。バージョンを書いたファイルはありません。
上流の更新だけのリリースはパッチ版で、自動で出ます。フォントの中身が
変わるリリースは、先に手でタグを切る必要があります。
`scripts/bump_pins.py` の `MIN_RELEASE` より下の自動リリースは止まります。
次は `v6.0.0` です。

公開せずにリリースのワークフローを試すときは、Run workflow で dry-run に
チェックを入れるか、コミットメッセージに `[release-dry]` を含めて push
します。

リリースノートはマージしたプルリクエストから作られるので、プルリク
エストのタイトルがそのままノートの 1 行になります。フォントを使う人から
見て何が変わるかをタイトルにしてください。v5.0.0 までのノートは各
リリースのページと `git show v5.0.0:CHANGELOG.md` にあります。

## Issue とプルリクエスト

不具合は `.github/ISSUE_TEMPLATE/` のテンプレートで報告してください。
プルリクエストには、何を変えたかと、どう確かめたか（`verify.py` を
掛けた面、出力が変わるなら `golden.py` の差分）を書いてください。

これまでの設計メモと測定値は履歴に残っています:
`git show a7c86ec:docs/gengou-plan.md`。その中の「据え置き」の一覧は、
検討したうえで意図的に手を付けなかったものの記録です。
