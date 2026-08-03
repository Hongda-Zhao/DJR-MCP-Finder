<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/DATA_AUDIT.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# 固定入力と経験的分解能の audit

この audit は、従来型手法の score aggregation 前に完了しました。手法の結果から独立しており、固定された estimand を変更しません。

## 入力 contract の結果

状態：**PASS**。

- Cohort は、固定された Train ID の正確な集合です。6,634 record、5,566 の `global_component_id` からなり、Validation または Test record は含まれません。
- Label は 6,000 の non-DJR、298 の cellular DJR、336 の VMA-DJR record を含みます。VMA は DJR の厳密な subset です。
- 各 component は一つの fold だけに属します。各 record は一度評価され、一度 calibration され、三つの fit/reference cycle で使用されます。
- 五つすべての cycle で、calibration、evaluation、reference component は互いに独立しています。十個すべての DJR/VMA reference manifest は、対応する fit-fold positive set と完全に一致します。
- TSV/FASTA の ID、順序、配列、checksum は一致します。五つの固定 source hash と 52 個すべての derived-input hash は、それぞれの attestation と一致します。
- Project の post-split integrity report は PASS です。Split をまたぐ component、sequence-SHA、条件を満たす search-edge の violation はゼロです。

## Evaluation fold の count

各 cell は `records/components` を示します。

| Eval fold | H1 DJR + | H1 non-DJR - | H2 VMA + | H2 cellular - | End-to-end VMA + | End-to-end - |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 114/94 | 1200/731 | 55/47 | 59/47 | 55/47 | 1259/778 |
| 2 | 178/65 | 1200/1115 | 119/18 | 59/47 | 119/18 | 1259/1162 |
| 3 | 115/48 | 1200/1112 | 53/47 | **62/1** | 53/47 | 1262/1113 |
| 4 | 114/91 | 1200/1109 | 55/49 | 59/42 | 55/49 | 1259/1151 |
| 5 | 113/94 | 1200/1107 | 54/48 | 59/46 | 54/48 | 1259/1153 |

## 循環 3/1/1 の count

| Cycle | Eval | Calibration | Fit folds | H2 calibration + / - | DJR reference | VMA reference |
|---|---:|---:|---|---:|---:|---:|
| 1 | 1 | 2 | 3,4,5 | 119/18 +; 59/47 - | 342/233 | 162/144 |
| 2 | 2 | 3 | 1,4,5 | 53/47 +; **62/1 -** | 341/279 | 164/144 |
| 3 | 3 | 4 | 1,2,5 | 55/49 +; 59/42 - | 405/253 | 228/113 |
| 4 | 4 | 5 | 1,2,3 | 54/48 +; 59/46 - | 407/207 | 227/112 |
| 5 | 5 | 1 | 2,3,4 | 55/47 +; 59/47 - | 407/204 | 227/114 |

## 分解能の制約

1. Fold 3 の cellular-DJR negative record 62 件は、すべて `V0GC_96fb96e7e076c167` に属します。H2 cycle 2 では、各 record が negative mass の 1/62（1.61%）を持つため、99%、99.5%、99.9% calibration のすべてで、経験的 false positive をゼロにする必要があります。
2. H2 evaluation fold 3 には、独立した negative component が一つしかありません。Component が一つの bootstrap stratum は multiplicity が一に固定され、この source の component 間 variation を推定できません。
3. Fold 2 には VMA positive が 119 件ありますが、component は 18 個だけで、そのうち一つの component が 101 record を含みます。Component weighting によって record count の支配は防がれますが、この fold の独立した positive unit は依然として 18 個だけです。
4. Fold の record count は 1,314/1,378/1,315/1,314/1,313 ですが、component count は 825/1,180/1,160/1,200/1,201 です。したがって、macro estimate には fold-level range と component count を併記する必要があります。
5. 二つの non-DJR component は、class label をまたがずに hard/background source label にまたがっています。大きい方の `V0GC_811321e4f6b69a00` は 470 record（hard 465、background 5）を含みます。Source weighting と bootstrap resampling では、各 global component を分割しません。

したがって、影響を受ける H2 と end-to-end の low-FPR sensitivity interval は、conditional な internal evidence として報告します。将来の外部評価では component level で層別化し、目標 FPR を分解できるだけの独立した cellular-DJR negative component を含める必要があります。
