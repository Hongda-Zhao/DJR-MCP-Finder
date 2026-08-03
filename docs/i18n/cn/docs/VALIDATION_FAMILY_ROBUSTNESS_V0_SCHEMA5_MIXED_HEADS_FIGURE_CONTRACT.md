<!-- i18n-mirror: non-authoritative translation; source=docs/VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_FIGURE_CONTRACT.md -->

> **翻译说明：** 本译文仅供阅读；冻结的英文原文为权威版本。

# Figure contract — schema-5 八模型 / mixed-head robustness（Amendment D）

## 核心结论

在相同的四个 source-specific Validation-family cohorts 上，可以公平比较八个符合条件的冻结 PLMs；
同时，可以依据 Train-only CV 和计算成本提名一个预先声明的双 encoder cascade，而不把这些相关的
Validation members 当作独立 Test。

## 证据与解释边界

- 主要提名证据：冻结的共享五折 Train-only
  `S = 0.60 H1 AP + 0.30 H2 AP + 0.10 H3 known macro-F1`。
- 辅助证据：equal-block→cluster→member 四来源 robustness，以及严格的 all-members-correct cluster
  fractions。
- 不对来源取平均；viral、cellular、background 和 matched HardNeg 保持为独立列。
- H3 known-class F1 与 reject recall 分开。H3 boundary 有四个主要展示行：Nucleocytoviricota F1、
  Preplasmiviricota F1、Produgelaviricota reject recall 和 literature-unclassified reject recall。
  两个 reject groups 不得合并为主要 pooled endpoint。
- Produgelaviricota 行显示 `7 relations / 2 parents / 2 blocks` 及其原始 member `k/n`；
  literature-unclassified 行显示 `1 / 1 / 1` 及其原始 member `k/n`。单记录行只显示 point，
  不提供 bootstrap confidence interval。
- 既有的 pooled `8 relations / 3 parents / 3 blocks` endpoint 和独立的冻结 representative benchmark
  （`n=5`）仅保留在 Source Data 与 QA/caption 材料中。两者既不作为第五个主要 H3 行出现在主画布中，
  也不作为 paired improvement claim。
- `N/A`、`not estimable` 和数值零使用不同标记。
- 所选路线标记为 `recommended for external confirmation`，而不是 independently validated 或
  production-superior。

## 图型与后端

- Archetype：quantitative comparison grid，配一个 decision/Pareto panel。
- Backend：仅使用 Python/matplotlib。
- 主目标：宽 183 mm、高 225 mm；最终文字最小 6.5 pt；可编辑 SVG/PDF，以及 300-dpi PNG 和
  600-dpi LZW TIFF。
- Palette：色盲安全的深蓝/橙/青绿色与中性灰；不得使用 rainbow heat map。

## Panel map

### a — 相同证据与适用 heads

紧凑的四行表：合法的 cluster/member/block counts 和 head applicability。一个不重叠的
`Test accessed = 0` badge 可维持 leakage boundary，无需重复 Test column。Weighting 细节保留在
caption/QA 中。目的：确认八个模型接收相同的合法证据，并避免对 background/HardNeg H2/H3 的误读。

### b — 八个 homogeneous models

八行，按 source-specific expected-path 分列。Cell value 是冻结的 equal-block→cluster→member estimate，
附 95% CI；相邻的小标记显示严格的 all-members-correct cluster fraction。该 panel 为描述性结果，
不提供 cross-source average 或 winner highlight。

### c — 九个预先声明的 mixed candidates

左侧：全部九个固定 candidate IDs，以及 Train-CV `S ± paired fold SE` 和 one-SE membership。
右侧：只显示已经由 Train-CV 选出的 nominee 的四个 source-specific expected-path rates 及 95% CIs，
以及其相对 all-6B 的 warning count。完整的 nine-candidate × four-source diagnostics 和 contextual
deltas 保留在 `panel_c_mixed_candidates.tsv`，但有意不绘制为第二个 ranking grid。Robustness 不会
重新排序候选。

### d — 运行层面的权衡

Accuracy/cost Pareto plot：x 轴为 always-on H1/H2 encoder cost，conditional H3 encoder cost 单独显示，
并附 worst-case sum。如未说明假定的 route prevalence，则不展示依赖 prevalence 的 runtime。

### e — H3 boundary

一个独立 panel 准确报告四个主要 H3 行：两个 known-phylum F1 values，以及分开的
Produgelaviricota 和 literature-unclassified reject recalls。Known-class 行显示 truth 与 evaluation
support；reject 行显示原始 member `k/n`、parent count 和 block count。Pooled rare recall、独立的
`4/5` representative benchmark 和较长的 interpretation note 保留在 caption/QA 与 Source Data 中，
不进入主图。Reject 表示避免强制分配到两个已知 phyla，而不是通用 unknown-virus detection。

## Reviewer-risk map

1. Selection leakage：相同的 Validation families 不能既用于调优又用于确认；图中应显示 Train-CV
   nomination 和 external-confirmation label。
2. Pseudoreplication：显示 block count 和 equal block→cluster→member bootstrap；绝不能使用朴素的
   sequence-level CI。
3. Source imbalance：禁止计算四来源平均值。
4. H3 overclaim：将 Produgelaviricota 与 literature-unclassified 分开，显示原始 `k/n` 和 hierarchical
   support，隐藏 single-block CI，将 pooled value 留在主画布之外，并使 reject recall 与 known
   macro-F1 分开。
5. Multiple comparisons：只有八个 nontrivial candidates 与 all-6B 的比较进入 Holm family；all-6B
   self-delta 为零，不构成 test。
6. Cost overclaim：分开 always-on 和 conditional encoder costs，并说明 timings 仅适用于特定
   workstation/environment。

## 必需的源数据表

- `materialization_summary.tsv`，以及 schema-4 `coverage_summary.tsv` continuity
- `legacy_numerical_operator_runtime.json`，以及
  `schema4_recomputation_audit_summary.tsv`（four-thread exact replay gate；Amendment-B tolerances
  仅为 diagnostic upper bounds）
- `source_path_summary.tsv`
- `strict_cluster_summary.tsv`
- `train_cv_candidate_summary.tsv`
- `pairwise_source_path_delta.tsv`
- `accuracy_cost_pareto.tsv`
- `candidate_nomination.tsv`
- `h3_class_summary.tsv`
- `model_cost_registry.tsv`

每个绘图值都必须能从导出的 panel source-data TSVs 中恢复；plotting script 在读取前必须验证结果目录的
`CHECKSUMS.sha256`。`source_data/panel_d_h3_boundary.tsv` 保留其稳定的 artifact name，并包含四个
panel-e primary rows 和两个明确标为 secondary 的 rows，以及 endpoint role、truth/evaluation support、
parent/block support、member 与 representative 的原始 `k/n`、value 和 confidence-interval fields。
