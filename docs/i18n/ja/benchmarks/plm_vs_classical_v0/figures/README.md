<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/figures/README.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

[English](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/benchmarks/plm_vs_classical_v0/figures/README.md) | [简体中文](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/benchmarks/plm_vs_classical_v0/figures/README.cn.md) | **日本語**

# Benchmark の図

これらの図は、固定 endpoint や主張の境界を変えずに、検証済みの内部 cross-fitted Benchmark を可視化します。

Benchmark root から再生成します。

```bash
python figures/plot_benchmark.py
```

Primary output：

- `benchmark_summary.svg` — 編集可能な primary figure。
- `benchmark_summary.pdf`、`.png` — 現在の review・publication 用 export。600-dpi TIFF は full archive にあります。
- `benchmark_remote_homology.svg` と PDF/PNG export — 記述的な low-coverage/no-hit diagnostic。TIFF は archive のみです。
- `source_data/` — 検証済み結果表から得た、plot 対象 row の正確なデータ。
- `visualization_manifest.json` と `CHECKSUMS.sha256` — source binding と artifact hash。
- `FIGURE_CONTRACT.md`、`FIGURE_LEGEND.md`、`QA_REPORT.md` — claim、caption、統計上の caveat、final-size audit。

Sensitivity は、独立した calibration fold で 99.5% specificity を目標に選択した threshold を、evaluation fold で測定した値として解釈してください。すべての evaluation fold が 99.5% specificity を達成したという主張ではありません。
