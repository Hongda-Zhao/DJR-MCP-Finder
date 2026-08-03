<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/figures/FIGURE_LEGEND.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# 图例

## Fig. 1 | Protein-language-model 与经典 remote-homology retrieval 的比较

**a, b** 三个 Benchmark task、九种 method 的 fold-macro component-balanced average precision（a）和 sensitivity（b）。Sensitivity 在 evaluation fold 上测量，其 threshold 是在互不重叠的 calibration fold 上以 99.5% source-balanced specificity 为目标选择的。彩色 row bar 用于区分 controlled、resource-augmented、metadata-augmented 和 operational track。单剑号标记 resource-augmented PSI-BLAST，双剑号标记 metadata-grouped HMMER，section symbol 标记 operational supervised ESM-C system；这些 track 不会替代 controlled anchor。**c, d** ESM-C 6B cosine retrieval 与各个 controlled classical anchor 在 average precision（c）和以 calibration 为目标的 sensitivity（d）上的预注册差异。点表示观察到的 five-fold macro difference，横线表示来自 10,000 次 paired global-component bootstrap replicate 的 percentile 95% interval。小于零的值有利于 classical anchor。空心点表示 H2/end-to-end interval，其结果以观察到的 singleton negative component 为条件。**e** Controlled method 的 fold-macro evaluation specificity；虚线代表 99.5% calibration target，而不是假定的 evaluation 值。该内部 Benchmark 在循环 3/1/1 component cross-fitting 下包含 6,634 条 Train 记录和 5,566 个 global component；Validation 与 Test prediction 均为零。H2/end-to-end endpoint 包含一个 fold/source，其中 62 条 cellular-DJR 记录只属于一个 component，因此分辨率受限。源数据在随附 TSV 文件中提供。

## Supplementary Fig. 1 | 描述性 remote-homology coverage diagnostic

**a** 最佳 local BLASTP match 覆盖 query 不足 80% 的 subset 中，component-balanced sensitivity。点表示三个 task 的描述性 estimate；该 stratum 在 H1 中包含 264 个 positive component，在每个 VMA task 中包含 100 个。**b** 各 controlled method 与 task 被编码为 no-hit 的 evaluation record fraction。这些 panel 使用与主 Benchmark 相同、以 calibration 为目标的 threshold，不会将不同 method 匹配到共同的实际 evaluation specificity，也不会把 BLAST local query coverage 当成全局 evolutionary-distance estimate。源数据在随附 TSV 文件中提供。

## 中文解读

主图 c、d 是结论面板：H1 中 ESM-C 的置信区间整体位于零左侧；H2 和端到端 VMA 的区间均跨零。面板 e 用实际 evaluation specificity 防止把“校准目标 99.5%”误读为所有 evaluation fold 都达到了 99.5%。补充图仅用于发现远缘/低覆盖信号，不承担优效性推断。
