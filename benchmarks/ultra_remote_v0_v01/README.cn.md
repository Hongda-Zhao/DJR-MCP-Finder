[English](README.md) | **简体中文**

# Ultra-remote benchmark：v0 与 v0.1

这是独立、fail-closed 的开发 audit。它不修改已经发布的 `plm_vs_classical_v0` benchmark，也不
打开 Validation 或 Test。

这个活动目录是精简的出版物/checksum 核心。它保留 protocol、配置、代码、精简结果、小型复现合同、
作图源数据，以及 PNG/PDF/SVG 输出。逐行 diagnostic、日志和 TIFF 导出仍以 checksum 绑定在
`FULL_ARTIFACT_POINTER.json` 指定的完整 archive 中；没有删除数据。

## 实际比较内容

| 层 | v0 | v0.1 candidate | 公平比较 |
|---|---|---|---|
| H1/H2 encoder | ESM-C 6B | ESM-2 3B | 相同 positive reference ID，maximum cosine |
| H1/H2 detector | ESM-C 6B + frozen classifier family | ESM-2 3B + 相同 classifier family | 相同的循环 3-fit/1-calibration/1-evaluation fold 和 hyperparameter |
| H3 phylum head | ESM-C 6B | 相同 ESM-C 6B | 排除：没有变化，且不是 homology-detection endpoint |

Cosine 层询问 representation 本身能否检索 held-out component。Supervised 层询问 operational
H1/H2 detector 能否使用该 representation。经典工具保留 parent benchmark 中原有的冻结 score 和
information-budget label。

## Ultra-remote 边界

当前数据只有一个 positive independent component 同时满足 best BLAST query coverage 至少 80%
且 identity 低于 20%。因此该 stratum 是 case series，不是 inferential benchmark。`qcov < 80%`
有足够数量进行描述性 stress test，但它只是低覆盖 proxy，不能证明 ultra-remote homology。其定义还
来自被比较方法之一 BLAST，因此不能支持另一种方法优于 BLAST 的正式结论。

Release-grade ultra-remote benchmark 仍应留给 external lockbox；其 label 和 distance stratum 应
独立于所有被比较方法冻结，最好来自结构、实验或人工证据。

## 验证精简核心

```bash
cd /path/to/DJR-MCP-Finder/benchmarks/ultra_remote_v0_v01
sha256sum -c CHECKSUMS.sha256
```

`results/validation.json` 是冻结的完整 validator 成功记录。这个精简目录无法重放 active validator，
因为原始逐行 score ledger 与 TIFF contract 仅存在于 archive 中。GitHub `pbs/` launcher 是可移植
重放模板，不是独立 runner。若要精确重放 scoring、rendering 和 validation，请先遵循
`FULL_ARTIFACT_POINTER.json` 并恢复其 `full_v1` 目录树。Ultra script 还会读取 parent PLM 的输入、
query score 与经典工具 receipt，因此也需要把 `../plm_vs_classical_v0/FULL_ARTIFACT_POINTER.json`
指定的 PLM 目录树恢复到其记录的活动路径。Visualization manifest 记录精简 rendering 输出和源数据
checksum。

在其他系统上恢复这些 archive 后，请从仓库根目录使用 `scripts/render_portable_config.py` 生成本地
config，把 `DJRMCP_ULTRA_CONFIG` 指向该副本，并设置 `DJRMCP_PROJECT_ROOT`、
`DJRMCP_ARCHIVE_ROOT` 和 `DJRMCP_VENV_ROOT`。检入的 JSON 仍是原始 gds2 运行的不可变记录。
