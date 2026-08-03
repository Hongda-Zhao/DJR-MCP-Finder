<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/figures/FIGURE_LEGEND.md -->

この翻訳は閲覧の便宜のみを目的としています。凍結された英語の原文が正式な文書です。

# Figure legend

**Figure | DJR-MCP Finder v0 対 v0.1 remote-component development audit。**
**a、** すべての component holdout、BLAST-defined 20–30% identity twilight layer、
BLAST-defined qcov <80% low-coverage stress layer における、raw encoder cosine layer と
task-adapted detector の paired component-balanced sensitivity difference（v0.1 minus v0）。
threshold は method、task、evaluation cycle ごとに、calibration fold 上の nominal 99.5%
specificity で個別に lock しました。error bar は、threshold を固定した 95% paired
evaluation-component bootstrap interval であり、calibration uncertainty は含みません。
**b、** low-coverage stress layer における absolute component-balanced sensitivity。marker
shape は H1 DJR、conditional H2 MCP、MCP end-to-end を示します。**c、** すべての H1
component holdout における、source- and component-balanced normalized partial AUROC at
FPR <=0.005。一つ以上の negative source で 0.5% FPR における independent-component
resolution が不足するため、H2 と end-to-end endpoint は省略します。**d、** strict identity
<20%、任意の coverage における identity <20%、20–30% twilight、low-coverage stress、すべての
holdout の positive independent-component count。点線と破線は、事前に凍結された descriptive
（n=30）および formal ultra-remote（n=100）の最小値を示します。空心 symbol は、v0 または
v0.1 が少なくとも一つの evaluation fold で実際の 99.5% specificity を満たさなかったことを
示します。したがって delta は matched-specificity improvement ではなく descriptive です。
すべての解析は Train-only cyclic component crossfit を使用します。BLAST-derived stratum は
method-conditioned であり、別の method が BLAST より優れているという正式な証拠ではありません。

Source data：`figures/source_data/` 内の `paired_delta.tsv`、`low_coverage_sensitivity.tsv`、
`low_fpr_pauc.tsv`、`sample_sufficiency.tsv`。
