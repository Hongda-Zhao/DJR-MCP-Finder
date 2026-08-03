<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/DATA_AUDIT.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# 冻结输入与经验分辨率审计

本次审计在经典方法 score aggregation 之前完成。它独立于各方法的结果，也不会改变冻结的 estimand。

## 输入约定结果

状态：**PASS**。

- Cohort 是精确的冻结 Train ID 集合：6,634 条记录和 5,566 个 `global_component_id`；不包含任何 Validation 或 Test 记录。
- 标签包含 6,000 条 non-DJR、298 条 cellular DJR 和 336 条 VMA-DJR 记录；VMA 是 DJR 的严格子集。
- 每个 component 只属于一个 fold。每条记录会被评价一次、calibration 一次，并用于三个 fit/reference cycle。
- 在全部五个 cycle 中，calibration、evaluation 和 reference component 互不重叠。全部十个 DJR/VMA reference manifest 都与对应 fit fold 的 positive 集合完全相同。
- TSV/FASTA 的 ID、顺序、序列和 checksum 一致。五个冻结 source hash 和全部 52 个 derived-input hash 都与其 attestation 匹配。
- 项目的 post-split integrity report 为 PASS，跨 split 的 component、sequence-SHA 或满足条件的 search-edge violation 均为零。

## Evaluation fold 计数

单元格显示 `records/components`。

| Eval fold | H1 DJR + | H1 non-DJR - | H2 VMA + | H2 cellular - | End-to-end VMA + | End-to-end - |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 114/94 | 1200/731 | 55/47 | 59/47 | 55/47 | 1259/778 |
| 2 | 178/65 | 1200/1115 | 119/18 | 59/47 | 119/18 | 1259/1162 |
| 3 | 115/48 | 1200/1112 | 53/47 | **62/1** | 53/47 | 1262/1113 |
| 4 | 114/91 | 1200/1109 | 55/49 | 59/42 | 55/49 | 1259/1151 |
| 5 | 113/94 | 1200/1107 | 54/48 | 59/46 | 54/48 | 1259/1153 |

## 循环 3/1/1 计数

| Cycle | Eval | Calibration | Fit folds | H2 calibration + / - | DJR reference | VMA reference |
|---|---:|---:|---|---:|---:|---:|
| 1 | 1 | 2 | 3,4,5 | 119/18 +; 59/47 - | 342/233 | 162/144 |
| 2 | 2 | 3 | 1,4,5 | 53/47 +; **62/1 -** | 341/279 | 164/144 |
| 3 | 3 | 4 | 1,2,5 | 55/49 +; 59/42 - | 405/253 | 228/113 |
| 4 | 4 | 5 | 1,2,3 | 54/48 +; 59/46 - | 407/207 | 227/112 |
| 5 | 5 | 1 | 2,3,4 | 55/47 +; 59/47 - | 407/204 | 227/114 |

## 分辨率限制

1. Fold 3 的 62 条 cellular-DJR negative 记录全部属于 `V0GC_96fb96e7e076c167`。在 H2 cycle 2 中，每条记录占 1/62（1.61%）negative mass，因此 99%、99.5% 和 99.9% calibration 都要求经验 false positive 为零。
2. H2 evaluation fold 3 只有一个独立 negative component。只有一个 component 的 bootstrap stratum 的 multiplicity 固定为一，无法估计该 source 的 component 间变异。
3. Fold 2 有 119 条 VMA positive，但只有 18 个 component，其中一个 component 包含 101 条记录。Component weighting 可防止记录数量占据主导，但该 fold 仍只有 18 个独立 positive unit。
4. 各 fold 的记录数量为 1,314/1,378/1,315/1,314/1,313，而 component 数量为 825/1,180/1,160/1,200/1,201。因此，报告 macro estimate 时必须同时给出 fold-level range 和 component count。
5. 两个 non-DJR component 横跨 hard/background source label，但没有跨越 class label。其中较大的 `V0GC_811321e4f6b69a00` 包含 470 条记录（465 条 hard 和 5 条 background）。Source weighting 和 bootstrap resampling 会保持每个 global component 完整。

因此，受影响的 H2 和 end-to-end low-FPR sensitivity interval 被报告为 conditional internal evidence。未来的外部评价应在 component level 进行分层，并包含足够多的独立 cellular-DJR negative component，以分辨目标 FPR。
