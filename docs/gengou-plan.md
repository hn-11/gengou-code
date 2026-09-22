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
  `USE_TYPO_METRICS`。win は 1160 / 454（上は Source Han Sans の宣言値、
  下は欧文の罫線・ブロック要素を覆う値。`build.WIN_METRICS`）。
- **太さの主従を逆転**。Latin は SCP の名前付きインスタンス（Light 300 /
  Regular 400 / Medium 500 / SemiBold 600 / Bold 700）そのもの、和文は
  `＝` のバーが合う Source Han Sans の面を実測で選ぶ（ExtraLight / Normal /
  Regular / Medium / Bold）。Normal と Heavy は消え、ウェイト名は英語
  フォントの体系になった。VF の wght 軸は SCP の wght と一致（恒等写像）。
- **幅の方針**: Gengou が持つ文字はすべて 1 セル（ギリシャ・キリル・
  罫線・矢印 7 種と `≠ ≤ ≥ …` も）。JIS 流の全角字形は `fwid` で戻す
  （矢印は合字から切り出した全角版、その他は Source Han Sans の全角
  グリフか同フォントの `fwid` 形）。自前の `hwid` / `ss09` の幅切り替えは
  不要になり廃止（Source Han Sans 自身の `hwid` は残る）。Source Han Sans の比例幅の残り（半角カナ 500、Hangul 字母
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
  `␣` を持っていたが、Source Code Pro には無い。**据え置き。** 実測すると
  142 字のうち**インクが 1 セル（600）に収まるのは Regular で 16 字
  （Light 19、Bold 15）だけ**で、残りはインク自体が 600 より広い（最大は `⏊` の 1000 ちょうど）。
  送り幅を 600 にして中央に置いても、インクは左右にはみ出したままで
  重なりの総量は変わらない——**この 120 字余りは縮小しない限り直らない**のに、
  v5 はその縮小を廃止した。上流に従って全角のままにする。
- ~~**NF 版のファミリー名が GDI の 31 文字に収まらない**~~ **解決**
  （nameID 1 だけ `NFM` に略す。`nerdpatch.NF_MARKER_GDI`）。綴ったままだと
  `Gengou JP Term Nerd Font Mono` 自体は 29 文字で収まるが、非 RIBBI は
  nameID 1 にウェイト名が付くので `... Nerd Font Mono SemiBold` が
  38 文字になり、JP の NF 20 面のうち 8 面（Term の Light / Medium /
  SemiBold 各 2 面と、基本ファミリーの SemiBold 2 面）が
  `LOGFONT.lfFaceName`（31 文字）に入らなかった（欧文の 10 面は全部収まる。
  v5.0.0 の `Sumi Moji` では Term の RIBBI が 32 文字で、JP 16 面・
  欧文 2 面が入らなかった）。nameID 1 を `Gengou JP Term NFM SemiBold`
  （最長 27 文字）に、nameID 16 / 4 は綴ったままにする分割で解決した。
  本家 font-patcher の `--windows` と同じ手で、DirectWrite 系
  （Windows Terminal・macOS・Linux）は 16 を読むので表示は変わらず、
  GDI 系のピッカーにだけ略称が出る。`verifylib.check_gdi_family_name` が
  31 文字を全面で門番している。副作用として NF 面の nameID 4 は
  nameID 1 で始まらなくなる（fontbakery の
  `opentype/name/match_familyname_fullfontname` はこれを落とす。
  本家 `--windows` も同じ）
- ~~**`drop_features` は参照されなくなった Lookup を残す**~~ **解決**
  （`prune_orphan_lookups`）。FeatureList から到達可能性を辿り、文脈
  依存 Lookup が呼ぶ先も再帰的に追って、届かない Lookup を捨てて索引を
  張り替える。JP Regular の実測で **GPOS 46,320 → 9,922 bytes**
  （−79%）、GSUB 35,102 → 34,582、ファイル全体で 1 面あたり 36,916
  bytes 減（30 面で約 1.1 MB）。いずれもこの改修単体の差で、出荷される
  面の値ではない: 後の `anchor_loose_letters` が 1 面あたり約 12 KB の
  ベースアンカーを足すので、JP Regular の GPOS は実測 21,984
  （9,922 + 12,062）に戻っている。`golden.py` で改修前後を突き合わせ、
  cmap・送り幅・シェーピング 665 通り・アウトライン 16,831 グリフ・
  メタデータがすべて一致することを確認済み。JSTF を持つフォントは同じ
  LookupList を索引するので触らない。
- **リリースの faces ジョブは欧文の静的面を 2 回ずつ作っている**
  （base と Term が同じドナーを使うため、10 面ぶんを 20 回）。**直さない。**
  6 つの faces ジョブは matrix で**並列**に走るので、この重複は壁時計
  時間を 1 秒も使っていない（CI のログで `build_latin.py` は 1 ジョブ
  7〜8 秒）。欧文を別ジョブに切り出すと artifact のアップロード /
  ダウンロードの往復が直列に入り、かえって遅くなる。消費するのは CPU
  分だけなので、測定値を添えて閉じる。
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
  `<Family> Nerd Font Mono` / `<PSFamily>NFM`。v5.0.0 で font-patcher と
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
  （引き伸ばす群——区切りと進捗バー——を除いた 10,372 字中）が本家パッチ
  より最大 1.43 倍小さい。font-patcher 独自の
  縦パディングが効く群（重い山括弧 U+276C〜2771 など）では最大 2.1 倍。アイコンごとに
  収め直すと、複数のアイコンを同じ倍率で束ねる font-patcher の
  ScaleGroups が崩れる（束の中の小さいアイコンが 3.1 倍に膨らむ）ので、
  正確に合わせるには本家の群テーブルを移植するしかなく、それは
  `nerdpatch.py` が避けている複雑さそのもの。現状は「ターミナルに
  `Symbols Nerd Font Mono` をフォールバックとして足したときと同じ相対
  寸法」で、セルからはみ出す側には決して倒れない。**据え置き。**
  「実測インクの最大値から一様倍率を引き直せば少し大きくできる」という
  案を検討したが、本家 v3.4.0 の 10,410 字を測ったところインク幅の
  中央値も 95 パーセンタイルも **2048 ちょうど**——つまりアイコンは
  デザイン正方形をきっちり埋めて描かれており、600/2048 はその正方形を
  セルに正確に写す倍率で、一様倍率のまま取り戻せる余白は無い
  （最大の 2252 は継ぎ目なく並べるための意図的なはみ出し）。
- **縦組みで位置がずれるのは、GPOS を持たない下付き記号だけ**（実測で
  記述を訂正）。以前ここには「NFD の `ḱ` は `k` の次のセルに落ちる」と
  書いてあったが、182 の「ベース＋結合文字」組を両方向でシェーピングして
  測ったところ、そうなっていない。`import_scp_marks`（ラウンド 38〜41）が
  ドナーの mark アンカーを移した副作用で、縦組みも直っていた。内訳は
  ccmp/liga で 1 グリフに合成されるもの 64 組、**縦組みでも横組みと同じ
  位置に付くもの 95 組**、**ずれるもの 23 組**。ずれる 23 組はすべて
  `U+0327` セディーユ・`U+0328` オゴネク・`U+0335` ストロークという
  GPOS で位置指定されていない下付き・重ね打ちの記号で、ずれ量は一律
  x −300・y −1000——アウトラインを 1 セル左に寄せる横組み専用の細工が
  縦組みでそのまま効き、さらに縦の原点補正が乗るため。Source Code Pro は
  これらを GPOS で置いていないので移せるものがなく、直すにはアンカーを
  新規に設計することになり、**今正しく出ている横組みの位置も動く**。
  実害（ターミナルに縦組みは無い）と釣り合わないので据え置き。
  一方、**送り幅 0 のグリフが縦の送り幅 1000 を持っていた**のは確実な
  誤りで、こちらが接ぎ木した 109 字は 0 に直した（`append_glyph`）。
  Source Han Sans 自身の 13 字は上流が 1000 を付けており、縦組みの
  日本語で実際に使われる字なので触っていない。
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
  中央配置し、収まらない字（Regular Italic で 42 字）だけ左右 8u まで詰める。結果、直立・斜体
  とも 234 字で一致し、ファミリー全体の cmap の差は 249 字から 16 字に
  減った（残る 16 字はギリシャ拡張で、Source Code Pro Italic が元から
  持たないもの。この 16 字も後述のとおり同じブロック指定で埋めたので、
  **現在の cmap の差は 0**）。直立面が持たない 10 字を Source Sans は持つが、
  斜体だけ広いのは逆向きの不整合なので入れていない。
  **アクセントの位置指定もドナーから取り込んだ**（`import_donor_base_anchors`）。
  字形だけ持ってきた段階では、斜体面のギリシャ・キリルに付くアクセントが
  全部 `x_offset 0`——改名前から続いていた穴で、旧斜体（Source Han Sans の
  115 字）でも同じだった。face 側の mark ルックアップに、ドナーのベース
  アンカーを `cell_fit` と同じ変換をかけて足す。マークのアンカーは
  マーク側の点、ベースのアンカーはベース側の点なので、両者を混ぜるのは
  妥協ではなく mark attachment の定義そのもの。ルックアップの対応は
  位置ではなく**カバーしているマークの符号位置**で取り、同点なら対応なし
  として拒否する。実測: 107 個のベースアンカーが入り、`а́` の x_offset が
  0 → −597、`И́` が 0 → −574、`ε̈` が 0 → −567（直立面は −580 / −596 /
  −564）。JP 面にも既存の `import_scp_marks` 経由で自動的に伝播し、可変
  フォントも全ウェイトで付く。ベースのカバー範囲は斜体 78 字・直立 64 字
  （共通 43）で、どちらか一方にしか無い字はドナー 2 つの設計差
  （`п` `д` `л` は Source Sans がベースとして持たない）。
  Source Han Sans のギリシャ・キリル 115 字は Source Code Pro の 234 字に
  完全に含まれるため、この変更後は 1 字も使われない（`narrow_letters` は
  上流が変わったときの保険として残置、`letters=0` がそれを示す）。
- ~~**JP 面の `usWinDescent` 288 は欧文レイヤーの罫線より浅い**~~
  **解決**（`build.WIN_METRICS = (1160, 454)`、`verify.py` が全 JP 面で
  門番）。Source Code Pro 由来の罫線素片は −400、ブロック要素は −454 まで
  伸びるので、288 では cmap 上の 111 字が宣言値の外にあった
  （`USE_TYPO_METRICS` を読む DirectWrite / CoreText / HarfBuzz は 1257u の
  行を使うので影響せず、GDI 系だけ下端が切れうる状態）。454 まで下げて
  罫線とブロック要素を覆い、GDI の行は 1448 → 1614u（+11%）。欧文
  ファミリーが同じインクに対して declare している値（`build_latin.LATIN_WIN_METRICS`
  の 1060 / 454）と揃えた。454 の外に残るのは U+3031 / U+3032
  （縦書きの繰り返し記号、−549）の 2 字だけ。この面のインクは 1808 /
  −1048 まであり、bbox を全部覆うと GDI の行が 2856u（typo の 2.3 倍）に
  なるため上は Source Han Sans の宣言値 1160 のままにした（Source Han Sans
  自身も 288 のまま −1048 のグリフを抱えている）
- ~~**上流アセットのハッシュ検証が無い**~~ **解決**。`fetch-upstreams` は
  5 つの zip（SHS / SCP / Source Sans 3 / Monaspace / Nerd Fonts）を取り、
  それぞれ `*_SHA` ピンと sha256 を突き合わせてから展開する。キャッシュ
  キーもタグ 6 個とハッシュ 5 個の全 11 ピンから作る（ハッシュだけだと
  手で上げたタグがキャッシュヒットで検証ごと素通りする）。
  `scripts/bump_pins.py` がタグとハッシュを一緒に書き換え、タグが動いて
  いないのに資産が差し替わっていたら書き換えずに落とす——ピンが守って
  いるものをそのまま洗浄してしまうため。手順は CONTRIBUTING.md
- ~~**結合アクセントが次の文字の上に乗る**~~ **解決**
  （`build.anchor_loose_letters`）。このドナーの結合文字はスペーシング設計
  ——Source Code Pro のアキュートは送りが 1 セルあり、墨はその中にある——
  で、シェーパーはマークの送りをゼロにする。したがってフォントが**置けない**
  マークは「だいたいの位置」に落ちるのではなく、**まるごと 1 セル右、次の
  文字の上**に落ちる。Source Code Pro はギリシャ・キリル 234 字のうち
  64 字、Source Sans は 82 字にしかベースアンカーを持たず、どちらも
  他方の上位集合ではない。ラテンも同様。結合文字 8 種 × ラテン・ギリシャ・
  キリルの全文字＝ 1 面 3,893 組で実測すると、**5 組に 4 組**がセル外だった
  （直立・斜体とも）。JP 面では出ない——接ぎ木がマークを 1 セル左に描き直す
  ので、置けないマークが結果的に正しい位置に落ちていた。
  対策は、各 mark ルックアップが**自分の持つアンカーから従っている規則**
  （墨のどちらの縁を追うか、そこからの中央値オフセット）を当てはめ、
  覆われていない文字にその規則でアンカーを与える。ドナーが実際に描いた
  アンカーに対する当てはめ精度は y が中央値 4〜6 ユニット・x が 11〜15、
  裾は設計者が意図的にずらした字で 200 程度。これが 600 ユニットの誤りと
  引き換えになる。規則に従わないルックアップ、ベースが少なすぎて当てはめ
  られないルックアップ（SCP に 3 つ、ベース 1〜4 個）は当て推量せずに
  そのままにする。欧文 1 面あたり 2,778〜2,811 アンカー、12 KB。
  **検証も作り直した。** 元の検査は 27 文字 × 数マークのプローブで、面の
  7 つの mark ルックアップのうち 1 つしか触れておらず、VF がアンカー
  502 個（静的面は 3,313）で出荷されていた一巡を見逃した。いまは
  `verifylib` の 3 ゲートで、どれもサンプルを取らない:
  `check_anchor_placement`（全ベースアンカーが自分のグリフの墨の上に
  ある——構造）、`check_anchor_coverage`（規則に従う全ルックアップで
  cmap 上の全文字がベース——`anchor_loose_letters` の不変条件の読み返し）、
  `check_marks_attach`（ルックアップごとに全ベース × 先頭マークと先頭
  ベース × 全マークを実際にシェイプし、`x_offset == base.x − mark.x −
  送り`・`y_offset == base.y − mark.y`・`x_advance == 0` を**閾値でなく
  等式**で照合。送りを含めるのは、GDEF がマークと言わないグリフも
  シェーパーは MarkCoverage にあれば置くが送りは消さないため）。
  VF は既定・両端・名前付きインスタンスの 6 ロケーションで instantiate
  して同じ 3 ゲートを通す。取ってある 10 種の変異体（全アンカー
  x:=150、y:=1000、プローブ外の字だけ x:=0、ベースの少ないルックアップ
  だけ遠くへ、など）は全部いずれかのゲートに落ちる。
  **round 7 でさらに作り直した。** この 3 ゲートを通る破損面が 12 種
  作れた（NULL アンカー、規則の下限を割るまで削ったカバレッジ、
  カバレッジから外したマーク、`.cap` 異体の脱落、マーク側アンカーの
  移動、全アンカーの一様なずれ、mkmk の移動と欠落、mark を持たない
  言語システム、別 feature の下に置いた mark ルックアップ、誤った字への
  ccmp 合成、プローブしていないマスターだけに効く VF デルタ）。いまの
  `verifylib.check_marks` は 8 ゲート: feature と GDEF クラス、
  ルックアップ**型**で歩いた上での feature 到達性、言語システムの
  parity、全アンカーの構造（ベース・マーク・Mark2、規則自体の帯、
  マークのアンカーはルックアップが付ける側の墨の縁から一定距離）、マーク主導の
  カバレッジ（全マークが全文字と GSUB 異体に届く。疎な 3 マーク
  U+031A/031B/0334 は名指しで除外）、GPOS から読んだ**ラン模型**に
  対するシェーパーの等式（合成は NFC の字へ、置換は置換先のアンカーで、
  飛ばす組は無い）、mkmk の等式、アセンダー字をアクセントが貫通しない
  こと。VF は変異ストアの領域ピーク（マスター 364.75 / 381.15）も
  instantiate する。変異体 32 種は全部落ちる。作り直しの最中に自分の
  バグも捕まえた: マーク補完の 2 つ目の挿入で古いレコード一覧と新しい
  カバレッジを zip して 1 つずれ、斜体のキャロンが `.cap` 用アンカーを
  受け取って `b` のアセンダーを貫通した——JP 側にだけあった貫通プローブ
  が捕捉し、Latin 側にも移した（縁からの距離のゲートはこれを構造で捕まえる）。
  **round 8 で再攻撃を受けてさらに直した。** 模型はシェーパーと同じく
  **後の**ルックアップを勝たせ、mkmk の MarkAttachmentType フィルタも
  読む。等式ゲートの根本の弱点——期待値をアンカー表から作るので、
  1 文字だけ帯の内側（350u）でずれたアンカー・第 2 クラスのアンカー・
  マークの輪郭だけ 200u 動かす、を見抜けない——には、**アンカーと独立な
  期待値**を足した: 全文字 × 各ルックアップ 2 マーク・全マーク × 3 文字
  をシェイプし、マークの墨が字の墨の縁から `_SEAT_DY`（上 −150〜+180、
  下 −200〜+200）・中心から `_SEAT_DX`（330）の内側にあり、ルックアップ
  ごとの中央値も `_SEAT_MEDIAN_*` に収まること（実測 p1〜p99: 上 23〜93、
  横 −137〜202、中央値 −73〜114）。ほかに、全クラスのベースアンカー、
  mark feature が届くのは型 1/4/6 のみで型 5 は無いこと、大文字の後の
  アクセントが持ち上げ形であること、タイバーが 2 字にまたがること、
  ASCII の英数字がそれぞれ墨のあるグリフを持ち `.notdef` が描くこと、
  VF に HVAR/VVAR/MVAR が無いこと。帯の定数は 1u 内外のテストで
  釘付けにした（それまでは 6 定数中 5 つを 10 倍にしても通った）。
  round 8 の変異体 13 種と過去の 32 種は全部落ちる
  **round 9 で verifier 自体をまた変異攻撃した**（42 種、うち 30 種が
  素通り）。見えていなかったのは「1 グリフ」単位の性質——送り幅は
  セルの整数倍なら何でも通り（`e` を 2 セルにしても）、字形の位置は
  平均でしか見ず（1 字を 250u 横・200u 上に動かしても）、GPOS の
  SinglePos で送りを足しても、合成済み文字になる組（E I N O U a e … と
  ギリシャ母音）はマークを一度も測らず、大文字が持ち上げない面は
  「持ち上げない面」として検査を飛ばし、縦組みの送りと原点、
  `vert`/`fwid` の写し先、Term の広げ忘れも見ていなかった。足したもの:
  `check_cells`（cmap の全文字の送りが East Asian Width どおりで、
  シェイプしても同じ送りであること；英数字と半角カナは中心 ±120・
  数字と大文字はベースライン −20〜+10、漢字・かなは全角ボックス
  −130〜890、全角グリフはセル ±12、送り 0 のマークは前のセル）、
  seat ゲートは合成する組を別のマークで測り直して全文字を見、
  各字は同じ種類（カテゴリ×マーク×全角か）の中央値 ±60 に収まること
  （ホーンやフックや下降部を縁に持つ ơ ư ɠ η ɥ ɻ ɕ ʇ ɖ y … は除く）、
  積み重ねは 2 つ目のマークの横ずれを「単独で座る位置」との差で ±80、
  大文字が持ち上げない面は FAIL、i/j はアクセントの下で点を落とすこと、
  タイバー以外の墨のはみ出しは 230u まで（最大の斜体の傾き 224）、
  JP: 縦組みの送りは全部 1 em（〱〲は 2 em）でかな・漢字は VORG を
  動かさないこと、`fwid` は U+FF01〜、`vert` は Unicode の縦書き用形
  （U+FE10〜、FE30〜）のグリフを返すこと、濁点・半濁点は全部の半角カナで
  同じ場所（ｶ の後と等しい）かつ高さ 620〜940、Term 面は隣に建った
  JP 面の全角グリフを 100u ずらした（縁に接するものは伸ばした）もの
  であること。
  **round 10 でさらに 57 種を当て、45 種が素通りした**。読んでいなかったのは
  FontMatrix（fontTools は無視するが FreeType は 70% で描く）、符号位置の
  無い合字グリフの位置と高さ、既定で効く GSUB/GPOS の中身（`rn`→`m`、
  `ccmp` の下の PairPos、`0`→`O`）、GDEF で字をマークに分類すると送りが
  0 になること、欧文面の行メトリクス、縦組みの送り・原点・vert の写し先、
  `.notdef` の空白化と空白の墨、name 4/6 の組み立て、家族内の cmap の
  食い違い。足したもの: `check_font_matrix`（top と全 FD が 1/1000）、
  `check_line_metrics`（全面 984/−273/0）、`check_gdef_classes`（送りの
  ある文字はマークでない）、`check_pair_positioning`（PairPos は `vkrn`
  だけ）、`check_substitution_identity`（既定で効く置換は入力と出力が
  NFKD で同じ文字。例外は i/j → ı/ȷ と 〳〵 → 〱 の 2 組だけ）、
  `check_ligature_cells`（合字の墨はセル ±40、高さは構成文字の −70〜+120）、
  `check_blank_glyphs`（`.notdef` は箱を描き、空白と既定無視文字は
  描かない。ソフトハイフンは SCP の設計で描く）、`check_name_composition`、
  `check_family_cmap`（同じ家族の隣の面と同じ文字集合）、JP の
  `check_vertical_layout`（全角文字は縦組みで 1 em 送り、x は −半角、y は
  自分の VORG、既定 VORG 880。〱〲と注音は SHS 独自の縦メトリクスなので
  除く）、NFM 面は `NF_SYMBOLS` 必須（ドナー無しの余裕 1/10 セルで
  区切りが 50u 短くても通った）。**残る盲点**（据え置き）: 1 字だけアンカーを横に 250u
  動かす（絶対帯 330 の内側。種類ごとの横中央値や重なり率も試したが、
  F の下のセディラ・A の足のオゴネク・Light の l の上の広いマークなど
  設計上の例外表が要るので採らない）、cmap の付け替え（が→か、b↔d）と
  輪郭の鏡映——参照するドナーが verifier に無い。round 10 の残り: 外接箱を
  保つ輪郭の破壊（`o` のカウンター落とし、0.8 倍、Bold 面に Light の `e`）、
  cmap の付け替え（é → e、IVS）、Term の記号の広げ忘れ（かな・漢字以外は
  伸ばす・引き伸ばす・詰め直すの 3 通りがあり、モデル化しない）、
  `vert` の対象の欠け（っ）、半角ﾞの横ずれ（設計上セルの左上）。
  ドナーとの輪郭比較（XOR 面積）を足せば大半が閉じるが、ビルドの変換を
  verifier にもう一度書くことになるので採らない
  **round 11 でさらに攻撃した**（GPOS の残りの型、guard の連鎖、マークの
  フィルタ、置換の 4 型、VORG、Nerd 面の家族参照など 30 種強、うち 11 種が
  素通り）。素通りしたのは、ゲートが 1 つの表しか読まないのにシェーパーは
  全部まとめて読むという同じ形の穴だった: `ccmp` の下の SinglePos で
  数字を 180u 下げる（欧文で 3 px 下がる）、`curs` のカーシブ接続で単語が
  階段状に上がる、AlternateSubst で `l` を `1` にする、文脈なしの規則で
  すべての `i` を点無しにする、連鎖文脈で送りを足して行の残りをずらす、
  `:::` で `::` の合字が出る、マークのフィルタリングセットから acute を
  外して積み重ねを黙らせる、記号の VORG を 620 にする、Nerd 面から IPA を
  37 字落とす。足したもの: `check_run_identity`（全文字を単独と 2 字の
  組でシェイプし、自分のグリフ・自分の送り・オフセット 0 であること。
  1 面 134 字・17,595 組）、`check_ligature_guards`（`build._guard_subtables`
  が書く規則そのもの——合字は自分の演算子が続く長い連なりの中では出ない）、
  positioning surface（この面が作る GPOS の型は 1/2/4/6/8 だけ。カーシブ 3、
  マーク対合字 5、文脈 7 は作らない）、マークのフィルタリングセットも
  「自分のマークを見られること」の対象に、積み重ねは横ずれだけでなく
  上下の隙間も（中央値 −130〜10、各組 −200〜160。実測 −142〜86）、
  置換の同一性は 4 型すべて（ウクライナ語の `ї` を点無し i に分解するのは
  ドナーの設計として名指し）、JP は VORG を**ドナーと突き合わせ**
  （全角で描く 15,778 字。`SHS_DIR` 必須）、家族 cmap の参照は自分の
  ファミリーの Regular（`GengouNFM-Regular.otf`）。
- ~~**静的面に Source Code Pro の重なった輪郭が残る**~~ **解決**
  （`build_latin.round_outlines` が `draw_clean` を通す）。VF のマスターは
  補間のために重なりを残し、Adobe の静的版は除去しているが、当方の静的面は
  インスタンス化したまま出していた: 直立 300 字・斜体 247 字（A K Q R e f
  k、キリルの њ љ）で、FreeType は継ぎ目を濃く描く（14px の њ で幅 11px に
  Δ121）。JP 面は接ぎ木時に `draw_clean` で描き直すので元から 0
- ~~**斜体で U+0310（candrabindu）が次の文字に飛ぶ**~~ **解決**
  （`build.anchor_loose_marks`）。Source Code Pro Italic は直立が持つ
  above ルックアップから U+0310 とその `.cap` 形だけを外している。
  `anchor_loose_letters` のマーク側: ルックアップ内で同じ高さに描かれた
  マークは同じアンカーを持つので、墨の中心が近いマークの中央値を与える
  （斜体 1 面あたり 2 マーク）。2 重ダイアクリティカル（U+035C〜0362）は
  2 文字にまたがる設計なので置かない
- ~~**斜体で 2 つ目のアクセントが 1 つ目の上に潰れる**~~ **解決**
  （`build.mirror_stack_lift`）。SCP Italic の grave・acute・breve・ring は
  Mark2 アンカーが自分の Mark1 の高さと同じで（全ウェイト）、`x̀́` を
  重ねて描く。直立は 2 つ目を Light 30・Regular 111・Bold 248 持ち上げ、
  wght 200 のマスターだけ持ち上げない。斜体は同じ wght の直立の持ち上げ
  量をそのまま写す（静的 5 面各 4 アンカー、VF マスター 381/400/700 で 4、
  200 で 0）
- ~~**GSUB で置換された字にアンカーが無い**~~ **解決**。シェーパーは
  GSUB のあとに GPOS を当てるので、`locl` のセルビア語 `б` に付く
  アクセントは置換先に付く——その `б` はどの BaseCoverage にも無く、
  `sr` では `б́` のアクセントが次のセルに飛んでいた。`anchor_loose_letters`
  が `locl` / `salt` / `case` / `cvNN` / `ssNN` の単純置換先（2 段まで）も
  文字として扱う（`vert` / `sups` は別の場所に描く別のグリフなので
  対象外）。直立 1 面 3,051 アンカー、斜体 2,911
- ~~**大文字の後のアクセントが持ち上がらない**~~ **解決**
  （`anchors.raise_marks_after_capitals`、round 8）。Source Code Pro の
  `ccmp` は大文字の後で上付きアクセントを `.cap` 形（34〜47u 上）に
  置き換えるが、その「大文字」の連鎖文脈にはラテン（斜体）またはラテン＋
  キリル（直立）しか無く、斜体の `А́`・`Ґ̀` は小文字用の形が大文字の
  79〜96u 上に乗って Bold では行の高さ（1060）を超え、直立でも `Ɗ` `ẞ`
  `Ḑ` などが外れていた（斜体 267 大文字中 107、直立 8）。Source Sans 3
  Italic 自身はギリシャ・キリルの大文字でも置き換える。全面で、対象範囲の
  cmap 上の大文字を全部その文脈に足す（直立 8 字、斜体 116 字）。
  ギリシャの大文字は上流の設計どおり別扱い——直立ではその後のアクセントが
  `locl` でトノス形になり（持ち上げ形は無い）、斜体は下の「Source Sans の
  `locl` を受け継いでいない」のとおりラテンのアクセントが乗るので、ラテンの
  大文字と同じく持ち上げる（round 9 で露見。それまでのゲートは、斜体が
  ギリシャ大文字の後だけ持ち上げなかった偶然で通っていた）
- ~~**数字・約物の後の結合マークが隣のセルに落ちる（JP 面では数字を貫く）**~~
  **解決**（round 10、`anchors.accent_bases`）。Source Code Pro は字にしか
  アンカーを持たず、`0` + U+0301 は欧文面で右隣のセル（墨 836〜1036）、
  JP 面では接ぎ木の −600 でセル内に来るが小文字の高さのままなので
  `0` の頭を貫いた（共有 5,008 平方 u、Bold の `!` + U+0300 は 13,921）。
  約物を描いている Monaspace 自身は数字・約物にもアンカーを持つ。
  `anchor_loose_letters` の対象を ASCII・Latin-1 の数字・約物・記号
  （カテゴリ N/P/S、U+0021〜00FF）に広げ、fitted rule で墨の上下に置く
  （`0́` は 731〜940、`.́` は 239〜448、`(́` は 872〜1081）。欧文 1 面
  3,375 アンカー。coverage ゲートも同じ集合を見る
- ~~**JP 面で `A` + U+02EA（注音の声調記号）が A の肩に付き、セルは空く**~~
  **解決**（round 9）。round 8 の `anchor_loose_letters` は `mark` の下の
  全ルックアップを字に合わせて埋めたが、Source Han Sans 自身の声調記号
  ルックアップ 2 本（注音の音節の**横**に置く設計）もその「規則」に通り、
  ラテン・ギリシャ・キリルの 807 字ずつが底に加わった（1 面 2,194 の
  「はぐれアンカー」のうち 1,898 がこれ）。U+0300/0301 などは後の SCP の
  ルックアップが上書きするので見えなかったが、声調記号だけが持つ
  U+02EA/02EB は A に付き（x −160, y 648）、600 の送りは残るので重なった上に
  1 セル空く。`anchors._mark_base_lookups(on_letter=True)` が注音の底を
  持つルックアップを外し、verifier は `check_tone_lookups` で声調
  ルックアップに字が無いことを見る（round 8 の面で FAIL、修正後 ok）。
  はぐれアンカーは 1 面 296
- ~~**JP 面で言語タグ `ja` の下ではギリシャの `locl` が届かない**~~
  **解決**（round 9）。`_add_feature_where` はドナーが名指す (script,
  language) だけを配線し、Source Han Sans が全スクリプトに持つ `JAN ` の
  LangSys は自分の `locl` のまま残った。LangSys は完結していて既定から
  継承しないので、ja ロケールのエディタが渡す言語タグでは `β` + U+0301 が
  トノスでなくラテンのアクセント（cid23853）になった（`el`/`en`/無指定は
  トノス）。ドナーが名指さない言語には script の既定リストを与える
  （シェーパーがドナーに無い言語にするのと同じ）。あわせて入れ替えで
  孤立した FeatureRecord を `prune_orphan_features` が落とし、
  `prune_orphan_lookups` は LangSys から辿る
- ~~**JP 面の全角ラテン（`fwid`）に付くアクセントがセルの右端に落ちる**~~
  **解決**。`add_width_alternates` が `x` → 全角 `ｘ` に写す先の Source Han
  Sans のグリフはどの BaseCoverage にも無く、`fwid` を効かせた `x́` の
  アクセントは 1000 セルの右端（墨 636〜836）に置かれていた。JP 面でも
  `anchor_loose_letters` を走らせる（幅の別形と全角化のあと、墨が
  確定してから）: `fwid` の写像先と、ドナーに無い Source Han Sans 自身の
  ラテン文字に、1 面あたり 1,686〜1,750 アンカー
- ~~**斜体にギリシャ拡張が無く、JP 面では豆腐が全角になる**~~ **解決**
  （`SANS_BLOCKS` にギリシャ拡張を追加、`build.notdef_to_cell`）。
  Source Code Pro は直立がこのブロックの 16 字（コロニス・プシリ・ダシア・
  ペリスポメニのスペーシング形）を描き、斜体は 1 字も描かない。そのため
  斜体面は、自分の直立が持っている字で `.notdef` に落ちていた（10 字）。
  さらに `.notdef` 自体が Source Han Sans のまま全角で、JP 面 1000 /
  Term 1200。ターミナルは East Asian Width で桁を決めるので、**フォール
  バック連鎖のどれにも無い符号位置を 1 つ打つだけで行がずれる**。
  欧文ドナーの `.notdef`（このセル用に描かれている）を全面で使うようにし、
  グリッド処理の前にピン留めしてファミリーのステップ表と Term の拡幅の
  どちらも触れないようにした。実測: Term で未収録符号位置の送りが
  1200 → 600。逆向きの誤り（桁より狭い箱）は白が空くだけで何も動かない
- **網掛け `░ ▒ ▓` は縦に敷き詰めると行の境目に濃い帯が出る**。ブロック要素は
  行より高く描かれている（`█` は −400..1000 の 1400、`▓` は 1435、`▒` 1390、
  `░` 1360）のに、この書体の行送りは 1257。差の分（`▓` で 178）が上下の行で
  二重に描かれる。実測: 同じセルを 1 行分ずらして重ねた墨の交差面積は
  `▓` 51,765 平方ユニット（そのセルの墨の 8.3%）、`▒` 11,313（4.1%）、
  `░` 1,359（1.1%）。網点のピッチは 200 で、横は 600/200 = 3 で割り切れるため
  **左右は完全に敷き詰まる**（隣接セルとの重なり 0）が、縦は
  1257/200 = 6.285 で割り切れない。FreeType で 200px/em にラスタライズすると、
  行境の約 20px 帯で墨の被覆率が 0.733〜0.765 に達し、模様自身のピーク 0.538 を
  40% 上回る。Midnight Commander の背景や htop のメーターなど、TUI の網掛けで出る。
  **据え置き（上流の設計判断）。** グリフは Source Code Pro と 1 バイト違わず、
  上流自身の行送りも 1257 なので上流でも同じことが起きる。これは上流が
  **隙間が空くより重なるほうを選んだ**結果で、この build 自身が罫線に対して
  採っている方針（`extend_edges`: 継ぎ目に白が出るくらいなら伸ばす）と同じ。
  直すなら `TILING_STRETCH` と同じ語彙で縦にも伸縮できるが、網点が正方形で
  なくなるうえ、上流が意識して選んだ取引を書き換えることになる
- **結合文字を 2 つ重ねると上下が重なる**。ギリシャの気息記号＋アクセント
  （`ῤ́` `ἂ` `ἦ`）で、斜体は 2 つのマークを約 6,000 平方ユニット重ねて描く
  （直立は合成して 1 グリフにする）。ただしこれは斜体固有ではなく、
  **上流の限界**: `mkmk` の Mark2 カバレッジが 12 字しかないため、基底 16 字
  × マーク 8 種の 2 重掛け 413 組のうち **Source Code Pro Upright 自身が
  370 組を重ねて描く**（当方の直立は 395 組、斜体は 406 組——増分は、これまで
  1 セル右へ飛んでいたマークがセル内に来て「次の文字」ではなく「前のマーク」
  と重なるようになった分で、描画としては改善）。Source Sans 3 Italic は
  246 組中 120 組と半分ほど。**据え置き。** 直すには mkmk アンカーの合成が
  要り、多声調ギリシャ語や 2 重ダイアクリティカルはターミナルの用途から遠い。
  （斜体の grave・acute・breve・ring が**完全に**潰れていた件は別で、上の
  `mirror_stack_lift` で直立と同じ持ち上げにした）
- **多声調ギリシャ語の分解形は豆腐になる**。U+0314（気息記号 rough）と
  U+0335（短い横棒オーバーレイ）を含む U+0300〜036F の 59 字は Source Code
  Pro が持たず、`ἡ` の NFD（η + U+0314）は η と `.notdef`（1 セル）に
  なる。Greek Extended の合成済み形も 233 字中 217 字が無い。**据え置き**
  （上流の字形セット。1 セルの `.notdef` なので桁はずれない）
- **東アジア文字幅 Neutral で 1 セルにした記号のうち `☑`（墨 731）と `❤`
  （742）は隣のセルに 100u 前後はみ出す**。Bold 14px で `a☑` の墨が 5px
  重なる。**据え置き**（Source Code Pro の設計幅。縮小は v5 で廃止した
  方針と同じ理由で採らない）
- **VF の名前付きインスタンスは静的面と最大 11u ずれる**（SemiBold Italic
  の `ψ`、Medium 直立の `ʷ` 4.2u、Bold 直立の `Ώ` 4.9u。Regular は 0）。
  `=` のバーとステム幅は一致するので太さではなく形のずれで、Source Sans /
  Source Code Pro 自身のマスター位置と当方のマスター位置（200 / 365 /
  400 / 700）の間の補間の差。ターミナルのサイズではサブピクセル。
  **据え置き**
- **疎なマーク U+031A / U+031B / U+0334 は、ドナーが覆う数字以外では次の
  セルに飛ぶ**（`◌` のみ、O U o のみ、L l のみ）。規則が当てはめられない
  ルックアップは触らない方針の帰結で、verifylib の `SPARSE_MARKS` に名指し
  してある。**据え置き**（round 11 で約物の後も同じと確認: 欧文面では
  U+031A・U+031B が約物 71 字すべてで次のセル、JP 面では接ぎ木の −600 で
  セル内に来て字の墨を切る 100 組。round 10 で数字・約物にアンカーを
  与えたのはこの 3 字を覆うルックアップではないので変わらない。
  下付きのセディラ・オゴネクが約物に触れるのは字と同じ量（Bold で
  950 対 950 平方 u）で、付く設計そのもの）
- **斜体の `d` `đ` `ď` `ɗ` 系ではアセンダーの上のアクセントが次のセルへ
  はみ出す**（RegularItalic の `d̋` で 183u、BoldItalic 209u；100u 以上
  はみ出す組が斜体 1 面 86〜141）。Source Code Pro Italic 自身と同一の
  アンカー（実測で一致）。**据え置き（上流の設計）**
- **IPA の `ɥ` `ʇ` `ɠ` `ɻ` にマークが重なる**（`ɥ` + U+0324 で 2,125〜
  6,075 平方ユニット、Bold の `ɠ` に上付き 10 種）。ドナーのアンカー。
  **据え置き（上流の設計）**
- **`#(` 合字は Bold Italic で 2 セルを 20u 超える**（SemiBold Italic 6u、
  斜体 VF は wght 575 から）。Monaspace のグリフ。**据え置き**
- **JP 面の `ﬀ`（U+FB00、Source Han Sans のみ）は 1 セルに収めても墨が
  13〜645** で 45u はみ出す。`☑` と同じ類。**据え置き**
- **半角カナ + 結合濁点 U+3099 は重なる**（`ｶ` の墨 82〜486 に対し
  濁点 335〜572）。Source Han Sans 自身と同じ（スペーシングの `ﾞ` と
  合成済み形は問題ない）。**据え置き（上流の設計）**
- **斜体は Source Sans の `locl` と合成規則を受け継いでいない**。
  `import_scp_locl` は欧文ドナーの `locl` を読むが、ギリシャ・キリルは
  第二ドナー由来なので対象外。結果、セルビア語の `б` `п` `г` `д` は斜体では
  ロシア語字形のまま（Source Sans Italic 自身は 4 字とも置換する）。気息記号の
  合成も同様に届かない（Source Sans の合成先が符号位置を持たない `.g` 異体で、
  「グリフは接ぎ木しない」方針に当たる）。ギリシャのアクセントも同じで、
  Source Code Pro Italic 自身に `grek` の `locl` が無く、Source Sans の
  `locl` は `.g` 異体へ写すので、斜体の `Β` + U+0301・`β` + U+0301 には
  ラテンのアクセント（大文字の後は `.cap` 形）が乗る（NFC で合成される
  `ά` などは Source Sans の合成済み形）。**据え置き。** ただし
  2 つの検査は「斜体ドナーにギリシャ／キリルが無い」という
  **すでに偽になった理由で自分を飛ばしていた**ので、既知の穴を列挙して
  検査自体は動かすようにした（新しい穴が開けば落ちる。ギリシャの検査は
  round 9 で `verifylib.check_greek_accents` に移し、欧文面と VF にも
  かかる。列挙は `verifylib.GREEK_ITALIC_GAP`）
- **`ss11` / `cv14` / `salt` を効かせると `->` `<-` が JP 系では合字のまま、
  欧文単独ファミリーではハイフン異体＋不等号になる**（`a->b` が JP 面では
  1200 の合字、欧文面では 600×2）。桁数はどちらも変わらない。原因は
  ルックアップ順で、`import_scp_variants` が JP 面では calt の上に異体の
  単純置換を積むため合字が勝つ。24 合字中この 2 つだけ。**据え置き**
  （既定では出ない差で、直すには接ぎ木の GSUB 順序を動かすことになる）
- **JP 面に Source Han Sans の `liga`（ff/fi/fl/ffi/ffl）が死んだまま残る**。
  入力グリフ（SHS 自身の f i l）は欧文レイヤーに置き換えられて cmap から
  外れ、どの置換もそれを出力しないので発火しない。11 の FeatureRecord が
  指しているだけで描画は変わらない。`prune_orphan_lookups` は LangSys から
  辿る到達性しか見ないので残る。**据え置き**（グリフ到達性まで見る刈り込みは
  別の仕組みになる）
- **JP 面の欧文レイヤーは `dist/latin` と輪郭数が違うことがある**（直立は
  `▚` の 1 字、斜体は Source Sans 由来のギリシャ・キリル 14〜31 字で
  `dist/latin` のほうが輪郭が 1 つ多い）。外接箱は 1u 以内で一致し、
  `pathops.simplify` 後の塗り面積は完全に一致（差 0.0 平方 u）——重なった
  冗長な輪郭で、描画は同じ。**据え置き**
- **東アジア文字幅 N / A の記号のうち 1 セルに収まらないものは
  Source Han Sans の全角のまま**（JP 1 面あたり N 142 字・A 424 字。
  `⇄` `⚠` など）。ターミナルは N を 1 桁と数えるので隣のセルに 4.6 px
  ほどかかる。ドナー自身が同じ幅で描く。**据え置き（上流の設計）**——
  1 セルに収まるものは v5 で narrow 済み
- **`fwid` を効かせても 2 セル合字は 600 グリッドの幅のまま**（`=>` が
  全角行の中で 1200、Term では全角 1 セル分）。どのエディタも `fwid` を
  使わないので**据え置き**。`hwid` は 600 グリッドなので問題ない
- **`frac` を効かせると数字の横の `/` が全部分数の斜線になる**（`://` も）。
  Source Code Pro と同じ。**据え置き（上流の設計）**
- **合成アンカーは縦の宣言値をはみ出す組を増やす**。すでにアクセントを
  持つ文字にさらに結合文字を重ねると、その分だけ上に伸びる。`ĺ` + U+0344 は
  y 1284 まで達し、`usWinAscent` 1060 を 224 超える（round 11: 背の高い
  記号 1 字でも同じで、`$` + U+0300 が 1181 と 121 超える）。欧文 1 面あたり、
  セル内に収まる組のうち宣言値の外に出るものが 29 → 3,087 組（上）・
  108 → 983 組（下）。`update_bbox` / `pin_win_metrics` はアウトラインしか
  見ないので win は広がらない。**据え置き。** 積み重ねの性質上避けられず、
  宣言値を覆うところまで広げると GDI の行が伸びる（それ自体が別の記録済み
  項目）。置かずに 1 セル右へ飛ばすほうが悪い
- **斜体で `ss14` / `cv04` のセリフ付き `l` が効かない**。`1` との判別用の
  異体字で、直立では 29 符号位置に効き、斜体では GSUB にタグ自体が無い
  （`cv07`–`cv11`・`ss12`・`ss13`・`ss15` のギリシャ・キリル異体字、
  ギリシャ・キリルの `locl` も同様に斜体で欠ける）。Source Code Pro Italic
  が出荷していないのが直接の原因だが、**Source Sans 3 Italic は `cv04` を
  持っている**（`l` → `l.a`、15 置換。`i` は対象外）。多くのエディタ配色は
  コメントやキーワードを斜体にするので、同じファイルの中で `l` の字形が
  混ざることになる。**据え置き。** 取り込むと、欧文の中核文字の異体字だけ
  別書体の字形になる——ギリシャ・キリルのときとは違い、SCP Italic は `l`
  を持っている（欠けているのは異体字だけ）ので、「無い」を「不揃い」に
  替える取引になる。異体字を持たないことのほうが一貫している
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

NF 版のファミリー名は nameID 16（と nameID 4）の綴り。nameID 1 は
GDI の 31 文字に収めるため `Gengou JP NFM` / `Gengou JP Term NFM` /
`Gengou NFM` に略してある（上の GDI の項）ので、旧 conhost・メモ帳・
Office のピッカーには略称のほうが出る。

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
  4 つの上流を合わせる合成の合でもある。どちらもこの書体の固有の特徴を
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
- SCP 由来: `zero` `salt` `cv01`〜`cv17`（cv03 / cv05 / cv13 は SCP 自身に無い）
  `ss11`〜`ss17`（+10 マウントは JP との整合のため維持）。SCP の `case`
  `ccmp` `locl` `frac` `numr` `dnom` `onum` `ordn` `sinf` `subs` `sups` も
  そのまま通す
- GPOS は SCP 自身のもの（結合文字の `mark` / `mkmk`、`ccmp`、`frac`、`size`）を保持。`kern` は無い（等幅）。
  Term 面では全角化で動いた字に付くマークの位置を横組み専用の `dist` で補正する

> **注記（v5）**: 以下 3.3・3.4 と 5 節は v4 までの設計の記録で、
> 数値は当時のもの（4 節は v5 の構成に書き直してある）。5 節が挙げる
> マスター数・ウェイト数・面数と SHCJ への言及は現行の実装とは一致しない
> ——現行の値は 1・3.1・3.2・4 節と README を見ること。v5 で基準を
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
scripts/build_latin.py     # SCP VF + Monaspace VF + SS3 VF Italic
                            #   -> dist/latin/Gengou-*.otf（JP 面のドナー・
                            #      NF パッチの入力・VF の検証に使う 10 面。
                            #      単体では配布しない）
scripts/build_latin_vf.py  # 同じマスターを varLib で合成
                            #   -> dist/latin/Gengou[wght].otf
                            #      dist/latin/Gengou-Italic[wght].otf
scripts/build.py           # SHS + dist/latin
                            #   -> dist/GengouJP*.otf（JP / JP Term の 20 面）
scripts/nerdpatch.py       # Nerd Fonts の記号フォントを接ぎ木
                            #   -> dist/nerd{,/latin}/*NFM-*.otf
scripts/verify.py          # JP 面の回帰テスト
scripts/verify_latin.py    # 欧文静的面の回帰テスト
scripts/verify_latin_vf.py # 可変フォントの回帰テスト
scripts/verify_many.py     # 上の静的面 2 つ（verify.py / verify_latin.py）に
                            #   glob で振り分けてまとめて走らせる。可変
                            #   フォントは落とす（verify_latin_vf.py は別掛け）
scripts/golden.py          # 2つの dist ディレクトリを比較（cmap・送り幅・
                            #   シェーピング・アウトライン・メタデータ・ヒント）
```

`build.py` は SCP VF・Monaspace VF に直接触れなくなり、`scripts/build_latin.py`
が先に走って `dist/latin` を作っていることを前提にする（`LATIN_DIR`
環境変数、既定 `dist/latin`）。Source Han Sans CJK（SHCJ）は v5 で上流から
外れたので、このパイプラインには出てこない。VF のインスタンス化・
太さ二分探索・Monaspace の合字/記号の合成（`VFSource.matched`、
`erode_path`、`replace_from_mona`、`add_glyphs`）は `scripts/vfsource.py`
に、欧文レイヤーがドナーの GPOS に足すアンカー（`anchor_loose_letters` /
`anchor_loose_marks` / `import_donor_base_anchors` / `mirror_stack_lift` /
`classify_unicode_marks`）は `scripts/anchors.py` にある——どちらも JP
ビルドが到達しない関数群で、round 7 で `build.py` から純粋移動した
（39 定義 1,164 行。接ぎ木後の bbox 更新 `update_bbox_after` は
`nerdpatch.py` だけが使うのでそちらへ）。両ファイルとも `build.py` の
共通ヘルパー（`draw_clean`、`append_glyph`、`add_gsub` /
`_guard_subtables`、`latin_blue_zones` / `add_latin_fd`、`autohint_face`、
`subroutinize_face` など）を import して使う。`build.py` 側は同じ関数群を、
VF インスタンスではなく `dist/latin` の完成品 OTF（`graft_halfwidth`,
`import_scp_variants`, `latin_ligatures` 等が受け取る）に対して呼び出す
だけになった。

round 9 で 3 つの仕組みを 1 つずつにまとめた（出力はバイト同一）:
ドナーのルックアップを写す 3 つの取り込み（`import_scp_locl` /
`import_scp_ccmp` / `import_scp_marks`）がそれぞれ持っていた「生き残る
集合を固定 → 番号を振る → 深いコピーを書き換えて先頭か末尾に挿す」は
`copy_lookups`（remap 関数と前後だけ渡す）1 つに、ドナーの輪郭を
新しいグリフに描く 8 箇所（`graft_halfwidth`・`import_scp_variants`・
`graft_scp_outputs`・`latin_ligatures`・`build_latin` の 2 箇所・
`vfsource.add_glyphs`）の pen → `draw_clean` → `alloc_glyph_name` →
`append_glyph` は `graft_outline` 1 つに、`VFSource` がインスタンスの
TTFont に後付けしていた属性（`wght` / `master` / `erode` /
`residual_slant`）は `vfsource.Instance` 型の宣言済み属性に（読む側の
`getattr(..., default)` は消えた）。ネストしたルックアップ番号を歩く
関数も `_renumber_lookups` と `_lookup_records` の 2 つから後者だけに。
verifier では `check_one_cell` を `check_widths_by_class` に畳んだ
（Monaspace の曖昧幅記号と `.notdef` は「方針で 1 セル」の分類）。

round 10 でさらに廃止・統合したもの（いずれも出力バイト同一）: 欧文
ファミリーの win メトリクスを面ごとに測って家族で揃える仕組み
（`fit_win_metrics` / `harmonize_win_metrics` / `scripts/harmonize_latin.py`
とそのテスト、release の再検証ステップ、nerdpatch の再フィット）は、JP と
同じく定数 `build_latin.LATIN_WIN_METRICS = (1060, 454)` を書く
`pin_win_metrics` 1 つに（全ウェイトで同じ 2 グリフ U+2593 と U+E0A0 が
極値。超えたらビルドが止まる）。`=` のバーを測る 105 行の輪郭極値ソルバー
（`_contour_bounds` 以下 5 関数）は、moveTo で分けた輪郭ごとに BoundsPen を
かける 15 行の `contour_boxes` に（全ドナー 9,000 グリフで一致）。
`narrow_letters`（SHS のギリシャ・キリルを 1 セルに詰める。両ドナーが
ブロック全体を描くので全面で 0 件、verifier が「ギリシャ・キリルは
1 セル」を見る）は削除。`_pos_records` は `_lookup_records` に、
`vmtx_donor` の `fullwidth` 引数は削除（どちらのドナーも 1000 / 880）。
verify.py が verifylib と二重に持っていた検査（`is_italic`、typo == hhea、
アライメントゾーン、GDEF のクラス、ウェイト名、等幅メタデータ、
`.notdef`・半角の 1 セル、1 セルの Wide 集合）は共有版の呼び出しに
（`check_monospace_metadata` の「win がボックスを覆う」は欧文の方針で、
JP はピン留めなので引数で外す）。定義だけで呼ばれていなかった
`check_letter_glyphs` は `check_cells` から全面で走る。CI の
`lint_workflows.py` ステップはテストと重複していたので削除。

build.py に残る処理（`build_face` の順）: SHS の読み込み、Gengou からの
グリフ・GSUB・GPOS の取り込み（`graft_halfwidth` / `latin_ligatures` /
`import_scp_variants` / `import_scp_locl` / `import_scp_marks` /
`import_scp_ccmp`。グリフ名を CID に付け替え、lookup と feature を SHS の
テーブルにマージ）、`narrow_halfwidth` / `narrow_letters` と `fit_to_grid`、
`widen_fullwidth`（Term）、`stretch_arrows` と `add_width_alternates`
（`fwid`）、`notdef_to_cell`、名前・STAT・メタデータ、`drop_features` と
`prune_orphan_lookups`、`add_latin_fd` とヒント付け。NF パッチは
`nerdpatch.py` が完成面に対して別に行う。

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
  下限で単にクランプする）方針にした。SCP wght がおよそ 365（斜体 381）を下回ると
  Monaspace 側の記号・合字はその下限の太さで止まり、静的版が erosion
  で削っている太さより太くなる——Light（SCP wght ≈317）はこの範囲に
  入る。実測（wght 300 の VF 対 静的 Light）: `=` のバーが 53u 対 37u
  （直立 +43%、斜体 +56%）、`(` の墨面積 60,512 対 41,854（+45%）、
  ASCII 記号 32・矢印/不等号/省略記号 11・合字 61 の計 104 グリフが
  墨面積で直立 24〜71%（中央値 45%）、斜体 30〜84%（中央値 56%）太い。
  バーは wght 200 から 365（斜体 381）まで 53u で平らで、そこから
  400 で 62、700 で 104 と上がる。**同じインスタンスの中で**文字が
  Regular 比 56% まで軽くなるのに記号は 86〜92% に留まるのが、利用者に
  見える差の正体（静的 Light は erosion で両方を揃える）。「わずか」では
  ない。静的 Light は erosion 版のまま JP 面のドナーに使う（単体では
  配布しないので、利用者から見える差は VF 側だけ）。マスターを増やして
  この範囲もカバーする案は保留（erosion 自体が非線形なので、マスターを
  増やしても補間では再現できないことに変わりはない）
- **太さの線形性**: SHCJ の各面に対する wght の一致点は二分探索で求めている。
  SCP 側は設計座標を SCP の avar で線形化してあるので中間ウェイトでも
  厳密に一致する（実装済み、`verify_latin_vf.py` で検証）。Monaspace 側は
  4 マスターの間で線形補間になるため、名前付きインスタンスの間では
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
