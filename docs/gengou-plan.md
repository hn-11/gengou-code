# Gengou — 欧文中間フォント計画

状態: 段階 1（1a・1b とも）・段階 2（VF 化）とも実装済み。v5.0.0 で
基準を英語圏のターミナルフォントに置き換えた（下の「v5」節）。
`scripts/build_latin.py` が Source Code Pro VF + Monaspace VF から直接
Gengou（`dist/latin`）を組み、`scripts/build.py` はそれを Source Han
Sans に接ぎ木する側になった（VF には直接触れない）。
`scripts/build_latin_vf.py` が同じレシピを CFF2 可変フォントとして組む
（`dist/latin/Gengou[wght].otf` / `Gengou-Italic[wght].otf`）。
`Gengou.zip` は VF 2 面（静的 10 面は JP 面のドナー・NF パッチの入力・
VF の検証に使い、配布しない）。名前は **Gengou**（源合）で確定し、
和文入りは **Gengou JP**（v3.2.0 までの Shoyu Code Pro JP、v5.0.0 までの
Sumi Moji JP からの二度目の改名。由来と衝突調査は 2 節）。

## v5: 基準を英語圏のターミナルフォントに

v4.0.0 までは Source Han Code JP（SHCJ）が基準だった: 2:3 の比率、SHCJ の
行間（1.453 em）、SHCJ の `=` バーに Latin の太さを寄せる主従、SHCJ の
半角/全角の割り当て。v5.0.0 で基準を欧文側（Source Code Pro）に置き換え、
SHCJ は上流から外れた。

- **セルは 600、既定は 3:5**。Gengou（SCP 原寸）に Source Han Sans を
  そのまま載せる。2:3（旧基本ファミリー）と 35 は廃止、Term（1:2）は
  全角の送りを 2 セルに広げるだけの変種として残す。
- **行間は SCP の 984 / −273（1.257 em）**。hhea = typo、
  `USE_TYPO_METRICS`。win は Source Han Sans の宣言値（1160 / 288）。
- **太さの主従を逆転**。Latin は SCP の名前付きインスタンス（Light 300 /
  Regular 400 / Medium 500 / SemiBold 600 / Bold 700）そのもの、和文は
  `＝` のバーが合う Source Han Sans の面を実測で選ぶ（ExtraLight / Normal /
  Regular / Medium / Bold）。Normal と Heavy は消え、ウェイト名は英語
  フォントの体系になった。VF の wght 軸は SCP の wght と一致（恒等写像）。
- **幅の方針**: Gengou が持つ文字はすべて 1 セル（ギリシャ・キリル・
  罫線・矢印 7 種と `≠ ≤ ≥ …` も）。JIS 流の全角字形は `fwid` で戻す
  （矢印は合字から切り出した全角版、その他は Source Han Sans の全角
  グリフか同フォントの `fwid` 形）。`hwid` / `ss09` の幅切り替えは不要に
  なり廃止。Source Han Sans の比例幅の残り（半角カナ 500、Hangul 字母
  920、ﬀ、⸻）はセルか全角の倍数に中央配置（`fit_to_grid`）。
- **東アジア文字幅が Wide の 13 字（`☕` `🎵` `🎶` `💩` `🔒` `🤖`、Hangul
  声調記号 2 字、注音の入声 5 字）は 1 セルのまま**。どれも片方のドナー
  にしか無く（前 6 字は Source Code Pro の 600、注音 5 字は Source Han
  Sans の 600、声調記号 2 字は Source Han Sans の 250 を `fit_to_grid` が
  1 セルに置く）、どちらにもこれより広い字形が無いため。ターミナルは
  2 桁分を空けるので左寄りに見える。2 セルに広げるかは未決（README の
  「幅の方針」に明記）。
- **東アジア文字幅が Neutral の 142 字が全角のまま**（Unicode 14.0 での
  実測。この分類は Unicode の版で動くので、新しい `unicodedata` で数え
  れば増える。`␣` U+2423、`⌘`
  `⚠` `⏎` `➡` `✚` `ﬃ` `ﬄ` など、Source Han Sans しか持たない記号）。
  ターミナルは 1 桁しか空けないので隣に食い込む。曖昧幅（A）と違い
  ターミナル側の設定では直せない。v4 では Source Han Code JP が 1 セルの
  `␣` を持っていたが、Source Code Pro には無い。1 セルに詰めるには縮小が
  要り（v5 で廃止した）、方針（「Source Han Sans にしかない文字は全角の
  まま」）とも衝突するので、要判断。
- **NF 版のファミリー名が GDI の 31 文字に収まらない**（`Gengou` への
  改名で半減、一部残る）。`Gengou JP Term Nerd Font Mono` は 29 文字で
  収まるが、非 RIBBI は nameID 1 にウェイト名が付くので
  `... Nerd Font Mono SemiBold` が 38 文字になる。JP の NF 20 面のうち
  8 面（Term の Light / Medium / SemiBold 各 2 面と、基本ファミリーの
  SemiBold 2 面）が `LOGFONT.lfFaceName`（31 文字）に入らない。欧文の
  10 面は全部収まる。v5.0.0 の `Sumi Moji` では Term の RIBBI が
  32 文字で、JP 16 面・欧文 2 面が入らなかった。
  DirectWrite の Windows Terminal や macOS / Linux では問題ないが、
  旧 conhost・メモ帳・Office の GDI 経路ではファミリー名で引けない。
  nameID 1 だけ短い別名にする手はあるが（本家 font-patcher の
  `--windows` 相当）、ピッカーによって別名で出るのと引き換え。
  Nerd Fonts 本家の命名を優先して現状維持、要判断。
- ~~**`drop_features` は参照されなくなった Lookup を残す**~~ **解決**
  （`prune_orphan_lookups`）。FeatureList から到達可能性を辿り、文脈
  依存 Lookup が呼ぶ先も再帰的に追って、届かない Lookup を捨てて索引を
  張り替える。JP Regular の実測で **GPOS 46,320 → 9,922 bytes**
  （−79%）、GSUB 35,102 → 34,582、ファイル全体で 1 面あたり 36,916
  bytes 減（30 面で約 1.1 MB）。`golden.py` で改修前後を突き合わせ、
  cmap・送り幅・シェーピング 665 通り・アウトライン 16,831 グリフ・
  メタデータがすべて一致することを確認済み。JSTF を持つフォントは同じ
  LookupList を索引するので触らない。
- **リリースの faces ジョブは欧文の静的面を 2 回ずつ作っている**
  （base と Term が同じドナーを使うため、10 面ぶんを 20 回）。欧文を
  別ジョブにして artifact で渡せば省けるが、アップロード / ダウンロード
  の往復と引き換えなので未着手。
- ~~**接ぎ木後の `update_bbox` は全グリフを描き直している**~~ **解決**
  （`update_bbox_after`）。接ぎ木が書いたグリフの箱だけで既存の extent を
  広げる。実測で JP 面 **6.0 秒 → 0.03 秒**、1 面の所要が 35 秒から 27 秒に。
  集約値は足せても引けないので、**差し替えたグリフが旧の極値を支えていて
  新しい字形がそこに届かない場合だけ**拒否して全再計算に戻す。欧文面が
  まさにその例で、Powerline の差し替えで `yMax` が 1060 → 1000 に下がる
  ため拒否される（拒否しなければ 1060 と誤って記録する）。JP 面は
  Source Han Sans のインクが 1808 まであるので影響を受けず、速い経路を
  通る。`verify.py` の `check_tables` がアウトラインから再計算して
  突き合わせるので、誤りは CI で必ず落ちる。
- **Nerd Fonts 版の命名は本家の流儀**: アイコンを 1 セルに収めるので
  `<Family> Nerd Font Mono` / `<PSFamily>NFM`。v5.1 で font-patcher と
  FontForge を捨て、本家の `Symbols Nerd Font Mono` から fontTools で
  接ぎ木する（同じ記号集合・同じ 1 セル送り、1 面 10 秒、CID 構造もメタ
  データもそのまま。寸法の差は下の項）。本家の立場は「フォールバック ＞ パッチ／合成」で、
  合成でも記号集合と寸法を本家に合わせ、名前に Nerd Font を含め、出典の
  ライセンスを添える——この 3 点を満たしている。
- **NF 版のアイコンは正方セルに収めている（本家パッチは 600 x 856）**。
  font-patcher は `--mono` のアイコンを セル幅 x `iconheight` に収める。
  `iconheight` は `(capHeight x 2 + 行の高さ) / 3` で、この面では
  `(656 x 2 + 1257) / 3 = 856`。接ぎ木元の `Symbols Nerd Font Mono` は
  2048 x 2048 の正方セルに収めて作られているので、セル / em の一様縮小
  （600 / 2048）では箱が 600 x 600 になり、縦長のアイコン 3,496 字
  （引き伸ばす群——区切りと進捗バー——を除いた 10,363 字中）が本家パッチ
  より最大 1.43 倍小さい。font-patcher 独自の
  縦パディングが効く群（重い山括弧 U+276C〜2771 など）では最大 2.1 倍。アイコンごとに
  収め直すと、複数のアイコンを同じ倍率で束ねる font-patcher の
  ScaleGroups が崩れる（束の中の小さいアイコンが 3.1 倍に膨らむ）ので、
  正確に合わせるには本家の群テーブルを移植するしかなく、それは
  `nerdpatch.py` が避けている複雑さそのもの。現状は「ターミナルに
  `Symbols Nerd Font Mono` をフォールバックとして足したときと同じ相対
  寸法」で、セルからはみ出す側には決して倒れない。要判断。
- **結合文字が縦組みで次のセルに落ちる**。接ぎ木した結合文字 53 字
  （U+0300〜U+036F）は、アウトラインを 1 セルぶん左に寄せて送り幅 0 に
  する方法で置いている。横組みの位置はドナー自身の GPOS を移して
  （`import_scp_marks`。アンカーは新設ではなく Source Code Pro のもの）
  解決した——`k` + U+0301 は `x_offset -122` / `y_offset +229` に付く——が、
  縦組みでは「1 セル左」が「1 字ぶん下」を意味しないので、NFD の `ḱ` は
  まだ `k` の次のセルにアクセントが落ちる。ドナー自身の縦組みでも同じ
  位置に落ちるので、縦組み用のアンカーはこちらで新設することになる。
  要判断。
- ~~**斜体面にギリシャ・キリルが揃わない**~~ **解決**（Source Sans 3
  Italic をドナーに追加）。実測した状態はこうだった: Source Code Pro
  Italic はキリルを 1 字も持たず、ギリシャは `π`（U+03C0）だけ——Adobe が
  手で描き起こしたイタリックの意図的な線引きで、待っても埋まらない。
  欧文単独の斜体面はその 1 字しか持たず、JP の斜体面は Source Han Sans の
  比例幅で 115 字を埋めて 119 字が欠けていた。しかもその 115 字は
  **直立面とは別書体**（`Δ` の cap が 732 対 656、`α` の x-height が 554 対
  498）で、周囲のラテンが 11° 傾いているのに**直立のまま**だった。
  Source Sans 3 Italic は Source Code Pro の起源にあたる書体で、実測で
  italicAngle（−11.0）と cap height が一致し x-height は 1 ユニット差
  （wght 400 / 700 とも）。比例幅なので `build.cell_fit` で 1 セルに
  中央配置し、収まらない 43 字だけ左右 8u まで詰める。結果、直立・斜体
  とも 234 字で一致し、ファミリー全体の cmap の差は 249 字から 16 字に
  減った（残る 16 字は他ブロックで、Source Code Pro Italic が元から
  持たないもの）。直立面が持たない 10 字を Source Sans は持つが、
  斜体だけ広いのは逆向きの不整合なので入れていない。
  Source Han Sans のギリシャ・キリル 115 字は Source Code Pro の 234 字に
  完全に含まれるため、この変更後は 1 字も使われない（`narrow_letters` は
  上流が変わったときの保険として残置、`letters=0` がそれを示す）。
- **JP 面の `usWinDescent` 288 は欧文レイヤーの罫線より浅い**。
  Source Code Pro 由来の罫線素片は −400、ブロック要素は −454 まで
  伸びるので、cmap 上の 111 字が宣言値の外にある。`USE_TYPO_METRICS` を
  読む描画系（DirectWrite / CoreText / HarfBuzz）は 1257u の行を使うので
  影響しないが、GDI 系だけは下端が切れうる。この面のインクは 1808 /
  −1048 まであり、bbox を全部覆うと GDI の行が 2856u（typo の 2.3 倍）に
  なるため覆えない。−454 まで上げれば罫線は救えて GDI の行は 1448 →
  1614u（+11%）。Source Han Sans 自身も 288 のまま −1048 のグリフを
  抱えているので現状維持、要判断。
- **上流アセットのハッシュ検証が無い**。`fetch-upstreams` は 4 つの zip を
  `curl -sSfL` で取って展開するだけで、キャッシュキーもタグ名だけから
  作っている。GitHub のリリース資産はタグを変えずに差し替えられるので、
  差し替えられても気付けない。zip の SHA-256 をピンと一緒に記録し、
  キャッシュキーにも混ぜるのが筋。未着手。
- **SHCJ 依存の解消**: バーの目標値（Latin が固定なので不要）、半角カナ
  のドナー（Source Han Sans 自身の 500 幅を中央配置）、行間（SCP）、
  半角の集合（Gengou の cmap）。`SHCJ_TTC` と `SHCJ_TAG` は消えた。

英語フォント基準で判断した残りの課題（優先順）: README の見本画像、
fontbakery を CI に、VS Code 統合ターミナル（xterm.js）の合字、Homebrew
cask / Scoop、リポジトリ名と `PROJECT_URL` の改名。合字なし変種
（JetBrains Mono NL / Cascadia Mono 相当）は需要が出てから。Nerd Fonts の
記号を本体に同梱する案（Cascadia 流）は、本家が名前で識別できることを
望んでいる以上、NF 付きの別ファミリーのままにする。

## 1. 目的

Gengou JP の欧文層（Source Code Pro の文字 + Monaspace の記号・合字）を
**独立した欧文フォントとして先に完成させ**、JP はそれを Source Han Sans に
載せるだけの工程にする。

- 欧文側の設計判断を 1 か所に集める: 記号の Monaspace 化、合字の文脈ガード、
  太さ合わせ、ヒントのアライメントゾーン、Light の削り（Monaspace wght 下限対策）
- 欧文フォント単体で HarfBuzz / fontbakery / 実機（Windows Terminal, iTerm2）の
  検証を回せるようにする。JP 側の検証は「和文と幅」に絞れる
- JP / 35 / Term の 3 ファミリーが同じ中間物から出るので、ファミリー間の
  欧文の差が構造的に消える
- 和文が不要な利用者向けに、そのまま配布物になる

描画結果は現行と同じものを目標にする（リファクタリングであって再設計ではない）。

## 2. 命名

| 用途 | ファミリー名 | PostScript 名 |
|---|---|---|
| 欧文のみ | Gengou | Gengou-Regular など |
| 欧文のみ NF | Gengou Nerd Font Mono | GengouNFM-Regular |
| 和文入り | Gengou JP / Gengou JP Term | GengouJP-Regular, GengouJPTerm-Regular |
| 和文入り NF | Gengou JP Nerd Font Mono など | GengouJPNFM-Regular など |

リブランディングで名前を変えた箇所（Shoyu Code Pro JP → Sumi Moji JP →
Gengou JP の二度の改名とも同じ箇所を触っている。リポジトリ名と
`PROJECT_URL` だけ未実施: リポジトリを改名すると GitHub は旧 URL を転送
するので、フォントの name テーブルに焼く URL は改名を見てから差し替える。
先に新 URL を書くと、改名までのあいだ 404 を焼いたフォントが出る）:

1. `scripts/build.py` の `set_names`（family / PostScript 名のプレフィックス）と `PROJECT_URL` / `PROJECT_COPYRIGHT`
2. `scripts/nerdpatch.py` の NF 命名正規表現
3. TTC のファイル名（のちに TTC 自体を廃止）
4. `.github/workflows/release.yml` のリリース資産名と `GENGOU_VERSION` 環境変数名
5. `scripts/verify.py` の `FAMILY_METRICS` 判定（ファミリー名のトークン）
6. README / LICENSE の名前と、リポジトリ名・`git remote`

命名上の注意:


- OFL の Reserved Font Name により `Source` と `Monaspace` はフォント名に
  使えない。OFL FAQ 5.4 は「RFN の単語全体は不可、単語の一部は可だが非推奨」
  で、`Monasource` は `Source` を丸ごと含むため不可側。`Gengou` は
  どちらの RFN も含まない
- 名前の由来: **源合**（げんごう）。**源**は Source Code Pro と源ノ角
  ゴシック（Source Han Sans JP）が共有する `Source` の訳字で、RFN が英語の
  `Source` を塞いでいることへの言い換えそのもの。**合**は合字の合であり、
  3 つの上流を合わせる合成の合でもある。どちらもこの書体の固有の特徴を
  指している
- v5.0.0 までの `Sumi Moji`（墨文字）からの改名: 筆致も滲みも抑揚もない
  角ゴシックに墨の名前は合っていなかった。命名時の判定が衝突調査だけで、
  字面と名前が合っているかを見ていなかったのが原因
- 衝突調査: フォント名 `Gengou` は既存なし。長音なしの `Gengo` は翻訳
  プラットフォーム Gengo（Lionbridge）と Go のコード生成ライブラリ
  kubernetes/gengo に当たり、`Gen Go Code` は英語で「generate Go code」と
  読めるので、どちらも採らなかった。源◯の二字（源真・源柔・源界・源暎・
  源泉・源流・源雲）は既存の派生フォント群で埋まっている
- name ID 0 / 9 のドナー表記、achVendID `GNGO`、STAT、WWS は JP と同じ規約

## 3. 仕様

### 3.1 グリフセット

- Source Code Pro VF の全レパートリー（ラテン・ギリシャ・キリル・記号・
  結合文字・罫線）。SCP 原寸（600 セル、1000 em）
- ASCII 記号 32 字と合字 61 種は Monaspace（現行と同じ選定、`data/mona_ligs.json`）
- `← → ↑ ↓ ⇐ ⇒ ⇔ ≠ ≤ ≥ …` は **1 セルの Monaspace 版を既定**にする
  （欧文フォントに全角は無い。JP で使う全角版は JP 側で合字グリフから切り出す、
  現行 `stretch_arrows` のまま）
- 合字グリフは現行どおり n セル幅の 1 グリフ（LigatureSubst）。Fira Code 式の
  スペーサー方式（VS Code 統合ターミナル対応）はスコープ外、別課題

### 3.2 GSUB / GPOS

- `calt` / `liga`: 合字 61 種 + 文脈ガード（入力列を全構成グリフでカバーする
  トリガールール、最長一致順）
- `ss01`〜`ss08`: 合字グループ、`cv99`: .alt 字形（`ss09` の幅切り替えは
  v5 で廃止: 既定が 1 セル、全角は `fwid`）
- SCP 由来: `zero` `salt` `cv01`〜`cv17` `ss11`〜`ss17`（+10 マウントは JP との
  整合のため維持）
- GPOS は SCP 自身のもの（結合文字の `mark` / `mkmk`、`frac`、`size`）を保持。`kern` は無い（等幅）

> **注記（v5）**: 以下 3.3・3.4 は v4 までの設計（4 は v5 の構成に
> 書き直してある）。v5 で基準を
> Source Code Pro に移した結果、行間は SCP の 984 / −273、ウェイトは
> SCP の名前付きインスタンス 5 つ、`dist/latin/term/` と拡大処理
> （`rescale` / `narrow_ambiguous` / `latin_onecell`）は無くなっている。
> 現行の仕様は本ファイル冒頭の v5 節と README を参照。

### 3.3 メトリクス

- 送り 600、UPM 1000。行間は SCP の hhea 値（984 / -273）で、OS/2 typo を同じ値にして
  USE_TYPO_METRICS を立て、win はファミリー全面のバウンディングボックスの最大値。JP に
  載せるときは現行どおり SHCJ の行間に差し替える
- `post.isFixedPitch=1`、PANOSE proportion 9、xAvgCharWidth は実計算、
  sxHeight / sCapHeight は実測（JP と同じ関数）

### 3.4 ウェイト

- 段階 1（静的）: JP と同じ 6 ウェイト × 2 スタイル。各面の太さは
  **SHCJ の `=` バー厚に一致**させる（現行の二分探索）。名前は JP と同じ
  Light / Normal / Regular / Medium / Bold / Heavy
- 段階 2（VF）: wght 軸 200〜900（SCP の範囲）。JP はこの VF を SHCJ の
  バー厚に合う wght でインスタンス化して使う。Term の太さ補正（600 セルのまま
  バー 69）も「少し重い wght でインスタンス化する」だけになり、現行の
  「拡大→削り」の工程が不要になる

### 3.5 ヒント

- SCP VF をインスタンス化するとヒントが落ちる（fontTools の CFF2 インスタンサ）ため、
  SCP 自身のアライメントゾーン（Private の BlueValues 等。インスタンス化で
  ペアが逆順になることがあるので並べ直す）に対して全グリフを otfautohint で
  ヒント付けし、cffsubr でサブルーチン化。JP 側は接ぎ木後に自分のゾーンで付け直す
- VF（CFF2）は otfautohint が対応しているが、ヒントはデフォルト
  マスターのみに乗る。静的インスタンスを配布するならインスタンス後に付け直す

## 4. ビルド構成

実装済み（段階 1a・1b・2 とも）。v5 時点の実際のパイプライン:

```
scripts/build_latin.py     # SCP VF + Monaspace VF
                            #   -> dist/latin/Gengou-*.otf（配布物であり、
                            #      JP 面のドナーでもある 10 面）
scripts/build_latin_vf.py  # 同じマスターを varLib で合成
                            #   -> dist/latin/Gengou[wght].otf
                            #      dist/latin/Gengou-Italic[wght].otf
scripts/build.py           # SHS + dist/latin
                            #   -> dist/GengouJP*.otf（JP / JP Term の 20 面）
scripts/nerdpatch.py       # Nerd Fonts の記号フォントを接ぎ木
                            #   -> dist/nerd{,/latin}/*NFM-*.otf
scripts/harmonize_latin.py # 欧文ファミリーの win メトリクスを面をまたいで揃える
scripts/verify.py          # JP 面の回帰テスト
scripts/verify_latin.py    # 欧文静的面の回帰テスト
scripts/verify_latin_vf.py # 可変フォントの回帰テスト
scripts/verify_many.py     # 上の 3 つを glob で振り分けてまとめて走らせる
scripts/golden.py          # 2つの dist ディレクトリを比較（cmap・送り幅・
                            #   シェーピング・アウトライン・メタデータ・ヒント）
```

`build.py` は SCP VF・Monaspace VF に直接触れなくなり、`scripts/build_latin.py`
が先に走って `dist/latin` を作っていることを前提にする（`LATIN_DIR`
環境変数、既定 `dist/latin`）。Source Han Sans CJK（SHCJ）は v5 で上流から
外れたので、このパイプラインには出てこない。VF のインスタンス化・
太さ二分探索・合字/記号の合成・グラフト用ヘルパー（`VFSource.matched`、
`draw_clean` / `erode_path`、`replace_from_mona`、`add_glyphs`、`add_gsub` /
`_guard_subtables`、`import_scp_variants`、`latin_blue_zones` /
`add_latin_fd`、`autohint_face`、`subroutinize_face` など）は `build.py`
モジュールに残ったまま `build_latin.py` から import されて使われる形で、
別モジュールへの複製はしていない。`build.py` 側は同じ関数群を、VF
インスタンスではなく `dist/latin` の完成品 OTF（`graft_halfwidth`,
`import_scp_variants`, `latin_ligatures`, `latin_onecell` 等が受け取る）
に対して呼び出すだけになった。

build.py に残る処理: SHS の読み込み、SHCJ からの半角カナ等の複写、行間の
複写、Gengou からのグリフ・GSUB の取り込み（グリフ名を CID に付け替え、
lookup と feature を SHS の GSUB にマージ）、10/9 拡大（JP）、`narrow_ambiguous`
と `widen_fullwidth`（Term）、`stretch_arrows` と `add_width_alternates`、
名前・STAT・メタデータ、NF パッチ。

JP 側の出力は、書き換え前（VF を直接読んでいた頃）とグリフアウトライン・
cmap・GSUB の shaping 結果が roundoff（±1〜2ユニット）を除いて一致する
ことを目標にしており、`scripts/golden.py` で2つの dist ディレクトリを
比較して確認する。

## 5. 段階

### 段階 1a: 35 から切り出し（実装済み、のち段階 1b で置き換え）

最初の実装。`build_latin.py` を切り出し、`dist/GengouJP35-*.otf`
（`build.py` が既にビルドした 35 面）から `dist/latin/` に
`Gengou-*.otf` 12 面を出す中間形態だった。`verify_latin.py` と
`Gengou.zip` のリリース資産化はこの段階で入り、以降も引き継がれている。
段階 1b の実装により、35 の完成品 OTF を経由する経路そのものは
置き換わっている。

### 段階 1b: build_latin.py が VF から直接組み、build.py が消費する（実装済み、v4.0.0）

1. ✅ `build_latin.py` の入力を 35 の完成品 OTF から SCP VF + Monaspace VF
   直接に変えた: SCP VF のインスタンスを CFF2ToCFF で静的 CID-keyed CFF
   化し、Monaspace の合字・記号・1セル矢印を接ぎ木、otfautohint で
   再ヒントして cffsubr でサブルーチン化（4節参照）
2. ✅ `build.py` を「欧文 OTF（`dist/latin` / `dist/latin/term`）を読む側」
   に書き換えた（`SHS_DIR` / `SHCJ_TTC` / `LATIN_DIR` のみを見る。
   `ci.yml` / `release.yml` とも `build_latin.py` を先に実行する）
3. ✅ **ゴールデン比較**: `scripts/golden.py` を追加し、2つの dist
   ディレクトリ間で cmap・送り幅・シェーピング・アウトライン（許容誤差
   付き）・メタデータ・CFF ヒントを比較できるようにした
4. 未着手: fontbakery universal チェックの `verify_latin.py` への追加

見積り: 数日。描画結果は変わらない（実績: roundoff ±1〜2ユニットの差を
除き一致）。

### 段階 2: VF（実装済み、v4.0.0、`scripts/build_latin_vf.py`）

1. ✅ デザインスペース: SCP VF 自身のマスター位置——**wght 200 / 400**
   （事前の見積りは「約 458」だったが、CFF2 の VarStore 領域のピークを
   avar/fvar 経由で逆算すると実際は 400 だった。決め打ちせず
   `build_latin_vf.confirm_scp_master_wghts` が毎回読み直す）に **Regular
   と Heavy の位置**（既定マスターと軸の上限。SCP の 900 マスターは上限
   の外）と **Monaspace の下限位置**（Monaspace の wght 200 のバーが
   SCP のバーと一致する SCP wght。これより細い側は Monaspace が下限で
   クランプされ一定、太い側は SCP 追随——このマスターが無いと Normal の
   記号が 4u 太くなる）を加えた 5 マスター——それぞれで SCP を厳密な wght に
   インスタンス化し、Monaspace を**太さ一致でインスタンス化**した静的
   マスターを用意する。マスターを置く設計座標は「SCP のユーザー wght を
   SCP 自身の fvar 正規化 + avar に通して線形化したもの」
   （`scp_design_axis`）——SCP の VF はユーザー wght に対して線形では
   ないので、ユーザー wght のまま線形補間すると中間ウェイトが静的版
   からずれる（初版はこれで Light のバーが 41u → 58u になっていた）。
   SCP 側のマスターは instancer の整数丸めを切ってインスタンス化する
   ——相対座標への丸めが経路に沿って累積し、丸めたマスターから組むと
   マスター間で `m` が最大 10u ずれた（実測）。
   Monaspace の wght 下限 200 で足りない場合、事前の見積りは「現行の
   erosion で削る」だったが、実装では **erosion をしない**方針にした
   ——erosion は pathops のブーリアン演算で非線形、マスター間の補間に
   使えるものではない（実測: `VFSource.matched` に `erode=False` を
   足すとそのまま下限でクランプするだけで済み、`fontTools.varLib.build`
   が問題なく通ることを確認済み）。詳細は次項のリスク参照
2. ✅ fontTools varLib でマスター群から CFF2 VF を組む（Upright /
   Italic は SCP と同じく別ファイル）。Monaspace 由来グリフは
   Monaspace VF の補間互換アウトラインから来るので互換性は保てるが、
   pathops の simplify を通すと点数が変わるため、**simplify は VF
   では使わず**重なりは残す（Adobe の VF と同じ扱い。
   `build.draw_clean` に `simplify=False` を追加）。ヒント付け・
   サブルーチン化も VF には行わない
3. ✅ STAT / fvar のインスタンス名は段階 1 と同じ 6 ウェイト、wght 軸は
   静的版の STAT と同じ usWeightClass の値（300/350/400/500/700/900、
   既定 400 = Regular で OS/2 usWeightClass と一致）で、avar が各値を
   段階 1 と同じ「SHCJ の `=` バー×600/667」に一致する SCP wght
   （実測: Upright 317/374/406/545/670/857、Italic 317/377/399/538/
   661/841）へ写す（`user_axis`。SCP 自身の avar の折れ点も引き戻して
   写像に含めるので、名前付きインスタンスの間でも SCP と厳密に一致
   する——`verify_latin_vf.py` が SCP_VF_U/I を指す環境で検証）。
   name テーブルは SCP VF 自身の慣習（`SourceCodeVF-Upright.otf` /
   `-Italic.otf`）に倣い nameID 6 に `Gengou-Roman` /
   `Gengou-Italic`、nameID 25 に `Gengou`、nameID 16/17 は省略
4. 未着手: JP 側 (`scripts/build.py`) を「欧文 VF をそのまま
   `VFSource.matched` でインスタンス化して使う」側へ切り替える作業。
   今回追加したのは Gengou 単体の VF（配布物）のみで、JP 側は
   引き続き `dist/latin` の静的 OTF（`build_latin.py` の出力）を
   接ぎ木している
5. 未着手: JP 側 12 面を、今回の VF からインスタンス化して作る経路
   （今は `build_latin.py` が別レシピで静的 12 面を直接組んでいる）

見積りどおり数日で実装。4・5 は次の課題として残す。

## 6. リスク・未決事項

- **重なり除去 vs 補間互換**: 静的版では pathops で重なりを除去しているが、
  VF ではマスター間の点対応が崩れる。VF は重なりを残し、静的インスタンスで
  除去する二本立てにした（実装済み）
- **Light の削り**: erosion は非線形なので VF では補間で再現できない
  ——見積り時点では「Light 相当をマスターに立てる」を想定していたが、
  実装では **erosion 自体をしない**（Monaspace が自身の wght 200 の
  下限で単にクランプする）方針にした。SCP wght がおよそ 366 を下回ると
  Monaspace 側の記号・合字はその下限の太さで止まり、静的版が erosion
  で削っている太さより太くなる——Light（SCP wght ≈317）はこの範囲に
  入るため、VF の Light 相当の記号は静的 Light（erosion 版）よりわずかに
  太い。静的 Light は引き続き erosion 版を配布する。マスターを増やして
  この範囲もカバーする案は保留（erosion 自体が非線形なので、マスターを
  増やしても補間では再現できないことに変わりはない）
- **太さの線形性**: SHCJ の各面に対する wght の一致点は二分探索で求めている。
  SCP 側は設計座標を SCP の avar で線形化してあるので中間ウェイトでも
  厳密に一致する（実装済み、`verify_latin_vf.py` で検証）。Monaspace 側は
  5 マスターの間で線形補間になるため、名前付きインスタンスの間では
  SCP との太さ一致に 1u 程度のずれが出うる。超える場合はマスターを増やす
  ——実測では Regular 実インスタンスのバー厚が静的版に対し ±1u 以内
  （`scripts/verify_latin_vf.py` で継続確認）
- **Italic**: SCP Italic は −11°（`post.italicAngle`、実測ステム角
  11.38°）で Monaspace の slnt の下限と一致するため、シアーは掛からない
  ——コード中の −12° は角度を申告しないドナーへのフォールバック
- **名前**: Gengou / Gengou JP で確定。商標（USPTO / J-PlatPat）は
  この環境から未確認。変更箇所の一覧は 2 節
- **バージョン**: JP と同じタグで同時にリリースする（別バージョン番号を
  持たない）
