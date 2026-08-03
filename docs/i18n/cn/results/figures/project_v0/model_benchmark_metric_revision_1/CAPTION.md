<!-- i18n-mirror: non-authoritative translation; source=results/figures/project_v0/model_benchmark_metric_revision_1/CAPTION.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# Figure 1 | 仅使用冻结开发数据选择 protein representation

**a,** 全部 14 个候选的四项冻结 Train-only score。H1/H2 AP 使用 raw decision-function score 计算；H3 使用未 calibration 的 class probability。数值为 mean ± SE，其中 SE 是在同一个共享 global-component fold map 上五个 score 的 sample standard deviation 除以 √5。S = 0.60·H1 AP + 0.30·H2 AP + 0.10·H3 two-known-class macro-F1。**b,** 相对于 fresh ESM-2 650M baseline 的 Validation metric difference（红色区域：regression 大于 0.01），以及相对于 esmc_6b 的 paired one-SE evidence；ΔS = S_reference − S_candidate，SEΔ 由五个 same-fold difference 计算。**c,** 描述性的 S–embedding-time comparison。Time 是排除 model load 后累计的 inference duration；marker 用于区分 2 个并不相同的 timing-comparability group。Peak GPU memory 为 NA：冻结比较没有 per-model peak_gpu_memory_source attestation；因此不推断 Pareto frontier。**d,** H3 Validation evidence 将 supervised two-class metric（Nucleocytoviricota 对 Preplasmiviricota）与 operational `unknown/other` rejection recall（diagnostic n = 5）分开；后者不能证明能够检测任意 unseen virus。**e,** 完整的 decision audit；修正后的 protocol 选择 ESM-C 6B。冻结的 Validation baseline 是 ESM-2 650M。没有遗漏任何候选，也没有读取 Test prediction 或 metric。

源数据：`panel_a_cv_metrics.tsv` 至 `panel_e_decision.tsv`。Train/Validation/Test 边界：selection 只使用 Train component-aware CV 和 Validation；R1 selection 中没有读取或生成 Test prediction 或 metric（`test_evaluation_permitted=false`）。现有 cohort 已在历史 ESM-2 650M lifecycle 中打开，无法评价 ESM-C 6B，必须由 prospective cohort 取代。不使用 hypothesis test 或 multiple-comparison correction；a 和 b 中的 interval 是由 fold 得出的 uncertainty，而不是 confidence interval。
