# Figure legends

## Fig. 1 | Comparison of protein-language-model and classical remote-homology retrieval

**a, b** Fold-macro component-balanced average precision (a) and sensitivity (b) for three benchmark tasks and nine methods. Sensitivity is measured on evaluation folds using thresholds selected to target 99.5% source-balanced specificity on disjoint calibration folds. Colored row bars distinguish controlled, resource-augmented, metadata-augmented and operational tracks. Daggers mark resource-augmented PSI-BLAST, double daggers mark metadata-grouped HMMER, and the section symbol marks the operational supervised ESM-C system; these tracks are not substituted for controlled anchors. **c, d** Pre-registered differences between ESM-C 6B cosine retrieval and each controlled classical anchor for average precision (c) and calibration-targeted sensitivity (d). Points are observed five-fold macro differences and horizontal lines are percentile 95% intervals from 10,000 paired global-component bootstrap replicates. Values below zero favour the classical anchor. Open points denote H2/end-to-end intervals that are conditional on the observed singleton negative component. **e** Fold-macro evaluation specificity for controlled methods; the dashed line is the 99.5% calibration target rather than an assumed evaluation value. The internal benchmark contains 6,634 Train records in 5,566 global components under cyclic 3/1/1 component cross-fitting; Validation and Test predictions are zero. The H2/end-to-end endpoint includes a fold/source with 62 cellular-DJR records in one component and is resolution-limited. Source data are provided in the accompanying TSV files.

## Supplementary Fig. 1 | Descriptive remote-homology coverage diagnostics

**a** Component-balanced sensitivity in the subset whose best local BLASTP match covers less than 80% of the query. Points show descriptive estimates for the three tasks; this stratum contains 264 positive components for H1 and 100 for each VMA task. **b** Fraction of evaluation records encoded as no-hit for each controlled method and task. These panels use the same calibration-targeted thresholds as the main benchmark, do not match methods to a common realized evaluation specificity, and do not treat BLAST local query coverage as a global evolutionary-distance estimate. Source data are provided in the accompanying TSV files.

## 中文解读

主图 c、d 是结论面板：H1 中 ESM-C 的置信区间整体位于零左侧；H2 和端到端 VMA 的区间均跨零。面板 e 用实际 evaluation specificity 防止把“校准目标 99.5%”误读为所有 evaluation fold 都达到了 99.5%。补充图仅用于发现远缘/低覆盖信号，不承担优效性推断。
