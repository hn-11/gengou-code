# Contributing

[English](CONTRIBUTING.md)

フォントは、元フォント（Source Code Pro、Source Sans 3、Monaspace、Source Han Sans JP、Symbols Nerd Font Mono）のリリースからビルドします。元のグリフはこのリポジトリに含まれていないため、ビルドのたびにこれらのファイルが必要です。

## 構成

| パス | 役割 |
|------|------|
| `scripts/build_latin.py` | 欧文レイヤーの生成手順。元フォントの読み込み、Monaspaceの記号と合字の移植、ウェイト・スタイルごとの静的な欧文書体の生成（メモリ上） |
| `scripts/build_latin_vf.py` | Gengou Code本体（可変フォント）を同じ手順で生成 |
| `scripts/build.py` | Gengou Code JPとJP Termを生成。欧文書体を作ってからSource Han Sansに組み込む。共通の関数もここにある |
| `scripts/vfsource.py` | 可変フォントのインスタンス化と、Monaspaceのウェイト合わせ |
| `scripts/anchors.py` | 欧文レイヤーが追加する結合記号のアンカー |
| `scripts/nerdpatch.py` | Nerd Fonts版の生成 |
| `scripts/verify.py` | 生成したフォントの検査の入口。検査本体は`verify_jp.py`、`verify_latin_vf.py`と共通の`verifylib.py` |
| `scripts/golden.py` | 2つのビルド結果を書体ごとに比較 |
| `scripts/bump_pins.py` | 元フォントの固定バージョンを更新（`upstream-sync.yml`が使用） |
| `data/mona_ligs.json` | 合字の定義 |

## ローカルでのビルド

```sh
pip install -r requirements.txt
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=... NF_SYMBOLS=...
python scripts/build_latin_vf.py              # dist/latin/GengouCode[wght].otf, GengouCode-Italic[wght].otf
python scripts/build.py                       # dist/GengouCodeJP*.otf（JPの2ファミリー）
python scripts/build.py "Regular"             # RegularとRegular Italicのみ（短時間で済む）
python scripts/build.py "Light Upright Term"  # 1書体のみ
python scripts/nerdpatch.py                   # 上記すべてのNF版をdist/nerd/に生成
```

| 環境変数 | 使用するスクリプト | 値 |
|----------|--------------------|----|
| `SCP_VF_U` | `build.py`、`build_latin_vf.py` | `SourceCodeVF-Upright.otf`のパス（[Source Code Proのリリース](https://github.com/adobe-fonts/source-code-pro/releases)） |
| `SCP_VF_I` | 同上 | `SourceCodeVF-Italic.otf`のパス |
| `SS_VF_I` | 同上 | `SourceSans3VF-Italic.otf`のパス（[Source Sansのリリース](https://github.com/adobe-fonts/source-sans/releases)）。正体だけをビルドする場合も必須です。斜体のギリシャ文字・キリル文字が気付かないうちに欠けるのを防ぐためです |
| `MONA_VF` | 同上 | `Monaspace Neon Var.ttf`のパス（[Monaspaceのリリース](https://github.com/githubnext/monaspace/releases)） |
| `SHS_DIR` | `build.py` | `SourceHanSansJP-<Weight>.otf`を置いたディレクトリ（[Source Han Sansのリリース](https://github.com/adobe-fonts/source-han-sans/releases)） |
| `NF_SYMBOLS` | `nerdpatch.py` | `SymbolsNerdFontMono-Regular.ttf`のパス（[Nerd Fontsのリリース](https://github.com/ryanoasis/nerd-fonts/releases)の`NerdFontsSymbolsOnly.zip`） |
| `GENGOU_VERSION` | ビルドと検査（任意） | リリースのバージョン番号（例: `6.0.0`）。未設定の場合、nameテーブルには元フォントのリビジョンが残ります |
| `GENGOU_SKIP_AUTOHINT` | `build.py`、`nerdpatch.py`（任意） | `1`を設定するとヒンティングを省略します（手元で短時間にビルドしたい場合）。このときヒントの検査は失敗しますが、想定どおりの動作です |

元フォントの正確なタグと取得元のURLは、`.github/actions/setup-build/action.yml`に記載しています。`.github/workflows/ci.yml`も上記と同じコマンドを実行しています。

ビルド対象の絞り込みは単語の組み合わせで指定し、指定したすべての種類の単語に一致する書体をビルドします。単語の種類は、ウェイト（`Light` `Regular` `Medium` `SemiBold` `Bold`）、スタイル（`Upright` `Italic`）、ファミリー（`Term`、Gengou Code JPは`base`）の3つです。同じ種類の単語を複数指定すると、そのいずれかに一致するものが対象になります。たとえば`"Light Regular base"`は4書体です。

## 変更の確認

```sh
python -m pytest tests/ -q
python scripts/verify.py dist/GengouCodeJP-Regular.otf
python scripts/verify.py 'dist/*.otf' 'dist/nerd/*.otf' 'dist/latin/*.otf' 'dist/nerd/latin/*.otf'
```

`verify.py`は、フォントの内容を見て適用する検査を決めます。可変フォントには`verify_latin_vf.py`、和文を含む書体には`verify_jp.py`を適用します。検査は一部の文字の抜き取りではなく、フォント全体を対象にします。全文字の送り幅と東アジアの文字幅の対応、各グリフのセル内での位置、合字のセル幅と誤適用の防止、結合記号、GSUB/GPOS/GDEF、メトリクス、名前などを確認します。可変フォントは、既定値、軸の両端、名前付きインスタンス、各マスターの位置で検査します。プルリクエストを出す前に、少なくともRegularの書体で検査を通してください。CIでも同じ検査を実行します。どのジョブで何をビルドするかは、`ci.yml`と`release.yml`の冒頭のコメントに記載しています。

出力が変わる変更では、意図した箇所だけが変わったことを示してください。変更前のコミットでビルドした結果を別のディレクトリに置き、次のように比較します。

```sh
python scripts/golden.py <変更前のdist> dist
python scripts/golden.py <変更前のdist>/latin dist/latin --only '*wght*'
python scripts/golden.py <変更前のdist>/nerd dist/nerd
```

`golden.py`は、cmap、送り幅、featureのタグ、テキストコーパスのシェーピング結果、アウトライン、メタデータ、ヒントを比較します。グリフの番号が振り直されていても問題ありません。サブディレクトリは対象にしないため、ディレクトリごとに実行してください。検出された差分とその理由をプルリクエストに記載してください。ビルドが2回必要なため、CIでは実行していません。

## 合字の追加・変更

合字は`data/mona_ligs.json`で定義します。`build_latin.py`がMonaspaceから欧文レイヤーに合字を描き、`build.py`がその完成したグリフをJPの書体に移します。各項目の形式は次のとおりです。

```jsonc
"!=": {
  "cells": 2,                  // 幅（セル数）。送り幅は600×cells
  "glyphs": ["exclam_equal"],  // Monaspace側のグリフ名。左から順に並べる
  "group": "ss01"              // stylistic set。calt/ligaにはすべてのグループが入る
}
```

キーは合字にする文字列そのものです。いずれかの文字がフォントにない場合や、グリフ名がMonaspaceにない場合、その項目はスキップされます。Monaspaceにそのグリフの`.alt`版がある場合は、自動的に`cv99`の代替字形になります。

合字を追加する手順は次のとおりです。

1. Monaspaceでグリフ名を調べる。
2. `data/mona_ligs.json`に項目を追加する。
3. Regularをビルドし、`verify.py`で検査する。
4. 英語版・日本語版の両方のREADMEで、stylistic setの表を更新する。

## 元フォントのバージョン

元フォントのリリースは、`.github/actions/setup-build/action.yml`の「Pin upstream releases」ステップで固定しています。タグと合わせて、取得するファイルのSHA-256も記載しており、一致しない場合はビルドがその時点で停止します。GitHubのリリースファイルは、タグを変えずに差し替えられるためです。

`upstream-sync.yml`は毎週月曜日に次の処理を行います。

1. `scripts/bump_pins.py`が各元フォントの最新リリースを調べ、ファイルを取得してハッシュを計算する。ファイル名が変わっていた場合や、タグが同じなのにハッシュが変わっていた場合は停止する。
2. `chore/upstream-sync`ブランチでプルリクエストを作成する。
3. `REQUIRED_CHECKS`に挙げたCIのジョブが成功したら、squashマージする。
4. パッチバージョンを1つ上げて`release.yml`を実行する。

新しいリリースで表示が悪くなった場合は、そのプルリクエストを閉じてください。固定バージョンはそのまま据え置かれ、翌週に再びプルリクエストが作成されます。手動で固定バージョンを更新する場合は、タグとハッシュを必ず一緒に書き換えてください。

## リリース

gitのタグがバージョンです。バージョンを記載したファイルはありません。元フォントの更新だけのリリースはパッチバージョンとして自動で公開されます。フォントの内容が変わるリリースは、先に手動でタグを作成する必要があります。`scripts/bump_pins.py`の`MIN_RELEASE`より低いバージョンの自動リリースは停止します。次のリリースは`v6.0.0`です。

公開せずにリリースのワークフローを試す場合は、Run workflowでdry-runにチェックを入れるか、コミットメッセージに`[release-dry]`を含めてpushします。

リリースノートはマージ済みのプルリクエストから生成するため、プルリクエストのタイトルがそのままリリースノートの1行になります。フォントの利用者から見て何が変わるのかが分かるタイトルを付けてください。v5.0.0までのリリースノートは、各リリースのページと`git show v5.0.0:CHANGELOG.md`で確認できます。

## Issueとプルリクエスト

不具合は`.github/ISSUE_TEMPLATE/`のテンプレートを使って報告してください。プルリクエストには、変更内容と確認方法（`verify.py`を実行した書体、出力が変わる場合は`golden.py`の差分）を記載してください。

これまでの設計メモと測定値は履歴に残っており、`git show a7c86ec:docs/gengou-plan.md`で参照できます。その中の「据え置き」の一覧は、検討したうえで意図的に対応しなかった項目の記録です。
