<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/figures/FIGURE_CONTRACT.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# Benchmark 可视化约定

核心结论：ESM-C 6B cosine retrieval 相比 controlled classical anchor 并未带来普遍的 sensitivity 提升；ESM2-650M 在 end-to-end VMA 上显示出 exploratory signal，需要在匹配 specificity 的外部验证中确认。

图表类型：quantitative grid。

目标期刊/输出：全宽 manuscript 或 technical-report figure；可编辑 SVG 和 PDF，以及高分辨率 PNG 与 LZW-compressed TIFF。

Backend：Python（matplotlib），仅用于绘图与导出。

最终尺寸：主图 183 × 215 mm；补充图 183 × 86 mm。

Panel 对应关系：

- a：全部九种 method、三个 task 的 absolute fold-macro component-balanced average precision。
- b：在 held-out calibration fold 上选择 99.5% specificity threshold 后的 absolute fold-macro sensitivity。
- c：预注册的 ESM-C-minus-classical AP difference，以及 95% component-bootstrap interval。
- d：预注册的 ESM-C-minus-classical sensitivity difference，以及 95% component-bootstrap interval。
- e：六种 controlled method 在 evaluation fold 上观察到的 specificity，用于显示 calibration-to-evaluation drift。
- Supplementary a：BLAST local-query-coverage <80% stratum 中的描述性 sensitivity。
- Supplementary b：各 method/task 的 no-hit fraction。

证据层级：

- Hero evidence：panel c 和 d 中的 paired-difference forest plot。
- Validation evidence：panel a 和 b 中的 absolute metric matrix。
- Controls/robustness：panel e 中达到的 specificity；supplementary figure 中的 coverage/distance diagnostic。

所需统计：five-fold macro estimand；10,000 次 paired global-component bootstrap replicate；percentile 95% interval；不报告 bootstrap P value 或 multiplicity-adjusted claim。

所需源数据：已验证 Benchmark Release 中的 `metrics_primary.tsv`、`paired_deltas.tsv`、`distance_strata.tsv`、`validation.json` 和 `summary.json`。

图像完整性说明：使用全部 27 个 primary-metric row 和全部 12 个预注册 paired comparison。没有省略任何 method、task、fold 或 interval。Secondary/resource-augmented 与 operational track 会加以标记，而不会与 controlled headline 合并。

Reviewer 风险：

- 这是内部 Train-only cross-fitted 开发 Benchmark，不是外部 Test。
- 99.5% 是 calibration-fold target；evaluation specificity 会单独测量和展示。
- H2 和 end-to-end sensitivity interval 为 conditional，因为一个 negative source/fold 包含 62 条记录，但只有一个独立 component。
- PSI-BLAST、family-grouped HMMER 和 supervised ESM-C 的 information budget 不同。
- BLAST local query coverage 是描述性 alignment stratum，不是全局 evolutionary distance。
