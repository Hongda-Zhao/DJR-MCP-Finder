[English](README.md) | **简体中文**

# Benchmark 图

这些图展示已验证的内部交叉拟合 benchmark，不改变其冻结 endpoint 或 claim boundary。

从 benchmark 根目录重新生成：

```bash
python figures/plot_benchmark.py
```

主要输出：

- `benchmark_summary.svg`——可编辑主图。
- `benchmark_summary.pdf`、`.png`——活动审阅和出版导出；600-dpi TIFF 位于完整 archive 中。
- `benchmark_remote_homology.svg` 及 PDF/PNG 导出——描述性的低覆盖/no-hit diagnostic；TIFF
  仅在 archive 中。
- `source_data/`——从已验证结果表导出的精确作图行。
- `visualization_manifest.json` 和 `CHECKSUMS.sha256`——源绑定与 artifact hash。
- `FIGURE_CONTRACT.md`、`FIGURE_LEGEND.md` 和 `QA_REPORT.md`——claim、图注、统计限制和
  最终尺寸 audit。

Sensitivity 应解释为：在不相交 calibration fold 上选择以 99.5% specificity 为目标的 threshold，
再在 evaluation fold 上测量的结果。这并不表示每个 evaluation fold 都实际达到 99.5% specificity。
