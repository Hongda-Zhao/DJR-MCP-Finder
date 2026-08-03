<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/figures/FIGURE_CONTRACT.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# Benchmark 可視化 contract

中心的結論：ESM-C 6B cosine retrieval は、controlled classical anchor に対して一般的な sensitivity の向上を示しません。ESM2-650M は exploratory な end-to-end VMA signal を示しますが、specificity を一致させた外部 validation が必要です。

Figure archetype：quantitative grid。

対象 journal/output：全幅の manuscript または technical-report figure。編集可能な SVG と PDF、高解像度 PNG、LZW-compressed TIFF。

Backend：Python（matplotlib）。描画と export にのみ使用します。

最終サイズ：main figure 183 × 215 mm、supplementary figure 183 × 86 mm。

Panel map：

- a：九つの method と三つの task すべてについて、absolute fold-macro component-balanced average precision。
- b：held-out calibration fold 上で 99.5% specificity を目標に選択された threshold での absolute fold-macro sensitivity。
- c：事前登録済み ESM-C-minus-classical AP difference と 95% component-bootstrap interval。
- d：事前登録済み ESM-C-minus-classical sensitivity difference と 95% component-bootstrap interval。
- e：六つの controlled method について観察された evaluation-fold specificity。Calibration-to-evaluation drift を可視化します。
- Supplementary a：BLAST local-query-coverage <80% stratum における記述的 sensitivity。
- Supplementary b：method/task ごとの no-hit fraction。

Evidence hierarchy：

- Hero evidence：panel c と d の paired-difference forest plot。
- Validation evidence：panel a と b の absolute metric matrix。
- Controls/robustness：panel e で達成された specificity。Supplementary figure の coverage/distance diagnostic。

必要な統計：five-fold macro estimand、10,000 回の paired global-component bootstrap replicate、percentile 95% interval。Bootstrap P value や multiplicity-adjusted claim は使用しません。

必要な source data：検証済み Benchmark Release の `metrics_primary.tsv`、`paired_deltas.tsv`、`distance_strata.tsv`、`validation.json`、`summary.json`。

Image-integrity note：27 個すべての primary-metric row と、12 個すべての登録済み paired comparison を使用します。Method、task、fold、interval は一つも省略しません。Secondary/resource-augmented track と operational track は表示で区別し、controlled headline と pooled しません。

Reviewer risk：

- これは内部の Train-only cross-fitted 開発 Benchmark であり、外部 Test ではありません。
- 99.5% は calibration-fold target です。Evaluation specificity は別に測定し、表示します。
- H2 と end-to-end sensitivity interval は conditional です。一つの negative source/fold が 62 record を含みますが、独立 component は一つだけだからです。
- PSI-BLAST、family-grouped HMMER、supervised ESM-C は information budget が異なります。
- BLAST local query coverage は記述的な alignment stratum であり、global evolutionary distance ではありません。
