# 引き継ぎ（2026-09-22 時点）

ブランチ `claude/terminal-font-ligatures-3duhds`、PR #25（open）、HEAD `a644270`。
CI は 5 ジョブとも green、テスト 485 passed、ruff clean、全 62 面の検証は
非ヒント FAIL ゼロ。**そのままマージできる状態**で、以下は「さらに良くする」話。

## 1. いま終わったこと

自己レビューのループが停止条件（実レンダリング欠陥ゼロの回が 2 回連続）を
満たして終了した。経緯・測定値・据え置き事項はすべて `docs/gengou-plan.md`
に記録済み。**新しい作業を始める前にそこを読むこと**——特に「据え置き」の
一覧は、再発見して同じ結論に至るのを防ぐためにある。

変異体の最終状態: ラウンド 11 の 17 体は全数 CAUGHT、ラウンド 9 は 42 体中
6 体が盲点、ラウンド 10 は 71 体中 15 体。塞げなかったものは測定値と
「何を測れば塞がるか」まで `gengou-plan.md` に書いてある。

## 2. 次にやるべきこと（優先順）

### 2.1 `verify_jp.main()` の分解 ★最優先

**事実**: `scripts/verify_jp.py` は 1,819 行で関数は 10 個、うち `main()` が
1,410 行（ファイルの 77%）。その中に `check()` が 67 個、`for` が 89 個。
他のファイルは細かく割れている（`build.py` は 116 関数で最大 158 行、
`verifylib.py` は 77 関数で最大 262 行）。**構造上の異常はここ 1 か所だけ**。

**これが原因で実際に起きた欠陥**（ラウンド 12 の指摘のうち 5 件が同じ根）:

| 指摘 | 起きていたこと |
|---|---|
| 1a | JP 面で合字が 61 個すべて死んでいても合格していた（同じ規則が欧文の `main()` にもあり、片方だけ正しかった） |
| 1c | `NF_SYMBOLS` 必須のガードが欧文側だけにあった |
| 2b | 東アジア文字幅の 35 行が `check_widths_by_class` と完全に重複 |
| 2d | `CASES` ループの二重実装 |
| 3a | `check_family_cmap` が CI で一度も走っていなかった |

しかも**中を覗くたびに重複が出た**（ラウンド 12 で触った 3 か所すべてで崩れた）。
残り約 20 個の汎用検査はまだ誰も覗いていない。

**やること**: 67 個の検査を名前つき関数に出す。分類は以下:

- **汎用 約 20 個** → `verifylib.py` へ。欧文側 (`verify_latin.py` の
  `main()` 146 行) と統合できる可能性が高い。例: グリッド上の送り、
  ファミリー名・PostScript 名・ウェイト名、CFF と hmtx の幅の一致、
  hmtx のベアリングと xMin、テーブルの有無、異体字セレクタの cmap、
  `no overlap in X`、`NF_SYMBOLS` の有無、`=` のバー厚
- **JP 固有 約 47 個** → `verify_jp.py` の module 直下へ。例: かな・全角の
  中央配置、罫線のタイル、濁点の逃がし、注音の声調、Term の送り、
  ccmp の文脈、`＝` のバー厚

**等価性の証明**: 検証コードなので、分解の前後で全 62 面の出力（`ok` /
`FAIL` / `skip` の行）が 1 字も変わらないことを `diff` で示せる。必ずやること。

```sh
source <env>            # 下記 4. 参照
python scripts/verify.py 'dist/*.otf' 'dist/latin/*.otf' \
  'dist/nerd/*.otf' 'dist/nerd/latin/*.otf' > before.log 2>&1
# 分解後
diff before.log after.log     # 空であること
```

### 2.2 変異体ハーネスの repo 化 ★重要・時間制約あり

56 個の門番が「本当に効くか」を証明した道具は**リポジトリに入っていない**。
scratchpad にしかなく、コンテナが消えれば失われる:

```
<scratchpad>/r9-mutants/   1,089 行
<scratchpad>/r10-mutants/  1,730 行
<scratchpad>/r11-mutants/  2,437 行
<scratchpad>/r12-mutants/  2,531 行   計 7,787 行（mutlib.py は 4 世代で重複）
```

一方で門番の docstring は「round 11, mutant D2」「round 12, mutant W3」と、
**誰も走らせられないもの**を参照している。記録として機能していない。

救いとして、各変異体が何をするかは `gengou-plan.md` と門番の docstring に
文章で残っているので**再導出はできる**（ただし手間）。

判断すべきこと: repo に入れるなら 4 世代の重複を 1 つに整理する
(`mutlib.py` + 世代ごとの変異体定義)。入れた分、`tests/test_verifylib.py`
(1,871 行) のうち「作りものフォントで門番を 1 回呼ぶ」型のテストは
実フォントの変異体テストに置き換えられる。**総量は減り、証明力は上がる**。

### 2.3 `golden.py` の去就

402 行＋テスト 329 行。**CI にも release にも呼び手がいない**。2 つのビルドが
バイト同一かを証明する道具で、リファクタのたびに使ってきたが、リポジトリの
中では死んでいる。CI で使うか、repo から出すかを決めること。

## 3. 削減の見積もり（フォント機能 vs 処理本体）

**結論: 行数では処理側の方が大きいが、フォント機能側は成果物が軽くなる。
別の軸の話なので、行数だけで比べないこと。**

### フォント機能側

| | 消える関数（実測） | 散在する参照 | コード計 | 成果物から消えるもの |
|---|---|---|---|---|
| `fwid`/`hwid` 廃止 | 138 行<br>(`stretch_arrows` 68 / `add_width_alternates` 15 / `check_width_forms` 55) | 41 箇所 | **約 250 行** | 置換 **621 組**、グリフ **264 個** |
| 縦組み廃止 | 153 行<br>(`vmtx_origin` 11 / `vmtx_donor` 15 / `repoint_features` 36 / `check_vertical_origins` 53 / `check_vertical_layout` 38) | 31 箇所 | **約 250 行** | 置換 **773 組**、グリフ **346 個**、テーブル **3 つ**（vmtx/vhea/VORG） |
| 計 | | | **約 500 行**（全体 21,600 行の 2.3%） | グリフ **610**、置換 **1,394 組**、テーブル **3** |

注: `tile_vertically`(108 行) は縦組みではなく**罫線のタイル**なので残る。名前が紛らわしいだけ。

他実装の調査結果（実際にビルドスクリプトを読んで確認）:
- **Source Han Code JP**(Adobe、同じドナー): `fwid`/`hwid` **無し**、縦組みは**有り**
- **Moralerspace**(Monaspace+Plex JP): 幅の別形**無し**（別ファイルで対応）、`vhea`/`vmtx` を**明示的に削除**、和文側 GSUB/GPOS を**全削除**
- **HackGen**: `halt`/`vhal`/`palt`/`vpal`/`kern` を削除

→ **`fwid` を持っているのは我々だけ**（外れ値）。縦組みは Adobe が残し実用系は捨てる、で割れる。

### 処理本体側

| | 削減 | 備考 |
|---|---|---|
| `verify_jp.main()` の分解 | **150〜300 行**（推定） | 移動が主。削減は重複の崩れ。実績: ラウンド 12 で 3 箇所触って ~68 行 |
| `golden.py` 除去 | **731 行** | 判断次第で丸ごと |
| 変異体ハーネス repo 化 | **+7,787 行**（整理すれば ~3,000） | 追加。代わりに単体テストの一部を置換可 |

**本当の価値は行数ではない。** 処理側は「同じ原因で 5 件の欠陥が出た構造」を
直すもので、効果は将来の欠陥率に出る。フォント機能側は成果物が軽くなる話。

## 4. 作業の作法（必須）

- 開発は **`claude/terminal-font-ligatures-3duhds` のみ**。PR #25 がマージ済みなら
  default から同名で切り直す
- コミットメッセージの末尾に必ず:
  ```
  Co-Authored-By: <あなた> <noreply@anthropic.com>
  Claude-Session: <セッション URL>
  ```
- **リポジトリに入る成果物（コミットメッセージ、コード、コメント）にモデル名を
  書かない**（上の `Co-Authored-By` だけが例外）
- GitHub 操作は **`mcp__github__*` のみ**（`gh` CLI は無い）
- **CI を赤くしない。** 押す前に必ず: `python -m pytest tests/ -q`、
  `ruff check scripts tests`、全 62 面の検証
- このセッションのトークンでは**タグを打てず、workflow_dispatch もできない**（403）。
  リリースの動作確認はコミットメッセージに `[release-dry]` を入れる

### ビルドと検証

```sh
export SCP_VF_U=... SCP_VF_I=... SS_VF_I=... MONA_VF=... SHS_DIR=... NF_SYMBOLS=...
export GENGOU_VERSION=6.0.0
export GENGOU_SKIP_AUTOHINT=1        # ローカル用。これを立てると
                                     # 「carries hints」FAIL が出るのは正常

python scripts/build_latin.py "Regular Upright"    # 欧文静的面（数秒）
python scripts/build_latin_vf.py                   # 可変フォント 2 本
python scripts/build.py "Regular Upright base Term" # JP + Term（1 面 1 分弱）
python scripts/nerdpatch.py dist/*.otf             # Nerd Fonts 版

python scripts/verify.py <font...>   # 唯一の入口。glob 可。
                                     # どの門番に掛けるかはフォント自身が決める
```

JP 面の検証は 1 面約 24 秒（うち 13 秒はラウンド 12 で入れた
かな・漢字 13,944 字のドナー比較）。

## 5. 人手が要る項目（エージェントではできない）

1. **`v6.0.0` タグを手で切る。** 未設定だとリネーム全体が `v5.0.1` として
   自動公開されうる（`bump_pins.MIN_RELEASE` が止めるようにはなっている）
2. **リポジトリ名のリネーム。** `PROJECT_URL` と `LICENSE` は意図的に旧名の
   まま。リネーム後に 1 行更新
3. **商標確認**

## 6. 読む順序

1. `README.md` — 何を作っているか
2. `CONTRIBUTING.md` — 作法、テスト・検証の走らせ方
3. `docs/gengou-plan.md` — 全ラウンドの記録。**「据え置き」は再発見しないこと**
4. `scripts/verifylib.py` の docstring — 各門番がどの変異体のために存在するか
