<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/figures/FIGURE_LEGEND.md -->

本译文仅供阅读；冻结的英文源文档为权威版本。

# 图注

**图 | DJR-MCP Finder v0 与 v0.1 的远缘 component 开发审计。**
**a，** 对全部 component holdouts、BLAST 定义的 20–30% identity twilight layer 以及 BLAST 定义的
qcov <80% low-coverage stress layer，比较 raw encoder cosine layer 与 task-adapted detector 的
paired component-balanced sensitivity difference（v0.1 minus v0）。每个 method、task 和
evaluation cycle 的 threshold 分别在其 calibration fold 上按名义 99.5% specificity 锁定。
Error bar 是 threshold 固定的 95% paired evaluation-component bootstrap interval，不包含
calibration uncertainty。**b，** low-coverage stress layer 中的 absolute component-balanced
sensitivity。Marker shape 分别表示 H1 DJR、conditional H2 MCP 或 MCP end-to-end。**c，** 全部
H1 component holdouts 上、按 source 和 component 平衡、FPR <=0.005 的 normalized partial AUROC。
由于一个或多个 negative sources 在 0.5% FPR 下缺乏 independent-component resolution，H2 和
end-to-end endpoints 被省略。**d，** strict identity <20%、任何 coverage 下 identity <20%、
20–30% twilight、low-coverage stress 与全部 holdouts 的 positive independent-component counts。
点线与虚线表示预冻结的 descriptive（n=30）和 formal ultra-remote（n=100）下限。空心符号表示
v0 或 v0.1 在至少一个 evaluation fold 中未达到实际 99.5% specificity，因此 delta 是描述性的，
而不是 matched-specificity improvement。所有分析均使用 Train-only cyclic component crossfit；
BLAST-derived strata 受 method 条件限制，并不是其他 method 优于 BLAST 的正式证据。

Source data：`figures/source_data/` 下的 `paired_delta.tsv`、`low_coverage_sensitivity.tsv`、
`low_fpr_pauc.tsv` 与 `sample_sufficiency.tsv`。
