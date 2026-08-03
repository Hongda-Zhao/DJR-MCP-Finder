<!-- i18n-mirror: non-authoritative translation; source=results/figures/project_v0/model_benchmark_metric_revision_1/QA_NOTES.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# Figure 1 QA note

- 中心的結論：修正済み raw-score AP、paired one-SE、Validation gate、事前登録済み tie break により、正確な 14-model registry から ESM-C 6B を選択します。
- Metric lineage：binary ranking metric は raw decision-function score を使用し、calibrated probability は calibration/threshold metric のために予約します。
- Archetype/backend：quantitative grid。Python/Matplotlib のみ。
- 最終サイズ：183 × 238 mm。SVG/PDF は編集可能な vector、TIFF は 600 dpi、PNG は 300 dpi。
- 入力完全性：前／後の正確な candidate count = 14/14。Exclusion = 0、sampling = none、hidden failed candidate = 0。
- 境界：development-only。固定された各 candidate row は `test_status=not_evaluated` と記載する必要があります。
- 統計：一つの共有 Train-only five-fold global-component map。Per-head/composite SE = SD/√5。Paired SEΔ は same-fold difference を使用します。
- H3 の制約：`unknown/other` は operational rejection diagnostic（Validation n=5）であり、任意の unseen-virus detector ではありません。
- Compute の制約：NA。固定比較には model ごとの peak_gpu_memory_source attestation がありません。Timing には 2 個の comparability group があるため、panel c は記述的であり、Pareto frontier を主張しません。
- Image integrity：すべての panel はプログラムで生成された quantitative vector graphic です。Microscopy、photograph、crop、local contrast adjustment、pseudo-colour processing はありません。
- Automated export QA：PASS（公開前に dimension と編集可能な SVG text を確認）。
- Visual QA status：passed。
- 手動による native-resolution inspection：五つすべての panel が判読可能で、clipping、overlap、missing label はありません。
- Plot された numeric source は変更されていません。この refresh では、修正済みの固定 Test policy を維持します。
- MCP の用語のみを更新。Native-resolution PNG について、clipping、overlap、label completeness を確認しました。
