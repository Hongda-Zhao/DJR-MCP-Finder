<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/results/REPORT.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# 内部 CROSS-FITTED 开发 BENCHMARK — 不是外部 TEST

这是一项内部循环 component-cross-fitted 开发比较，不是外部优效性结论。Headline 已预先固定：ESM-C 6B cosine retrieval 会分别与每个注册的 classical anchor 比较，不会在事后选择最佳 baseline。

## 经验分辨率审计

Endpoint 仍冻结在 99.5% specificity，但会单独报告其经验分辨率，而不会将其视为无条件的 low-FPR evidence。

| Task | Sensitivity inference status | Zero-FP granularity cycles | Singleton calibration sources | Singleton evaluation sources | Low-positive-component folds |
|---|---|---|---|---|---|
| h1_djr | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP | 1,2,3,4,5 | none | none | none |
| h2_vma_conditional | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED | 1,2,3,4,5 | cycle 2 / cal fold 3: cellular_djr_none 62/1 records/components | fold 3: cellular_djr_none 62/1 records/components | fold 2: 119/18 records/components |
| vma_end_to_end | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED | 1,2,3,4,5 | cycle 2 / cal fold 3: cellular_djr_none 62/1 records/components | fold 3: cellular_djr_none 62/1 records/components | fold 2: 119/18 records/components |

具体而言，fold 3 包含 62 条 cellular-DJR negative 记录，但只有一个 global component。在 cycle 2 中，这是 H2 calibration source：每行占 negative mass 的 1/62，因此 99%、99.5% 和 99.9% 都要求经验 false positive 为零。当 fold 3 被评价时，同一个 source 只有一个独立 negative component。
只有一个 component 的 fold/source stratum 的 bootstrap multiplicity 固定为一。因此，其 component 间 calibration/evaluation variation 无法估计；受影响的 sensitivity delta interval 以观察到的该 component 为条件。Fold 2 也只有 18 个独立 VMA-positive component（119 条记录），因此 aggregate value 必须附有 fold range 和 component count。

## Controlled primary comparison

AP 是五个 evaluation fold 的 component-balanced AP 的 macro-average。Sensitivity 使用每个 cycle 的专用 calibration fold，并以 99.5% source-balanced specificity 为目标；其 interval 是 paired global-component bootstrap delta interval，并受上述 resolution status 约束。

| Task | Classical anchor | ESM-C cosine AP | Anchor AP | AP delta (95% CI) | ESM-C sensitivity | Anchor sensitivity | Sensitivity delta (95% CI) | Sensitivity status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| h1_djr | blastp | 0.8719 | 0.9392 | -0.0672 (-0.0998, -0.0347) | 0.7340 | 0.8692 | -0.1353 (-0.1899, -0.0523) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | diamond_ultra | 0.8719 | 0.9406 | -0.0687 (-0.1024, -0.0345) | 0.7340 | 0.9025 | -0.1686 (-0.2170, -0.0979) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | mmseqs_s7.5 | 0.8719 | 0.9319 | -0.0600 (-0.0932, -0.0256) | 0.7340 | 0.8805 | -0.1466 (-0.2034, -0.0722) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | hmmer_component | 0.8719 | 0.9542 | -0.0823 (-0.1119, -0.0521) | 0.7340 | 0.9016 | -0.1676 (-0.2236, -0.1023) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h2_vma_conditional | blastp | 0.9861 | 0.9829 | +0.0032 (-0.0102, +0.0211) | 0.9306 | 0.9443 | -0.0138 (-0.0599, +0.0307) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | diamond_ultra | 0.9861 | 0.9806 | +0.0054 (-0.0112, +0.0268) | 0.9306 | 0.9317 | -0.0011 (-0.0479, +0.0434) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | mmseqs_s7.5 | 0.9861 | 0.9751 | +0.0109 (-0.0051, +0.0303) | 0.9306 | 0.9119 | +0.0187 (-0.0367, +0.0685) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | hmmer_component | 0.9861 | 0.9911 | -0.0050 (-0.0194, +0.0102) | 0.9306 | 0.9569 | -0.0263 (-0.0712, +0.0179) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | blastp | 0.9528 | 0.9544 | -0.0017 (-0.0328, +0.0334) | 0.9301 | 0.9401 | -0.0100 (-0.0557, +0.0343) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | diamond_ultra | 0.9528 | 0.9497 | +0.0031 (-0.0294, +0.0398) | 0.9301 | 0.9317 | -0.0015 (-0.0471, +0.0439) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | mmseqs_s7.5 | 0.9528 | 0.9317 | +0.0211 (-0.0140, +0.0600) | 0.9301 | 0.9078 | +0.0223 (-0.0300, +0.0746) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | hmmer_component | 0.9528 | 0.9660 | -0.0132 (-0.0427, +0.0203) | 0.9301 | 0.9569 | -0.0267 (-0.0708, +0.0197) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |

## 其他 controlled-primary PLM comparator

该 controlled PLM comparator 不会替代注册的 classical anchor。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| esm2_650m_cosine | h1_djr | 0.9515 (0.9152–0.9744) | 0.8954 (0.8371–0.9432) |
| esm2_650m_cosine | h2_vma_conditional | 0.9965 (0.9827–1.0000) | 0.9977 (0.9894–1.0000) |
| esm2_650m_cosine | vma_end_to_end | 0.9906 (0.9639–1.0000) | 0.9859 (0.9400–1.0000) |

## Resource-augmented secondary

PSI-BLAST 使用 iterative positive-database enrichment，并保持为 secondary。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| psiblast_longest_seed_positiveDB_3iter | h1_djr | 0.9705 (0.9365–0.9958) | 0.9493 (0.8958–0.9894) |
| psiblast_longest_seed_positiveDB_3iter | h2_vma_conditional | 0.9982 (0.9913–1.0000) | 0.9750 (0.9574–1.0000) |
| psiblast_longest_seed_positiveDB_3iter | vma_end_to_end | 0.9899 (0.9685–1.0000) | 0.9750 (0.9574–1.0000) |

## Metadata-grouped secondary

Family-grouped HMMER 使用冻结 grouping metadata，并保持为 secondary。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| hmmer_family | h1_djr | 0.9971 (0.9915–1.0000) | 0.9957 (0.9890–1.0000) |
| hmmer_family | h2_vma_conditional | 0.9994 (0.9971–1.0000) | 0.9806 (0.9444–1.0000) |
| hmmer_family | vma_end_to_end | 0.9931 (0.9829–1.0000) | 0.9806 (0.9444–1.0000) |

## Operational supervised，仅作描述性报告

Supervised ESM-C system 会从 labelled negative 学习，因此不符合 primary 要求。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| esmc6b_supervised | h1_djr | 0.9945 (0.9846–0.9999) | 0.9753 (0.8923–1.0000) |
| esmc6b_supervised | h2_vma_conditional | 1.0000 (1.0000–1.0000) | 1.0000 (1.0000–1.0000) |
| esmc6b_supervised | vma_end_to_end | 0.8723 (0.6297–0.9792) | 0.8000 (0.0000–1.0000) |

PSI-BLAST 是 resource-augmented secondary evidence，family-grouped HMMER 是 metadata secondary evidence，而 supervised ESM-C 仅为 operational descriptive evidence。
Pooled raw AP 仅保留为 secondary diagnostic。99.9% ladder 是 `RESOLUTION_LIMITED_SECONDARY`，且无法通过该 cohort 估计 FP-per-million。
两个 primary metric 的 uncertainty 都使用 10,000 次 paired global-component replicate。只报告 delta 95% interval；不会将 bootstrap sign fraction 表述为 P value，也不会生成 Holm adjustment。
Source-specific calibration/evaluation check、distance stratum、approximate MDE、profile construction、reference contract 和 runtime receipt 位于随附 TSV 文件中。
