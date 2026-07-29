# Project V0 current figure release

活动 release 只保留一张主图和一张补充图。Figure 1 决定并解释主模型；Supplementary Fig. S1 是模型
冻结后的 schema-5 family-neighbour 辅助评价，不能反馈到 Figure 1。

| Figure | Directory | 结论 | 解释边界 |
| --- | --- | --- | --- |
| 1. 14-model development benchmark | `model_benchmark_metric_revision_1/` | raw-score ranking 下选择 ESM-C 6B，`S=0.997145`；旧 650M H1 CV AP `0.857` 是 sigmoid-tie artifact，修正为 `0.997917` | Train/Validation development selection；ESM-C 6B Test=`not_evaluated` |
| Supplementary Fig. S1. Schema-5 head-focused robustness | `validation_family_robustness_v0_schema5_head_focus/` | 八个 homogeneous systems 与九个预注册 mixed recipes；Train-CV nominee 为 H1/H2 ESM-2 3B + H3 ESM-C 6B，四来源 `0/4` warning | auxiliary only；robustness 不参与排序；不是 equivalence、release gate、独立 Test 或 unseen-family benchmark |

Supplementary Fig. S1 分三层展示逐 Head 表现、expected-path 表现和 3×3 mixed recipe 的
Train-CV→nomination→四来源检查顺序。H3 rare/unclassified 仍分别报告，不能合并成普适 unknown-virus
检测。完整阅读说明见该目录的 `FIGURE_GUIDE.md`。

每个完成目录保留 editable SVG/PDF、PNG、panel source data、QA/provenance 与 checksum manifest；可用的
TIFF 也随当前 compact release 提供。`FIGURE_RELEASE_CHECKSUMS.sha256` 只是两张当前图的便捷索引；
冻结主流程 manifest 绑定 Figure 1，head-focus release manifest 绑定 Supplementary Fig. S1。

历史 Test 只为 ESM-2 650M 打开；当前活动图不提供 ESM-C 6B Test panel，避免把旧模型证据错误归给新模型。
