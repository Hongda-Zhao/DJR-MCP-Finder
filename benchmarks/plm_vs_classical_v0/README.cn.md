[English](README.md) | **简体中文**

# PLM 与经典远程同源方法 benchmark

> **内部交叉拟合开发 BENCHMARK——不是外部 TEST**

这个活动目录是精简的出版物/checksum 核心。它保留冻结 protocol、配置、代码、精简结果表、验证记录、
作图源数据，以及 PNG/PDF/SVG 输出。输入、原始 receipts、检索数据库、日志、逐行 ledger 和 TIFF
导出仍以 checksum 绑定在 `FULL_ARTIFACT_POINTER.json` 指向的完整 archive 中；没有删除数据。

本目录在冻结的 DJR-MCP-Finder Train split 上比较项目的蛋白语言模型（PLM）系统与序列和 profile
检索 baseline。它从不评估 protected Test split。五个既有 `global_component_id` fold 以循环
3/1/1 设计复用：每个 cycle 用三个 fold 构建数据库/模型，一个不相交 fold 校准 operating threshold，
另一个不相交 fold 用于评估。校准与评估使用完全相同的数据库/模型，但均不进入拟合。

Benchmark 刻意分成两条独立轨道：

1. **受控 retrieval：** ESM-C/ESM-2 最大 cosine similarity、BLASTP、DIAMOND、MMseqs2、
   HMMER 和 PSI-BLAST 使用相同的 fold-specific positive reference ID。
2. **Operational supervised system：** ESM-C 6B embedding 使用项目冻结的 H1/H2 classifier
   设置进行拟合。该轨道还会从标注 negative 中学习，因此不能用来把增益单独归因于 PLM representation。

三个 endpoint 分别是 DJR detection（H1）、VMA 与 cellular DJR 的区分（H2），以及 end-to-end
VMA detection。主要指标是 fold-macro component-balanced AP，以及在 99.5% source-balanced
specificity 校准目标下的 sensitivity。99.9% endpoint 仅作为受分辨率限制的次要证据报告。

聚合前 audit 还发现 fold 3 的 62 个 cellular-DJR negative 属于同一个 component。受影响的
H2/end-to-end 低 FPR sensitivity interval 会保留，但明确标为 conditional 且 resolution-limited；
详见 `PROTOCOL.md`。与 score 无关的计数和泄漏检查记录在 `DATA_AUDIT.md`。

## 验证精简核心

```bash
cd /path/to/DJR-MCP-Finder/benchmarks/plm_vs_classical_v0
sha256sum -c CHECKSUMS.sha256
```

`results/validation.json` 是冻结的完整 validator 成功记录。精简副本刻意不能重放完整 validator 或
检索流程，因为它们的原始输入和 receipts 仅存在于 archive 中。GitHub 中的 `pbs/` launcher 是可移植
的重放模板，但不是独立 runner：若要精确端到端重放，请遵循 `FULL_ARTIFACT_POINTER.json` 并在提交
任务前恢复其中的 `full_v1` 目录树。不要把这个精简 source checksum 重新解释为完整 pipeline 或科学
结果 checksum。

冻结的科学合同见 `PROTOCOL.md`；机器可读路径、checksum、参数和工具版本见
`config/benchmark.json`。

在其他系统上恢复完整 archive 后，请保留检入的 config 作为 provenance，并从仓库根目录生成运行副本：

```bash
python scripts/render_portable_config.py \
  benchmarks/plm_vs_classical_v0/config/benchmark.json \
  build/local-configs/plm_vs_classical_v0.json
```

先设置 `DJRMCP_PROJECT_ROOT`、`DJRMCP_ARCHIVE_ROOT`、`DJRMCP_SOFTWARE_ROOT` 和
`DJRMCP_VENV_ROOT`，再把生成的路径作为 `DJRMCP_PLM_CONFIG` 传入。PBS launcher 会从这些变量
（或自身位置/`PBS_O_WORKDIR`）解析 checkout，而不要求使用历史 gds2 项目路径。

Headline controlled track 从不把 supervised classifier 与 retrieval tool 混在一起。Supervised
ESM-C、按 metadata 分组的 HMM，以及迭代 PSI-BLAST 均在明确标注的 supplementary track 中报告。
