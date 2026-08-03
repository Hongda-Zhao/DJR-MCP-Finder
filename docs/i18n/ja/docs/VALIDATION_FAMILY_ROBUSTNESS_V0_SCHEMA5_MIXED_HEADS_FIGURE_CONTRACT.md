<!-- i18n-mirror: non-authoritative translation; source=docs/VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_FIGURE_CONTRACT.md -->

> **翻訳について：** この翻訳は閲覧用です。凍結済みの英語原文を正式版とします。

# Figure contract — schema-5 八モデル / mixed-head robustness（Amendment D）

## 中心的な結論

同じ四つの source-specific Validation-family cohorts において、適格な八つの凍結済み PLMs を公平に
比較できます。同時に、相互に関連するこれらの Validation members を独立 Test とみなすことなく、
Train-only CV と計算コストから、事前宣言した二エンコーダー cascade を選定できます。

## エビデンスと解釈の境界

- 主要な選定エビデンス：凍結済みの共通五折 Train-only
  `S = 0.60 H1 AP + 0.30 H2 AP + 0.10 H3 known macro-F1`。
- 補助エビデンス：equal-block→cluster→member の四情報源 robustness、および厳密な
  all-members-correct cluster fractions。
- 情報源間では平均しません。viral、cellular、background、matched HardNeg は個別の列として
  維持します。
- H3 known-class F1 と reject recall は分けます。H3 boundary には、Nucleocytoviricota F1、
  Preplasmiviricota F1、Produgelaviricota reject recall、literature-unclassified reject recall という
  四つの主要表示行があります。二つの reject groups を一つの主要 pooled endpoint に統合しません。
- Produgelaviricota 行には `7 relations / 2 parents / 2 blocks` と、その生の member `k/n` を表示します。
  literature-unclassified 行には `1 / 1 / 1` と、その生の member `k/n` を表示します。単一レコードの
  行は point のみとし、bootstrap confidence interval は付けません。
- 既存の pooled `8 relations / 3 parents / 3 blocks` endpoint と、別個の凍結済み representative
  benchmark（`n=5`）は、Source Data と QA/caption 資料にのみ残します。いずれも五番目の主要 H3 行
  または paired improvement claim としてメインキャンバスに表示しません。
- `N/A`、`not estimable`、数値のゼロには、それぞれ異なる記号を使用します。
- 選択した経路には `recommended for external confirmation` と表示し、independently validated または
  production-superior とは表示しません。

## 図のアーキタイプとバックエンド

- Archetype：一つの decision/Pareto panel を伴う quantitative comparison grid。
- Backend：Python/matplotlib のみ。
- Main target：幅 183 mm、高さ 225 mm。最終テキストの最小サイズは 6.5 pt。編集可能な SVG/PDF、
  300-dpi PNG、600-dpi LZW TIFF。
- Palette：色覚多様性に配慮した濃紺/オレンジ/青緑と中間色のグレー。rainbow heat map は使用しません。

## パネル構成

### a — 同一のエビデンスと適用可能な heads

コンパクトな四行表：有効な cluster/member/block counts と head applicability。一つの重ならない
`Test accessed = 0` badge によって、Test column を繰り返さず leakage boundary を維持します。
Weighting の詳細は caption/QA に記載します。目的は、八つのモデルに同じ有効なエビデンスが与えられる
ことを確立し、background/HardNeg H2/H3 の誤読を防ぐことです。

### b — 八つの homogeneous models

八行を source-specific expected-path の各列に対して表示します。Cell value は、凍結済みの
equal-block→cluster→member estimate と 95% CI です。隣接する小さな記号で、厳密な
all-members-correct cluster fraction を示します。この panel は記述的であり、cross-source average
や winner highlight はありません。

### c — 事前宣言した九つの mixed candidates

左側：九つすべての固定 candidate IDs と、Train-CV `S ± paired fold SE` および one-SE membership。
右側：すでに Train-CV で選択された nominee だけについて、四つの source-specific expected-path
rates と 95% CIs、および all-6B に対する warning count を示します。完全な nine-candidate ×
four-source diagnostics と contextual deltas は `panel_c_mixed_candidates.tsv` に残しますが、第二の
ranking grid としては意図的に描画しません。Robustness は候補を再順位付けしません。

### d — 運用上のトレードオフ

Accuracy/cost Pareto plot では、常時実行する H1/H2 encoder cost を x 軸に置き、条件付き H3 encoder
cost を別に示します。worst-case sum も併記します。想定 route prevalence を示さずに、prevalence に
依存する runtime を表示しません。

### e — H3 boundary

独立した panel に、四つの主要 H3 行だけを正確に示します。すなわち、二つの known-phylum F1 values、
および個別の Produgelaviricota と literature-unclassified reject recalls です。Known-class 行には
truth と evaluation support、reject 行には生の member `k/n`、parent count、block count を表示します。
Pooled rare recall、別個の `4/5` representative benchmark、長い interpretation note は caption/QA と
Source Data に残し、メインプロットの外に置きます。Reject は二つの既知 phyla への強制的な割り当てを
避けることを意味し、一般的な unknown-virus detection を意味しません。

## レビュアーリスクマップ

1. Selection leakage：同じ Validation families を調整と確認の両方に使用することはできません。
   図上に Train-CV nomination と external-confirmation label を表示します。
2. Pseudoreplication：block count と equal block→cluster→member bootstrap を表示し、単純な
   sequence-level CI は決して使用しません。
3. Source imbalance：四情報源の平均を禁止します。
4. H3 overclaim：Produgelaviricota と literature-unclassified を分け、生の `k/n` と hierarchical
   support を表示し、single-block CI を表示せず、pooled value をメインキャンバス外に置き、reject
   recall と known macro-F1 を分けます。
5. Multiple comparisons：all-6B と比較する八つの nontrivial candidates だけを Holm family に
   含めます。all-6B self-delta はゼロであり、test ではありません。
6. Cost overclaim：always-on と conditional encoder costs を分け、timings は特定の
   workstation/environment に依存すると明記します。

## 必須のソースデータ表

- `materialization_summary.tsv` と schema-4 `coverage_summary.tsv` continuity
- `legacy_numerical_operator_runtime.json` と
  `schema4_recomputation_audit_summary.tsv`（four-thread exact replay gate。Amendment-B tolerances は
  diagnostic upper bounds にすぎません）
- `source_path_summary.tsv`
- `strict_cluster_summary.tsv`
- `train_cv_candidate_summary.tsv`
- `pairwise_source_path_delta.tsv`
- `accuracy_cost_pareto.tsv`
- `candidate_nomination.tsv`
- `h3_class_summary.tsv`
- `model_cost_registry.tsv`

描画されるすべての値は、エクスポートした panel source-data TSVs から復元できなければなりません。
plotting script は、読み取り前に結果の `CHECKSUMS.sha256` を検証する必要があります。
`source_data/panel_d_h3_boundary.tsv` は安定した artifact name を維持し、四つの panel-e primary rows と
明示的に secondary とした二つの rows に加え、endpoint role、truth/evaluation support、parent/block
support、member と representative の生の `k/n`、value、confidence-interval fields を含みます。
