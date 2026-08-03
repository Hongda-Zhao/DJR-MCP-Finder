<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/figures/FIGURE_CONTRACT.md -->

本译文仅供阅读；冻结的英文源文档为权威版本。

# 图表合同

核心结论：可以在 component-held-out 和由 BLAST 定义的困难蛋白上估计 v0.1 encoder 变更，
但目前严格的 <20% identity cohort 太小，无法支持 ultra-remote 优越性声明。

- 图表原型：quantitative grid，以 paired-delta panel 为主要视觉区域。
- 目标/输出：manuscript/report figure；可编辑 SVG 和 PDF、600-dpi TIFF 与 preview PNG。
- Backend：仅使用 Python（matplotlib）。
- 最终尺寸：宽 180 mm，高约 145 mm。
- Panel a：全部 holdouts、20–30% identity twilight layer 和 low-coverage stress 的 paired
  v0.1 minus v0 sensitivity delta，并显示 95% descriptive bootstrap CI。
- Panel b：low-coverage stress stratum 中所选 PLM 与 classical methods 的 absolute sensitivity，
  使用 calibration-fold-locked thresholds。
- Panel c：全部 component-held-out rows 上 FPR <=0.005 的 normalized partial AUROC。省略没有
  足够 per-source negative-component resolution 的 endpoints。
- Panel d：independent-component count 与预冻结 adequacy thresholds 的比较。
- 统计：仅在 total n >=30 且每个 fold n >=5 时使用 paired component bootstrap；严格 <20%
  strata 不给出 CI 或 superiority inference。
- Source data：每个绘制的点都必须存在于 `figures/source_data/`。
- Reviewer 风险：BLAST-derived strata 受 method 条件限制；实际 evaluation specificity 可能未达到
  99.5% 目标；H2 有一个 evaluation fold 仅包含一个 negative component；当前 benchmark 只是
  Train-only development evidence。空心符号表示任一系统未达到实际 specificity gate 的 paired
  delta；fixed-threshold bootstrap interval 不包含 calibration uncertainty。
