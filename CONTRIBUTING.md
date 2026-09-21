# Contributing

Gengou JP は上流フォント（Source Han Sans JP / Source Code Pro / Source Sans 3 / Monaspace）を CI 上で合成して構築されています。ソースグリフを直接同梱していないため、ローカルビルドの際には各上流ファイルが必要となります。

## ローカルビルド

```sh
pip install -r requirements.txt
```

ビルドは 2 段階で進行します。まず `scripts/build_latin.py` が Source Code Pro VF・Monaspace VF・Source Sans 3 VF Italic（斜体のギリシャ・キリル文字）から欧文レイヤー Gengou を `dist/latin` に生成し、次に `scripts/build.py` がそれを Source Han Sans JP に合成します。
それぞれのスクリプトが参照する環境変数:

| 変数 | 参照スクリプト | 内容 | 入手元 |
|------|------|------|--------|
| `SCP_VF_U` | `build_latin.py` / `build_latin_vf.py` | `SourceCodeVF-Upright.otf` へのパス | [Source Code Pro Releases](https://github.com/adobe-fonts/source-code-pro/releases) |
| `SCP_VF_I` | 同上 | `SourceCodeVF-Italic.otf` へのパス | 同上 |
| `SS_VF_I` | 同上 | `SourceSans3VF-Italic.otf` へのパス（斜体のギリシャ・キリル文字用） | [Source Sans Releases](https://github.com/adobe-fonts/source-sans/releases) |
| `MONA_VF` | 同上 | Monaspace の可変フォント（例: `Monaspace Neon Var.ttf`） | [Monaspace Releases](https://github.com/githubnext/monaspace/releases) |
| `SHS_DIR` | `build.py` | `SourceHanSansJP-<Weight>.otf` が入ったディレクトリ | [Source Han Sans Releases](https://github.com/adobe-fonts/source-han-sans/releases) |
| `NF_SYMBOLS` | `nerdpatch.py` | `SymbolsNerdFontMono-Regular.ttf` へのパス | [Nerd Fonts Releases](https://github.com/ryanoasis/nerd-fonts/releases) の `NerdFontsSymbolsOnly.zip` |
| `LATIN_DIR` | `build.py`（任意、既定 `dist/latin`） | `build_latin.py` の出力先 | — |
| `GENGOU_VERSION` | 3 つとも（任意） | リリース版番号（例 `6.0.0`）。未設定時は上流のリビジョン情報を name テーブルに維持 | — |
| `GENGOU_SKIP_AUTOHINT` | `build.py` / `build_latin.py`（任意） | `1` 指定でヒント付けをスキップ（テストビルドの時短用） | — |

取得元の URL パターンや正確なタグについては、`.github/actions/fetch-upstreams/action.yml` および `.github/workflows/ci.yml` を参照してください。

リリースタグがバージョン番号となります（バージョン管理ファイルは存在しません）。上流フォントの更新のみを反映するリリースはパッチバージョンの更新となり、週次の `upstream-sync` ワークフローが自動で PR を作成・マージし、該当タグで `release.yml` を実行します。**フォント自体の仕様が変更されるリリースについては、手動でメジャータグを作成する必要があります**（`scripts/bump_pins.py` の `MIN_RELEASE` がその下限値となっており、下回る自動リリースはエラーとなります）。本リブランディングリリースの次のタグは `v6.0.0` となります。

```sh
# 環境変数を export して実行
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=...
python scripts/build_latin.py           # dist/latin/Gengou-*.otf（10 面）
python scripts/build_latin.py "Regular" # Regular 系のみ
python scripts/build.py                 # 両ファミリー
python scripts/build.py "Regular"       # Regular 系のみ（動作確認用・高速）
python scripts/build.py "Light Upright Term"   # 1 面のみ指定
```

フィルタキーワードを指定することで、条件に一致する面のみをビルドできます:
ウェイト名（`Light` `Regular` `Medium` `SemiBold` `Bold`）、スタイル（`Upright` / `Italic`）、バリエーション（`Term` / 基本ファミリーは `base`）。同一指定内で複数キーワードを渡すことも可能です（例: `"Light Regular base"` で基本ファミリーの Light と Regular の 4 面）。
`"Regular"` は Regular および Regular Italic の全ファミリー、`"Light Italic"` はファミリーごとに 1 面、`""`（空文字列）の場合は基本ファミリー全体が対象となります。

可変フォント版の Gengou は `python scripts/build_latin_vf.py`（`build_latin.py` と共通の環境変数）を実行することで `dist/latin/Gengou[wght].otf` および `Gengou-Italic[wght].otf` を生成します。

## テスト・検証

```sh
python -m pytest tests/ -q                                  # 単体テスト
python scripts/lint_workflows.py                            # .github/ の YAML 検証
python scripts/verify_latin.py dist/latin/Gengou-Regular.otf
python scripts/verify_latin_vf.py "dist/latin/Gengou[wght].otf"
python scripts/verify.py dist/GengouJP-Regular.otf
```

グリフの合成漏れやメトリクスの崩れなど、シェイピング処理の回帰テストを行います。結合アクセントについては `scripts/verifylib.py` の 3 つの検証ゲート（全アンカーが自グリフ領域内に存在すること、全文字がベースに含まれること、シェーパーが全ベースおよび全マークをアンカー通りに配置すること）によって、サンプル抽出ではなく面全体を検証します（可変フォントは各ロケーションにインスタンス化して同様のゲートを実行します）。
変更を提出する前に、少なくとも `Regular` スタイルで検証が通過することを確認してください。CI（`.github/workflows/ci.yml`）でも push / PR 時に同様の検証が実行されます。
複数の面をまとめて検証する場合は `python scripts/verify_many.py dist/*.otf dist/latin/*.otf` を使用することで面ごとにプロセスを分離して検証できます。ビルド前後の出力を比較したい場合は `python scripts/golden.py <前の dist> <今の dist>` により cmap・送り幅・シェーピング・アウトライン・メタデータ・ヒント差分を照合可能です。

Nerd Fonts（NF）対応版の生成をテストする場合（`NF_SYMBOLS` に Symbols Nerd Font Mono のパスを指定。fontTools による直接移植のため FontForge や font-patcher は不要で 1 面 10 秒程度で完了します）:

```sh
NF_SYMBOLS=... python scripts/nerdpatch.py [面のパス | 名前の一部]
```

## 合字を追加・変更する（`data/mona_ligs.json`）

合字の定義は `data/mona_ligs.json` に格納されており、`scripts/build.py` の `load_ligatures()` が読み込みます。グリフは `build_latin.py` が `build.add_glyphs()` を通じて Monaspace から Gengou へ描画し、`build.py` はその完成グリフを `latin_ligatures()` で JP 側へ適用し、両スクリプト共通の `add_gsub()` により calt/liga および stylistic set を構築します。1 エントリの形式:

```jsonc
"!=": {
  "cells": 2,                       // 合字が占める半角セル数（送り幅 = CELL * cells）
  "glyphs": ["exclam_equal"],       // Monaspace VF 側のグリフ名（複数可、左から順に並べて描画）
  "group": "ss01"                   // 属する stylistic set（calt/liga にはすべてのグループが自動的に含まれる）
}
```

- **キー**: 合字として認識させたい文字列そのもの（例 `"!="`）。この文字列の各文字が出力フォントの cmap に存在しない場合はスキップされます。
- **`glyphs`**: Monaspace VF 側のグリフ名リスト。単一グリフなら 1 要素、複数グリフを並べて 1 つの合字にする場合は複数要素（左詰めで並べて描画）。指定したグリフ名が Monaspace 側に存在しない場合はスキップされます。
- **`cells`**: 合字の見た目上の幅（半角セル単位）。通常は文字列の文字数と一致させます。
- **`group`**: `ss01`〜`ss08` のいずれか。README の「合字一覧」表にあるグループ分けに対応し、対応する stylistic set 機能として個別に有効化できるようになります。既存グループの詳細は README を参照してください。

新しい合字を追加する手順:

1. 対象の記号列を Monaspace 側の GSUB/グリフ名で確認する（Monaspace のソースまたはフォント自体を参照して `xxx_yyy` 形式のグリフ名を探す）。
2. `data/mona_ligs.json` に上記形式でエントリを追加する。
3. `python scripts/build.py "Regular"` でビルドし、`scripts/verify.py` で確認する。
4. README の合字一覧・該当する ss テーブル行も実態に合わせて更新する（存在しない合字の記載や記載漏れがないようにすること）。

`.alt` サフィックス付きグリフ（例 `exclam_exclam.alt`）が Monaspace 側に存在する場合、`cv99`（演算子の代替デザイン切り替え）として自動的に取り込まれます。

## 上流のバージョンピンを更新する

上流の固定タグは `.github/actions/fetch-upstreams/action.yml` の「Pin upstream releases」ステップ（`SHS_TAG` / `SCP_TAG` / `SCP_VF_ZIP` / `SS_TAG` / `MONA_TAG` / `NF_TAG`）に一元化されており、`ci.yml` / `release.yml` はこのアクションを共有しています。同ステップには各アセットの SHA-256（`SHS_SHA` / `SCP_SHA` / `SS_SHA` / `MONA_SHA` / `NF_SHA`）も定義されており、取得した zip ファイルが一致しない場合は展開せずにその場でエラー停止します。GitHub のリリースアセットは同一タグのままファイルを差し替えることが可能であるため、タグ情報のみではビルドに使用されたバイト列の同一性を保証できないためです。キャッシュキーは**タグとハッシュの両方**から生成されます。

通常は手動で更新する必要はありません。`upstream-sync.yml`（毎週月曜実行、`workflow_dispatch` での手動起動も可能）が更新検知からリリース準備までを自動で実行します:

1. `scripts/bump_pins.py` が各上流の `releases/latest` を取得し、ピンを書き換える。書き換え前に 5 つのアセットを実際に取得してハッシュを検証するため、上流がアセット名を変更した場合はこの段階でエラーとなる。**タグが更新されていない状態でハッシュのみが変更された場合もエラー停止する**（アセットが差し替えられたことを意味し、自動書き換えを行わず人間の判断に委ねるため）。
2. `chore/upstream-sync` ブランチに PR を作成する。
3. CI の各ジョブ（`upstream-sync.yml` の `REQUIRED_CHECKS`）の成功を確認して squash マージする。
4. パッチバージョンを 1 つ上げたタグで `release.yml` を実行する。

Issue は起票しません。PR 自体が更新情報とビルド検証結果を兼ね備えているためです。

新しい上流フォントで字形に問題が生じている場合は **PR を閉じてください**。ピンは維持され、翌週の定期実行時に PR が再作成されます。恒久的に追従対象から外したい場合は `scripts/bump_pins.py` の更新対象から除外します。

見た目に影響しうる変更（合字・ウェイトマッチング・グリフ形状など）があった場合は、README の該当箇所（`=`バーの実測値など）も合わせて見直してください。この作業は自動化の対象外です。

手動で追従する場合は `.github/actions/fetch-upstreams/action.yml` のピンを書き換えます（キャッシュキーはピン情報から自動算出されます）。**タグと SHA-256 は必ずペアで更新してください**。

## Issue / Pull Request

バグ報告には `.github/ISSUE_TEMPLATE/` のテンプレートを利用してください（上流更新は `upstream-sync.yml` が PR として処理するため、Issue 用のテンプレートはありません）。Pull Request を作成する際は、変更内容と動作確認方法（実行した `verify.py` の検証対象スタイルなど）を簡潔に記載してください。

リリースノートは GitHub がマージ済み PR から自動生成するため、変更履歴ファイルはありません（v5.0.0 までの手書き履歴は各リリースチャネルおよび `git show v5.0.0:CHANGELOG.md` に保持されています）。**PR のタイトルがそのまま公開用リリースノートの 1 行**となるため、変更内容が正確に把握できるタイトルを設定してください。
