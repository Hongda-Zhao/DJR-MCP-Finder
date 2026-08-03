<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/figures/QA_REPORT.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# 图表 QA 报告

状态：**PASS**。

## 科研与数据完整性

- 可视化与状态为 `PASS` 的已验证 `summary.json` 和 `validation.json` artifact 绑定。
- 全部 27 个 method–task primary-metric row 和全部 12 个预注册 paired comparison 均恰好出现一次。
- Paired panel 使用报告的 point estimate，以及来自 10,000 次 paired global-component bootstrap replicate 的 percentile 95% interval；没有绘制 P value 或 Holm field。
- Low-coverage panel 包含 `best_local_qcov_lt80` stratum 中全部 18 个 controlled method–task row。
- 不会为了方便绘图而采样或排除任何 record、method、task、fold 或 interval。
- Secondary/resource-augmented、metadata-augmented 和 operational track 在视觉与文字上继续与 controlled comparison 分离。

## Source preflight

严格的 static preflight 报告 14 个 PASS、0 个 WARN 和 0 个 FAIL：Python 语法有效、仅使用 Python backend、SVG/PDF 文字设置可编辑、使用 sans-serif font、检测到的最小字号为 5.2 pt、没有不安全的 rainbow map、导出 SVG/PDF/TIFF、600 dpi raster output、图宽 183 mm、未检测到 sampling 或 simulated data，且没有未受保护的 logarithmic transform。

## 导出与视觉检查

- 主图：183 × 215 mm；PNG/TIFF 为 4320 × 5070 pixel、600 dpi；SVG/PDF 保留可编辑文字。
- 补充图：183 × 86 mm；PNG/TIFF 为 4320 × 2040 pixel、600 dpi；SVG/PDF 保留可编辑文字。
- PDF page size 分别为 518.4 × 608.4 pt 和 518.4 × 244.8 pt。
- 导出后以原始分辨率检查了主图和补充图 PNG。Panel label、task label、method label、confidence interval、legend、color bar 和 footnote 均清晰可见，没有重叠或 clipping。
- 主图 SVG 包含 151 个 `<text>` node，补充图 SVG 包含 44 个；PDF 检查显示嵌入了 Arial TrueType/CIDFontType2 font。
- 白色背景、克制的非 rainbow palette 和 marker shape 使图表在不依赖颜色时仍可解释。

## 图中包含的统计与 reviewer caveat

- 99.5% 是 calibration-fold target，而不是假定的 evaluation specificity；实际 evaluation specificity 会明确展示。
- H2/end-to-end interval 使用空心 marker 显示，并标记为 conditional/resolution-limited，因为一个 negative source/fold 只有一个独立 component。
- Low-query-coverage panel 是描述性的，不是全局 evolutionary-distance analysis 或 matched-specificity superiority test。
- Benchmark 仍为内部且仅使用 Train；Validation/Test prediction count 均为零。

## 图像完整性声明

不使用 microscopy、photograph、gel 或其他 raster observation。Raster 文件是 vector/data graphic 的直接 600 dpi render；不涉及局部 contrast adjustment、selective masking、compositing 或 image reuse。
