<!-- i18n-mirror: non-authoritative translation; source=results/figures/project_v0/model_benchmark_metric_revision_1/QA_NOTES.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# Figure 1 QA 说明

- 核心结论：修正后的 raw-score AP、paired one-SE、Validation gate 和预注册 tie break，从精确的 14-model registry 中选择了 ESM-C 6B。
- Metric lineage：binary ranking metric 使用 raw decision-function score；calibrated probability 仅用于 calibration/threshold metric。
- Archetype/backend：quantitative grid；仅使用 Python/Matplotlib。
- 最终尺寸：183 × 238 mm；SVG/PDF 为可编辑 vector，TIFF 为 600 dpi，PNG 为 300 dpi。
- 输入完整性：前/后的精确 candidate count = 14/14；exclusion = 0；sampling = none；隐藏的 failed candidate = 0。
- 边界：仅用于开发；每个冻结 candidate row 都必须写明 `test_status=not_evaluated`。
- 统计：一个共享的 Train-only five-fold global-component map；per-head/composite SE = SD/√5；paired SEΔ 使用 same-fold difference。
- H3 局限：`unknown/other` 是 operational rejection diagnostic（Validation n=5），不是任意 unseen-virus detector。
- 计算局限：NA：冻结比较没有 per-model peak_gpu_memory_source attestation。Timing 包含 2 个 comparability group，因此 panel c 是描述性的，不提出 Pareto frontier 结论。
- 图像完整性：全部 panel 都是程序化 quantitative vector graphic；不涉及 microscopy、photograph、crop、local contrast adjustment 或 pseudo-colour processing。
- 自动 export QA：PASS（发布前检查了尺寸和可编辑 SVG text）。
- Visual QA 状态：passed。
- 人工原始分辨率检查：全部五个 panel 均清晰可读，没有 clipping、overlap 或缺失 label。
- 绘制的数值 source 未改变；本次 refresh 保留修正后的冻结 Test policy。
- 仅更新 MCP 术语；已检查原始分辨率 PNG 是否存在 clipping、overlap，以及 label 是否完整。
