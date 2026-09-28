<!-- i18n-mirror: non-authoritative translation; source=docs/repository/CHANGELOG.md -->

> **翻译说明：** 本译文仅供阅读；如有差异，以源语言原文为准。

# 变更日志

DJR-MCP Finder 所有值得记录的工程变更均记录于此。科学证据的修订仍由其冻结的 protocols 和
checksum manifests 管理。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)。仓库发布采用简洁的
`MAJOR.MINOR` 标签；可安装的 Python distributions 保留各自独立的 PEP 440 versions。

## [未发布]

## [0.2] - 2026-09-28

### 新增

- Train 内按 component 隔离的短序列 benchmark，支持校验后复用 embedding、
  配对截短准备与原始长度评测。
- 560 条 MCP 阳性长度统计，其中 Train 336 条；保留集只检查长度，不做评分。
- <250、250–299、300–349、350–399、400–449、450–499、≥500 aa 汇总表及英文图。
  V0.1 在 Train 检出 331/336 条 MCP，假阳性为 0/6,298；配对截短性能仍待完成。
- 可选入口 `djrmcp-predict-v02-preview`：<250 aa 输出 `mcp_unreliable_short_sequence`，
  分数 `NA`，跳过模型；≥250 aa 原样使用冻结 V0.1。该标签是不予判定，不是 MCP 阴性。
- 三语 V0.2 策略与设计文档；首页按既有对照表样式展示性能、样本数、证据限制和英文图。

### 变更

- 软件发布升级为 `v0.2`，研究包为 `0.2.0`，候选推理包为 `0.3.0`；正式 V0 包仍为 `0.1.0`。
- 同步引用元数据和版本映射；科学模型 ID、冻结权重、校准与 bundle 不变，没有训练科学模型 V0.2。
- 主图去掉重复的 FP 列，总体假阳性保留在图注。

### 验证

- 本地通过 236 项核心测试、33 项正式 V0 测试和 69 项候选推理测试，共 338 项。
- 文档、元数据、关键 Ruff 检查与三个包的 wheel/sdist 检查通过。
- 新测试覆盖长度边界、混合输入顺序、跳过模型、非法 FASTA、分数透传、校验和及覆盖行为。

### v0.1 之后的其他工程更新


### 新增

- 分层的 `docs/` 信息架构和机器可读的 release manifest。
- 在三种首页语言中提供稳定的顶层目录功能表。
- 统一的 `make setup/test/lint/smoke/build/check` 贡献者命令。
- 由 tag 触发的 package build 和 GitHub Release artifact 工作流。

### 变更

- Python package metadata 现采用 SPDX/PEP 639 licensing、完整的 project URLs、typed-package
  markers，以及由 metadata 提供的 runtime versions。
- 首页 README 现以采用和使用为重点；详细的科学与可复现性材料移至 `docs/`。
- V0.1 现为当前首选结果，而已发布的 V0 仍是一等的可复现 baseline 和 fallback；两者继续以各自
  不同的 release statuses 显示。
- 当前推理输出采用 MCP 术语（`head2_mcp_probability`、`djr_non_mcp` 和 `mcp::...`）；归档的
  benchmark identifiers 为保证可复现性而保持不变。
- 首页现先展示冻结的 V0 model-selection benchmark，再展示 V0/V0.1 remote-component
  development audit，并将 V0.1 标识为当前首选结果。
- 根目录下的科学 workflow、report 和 robustness protocol 文档已移至 `docs/research/`；文档检查会
  防止根目录 Markdown 再度膨胀。
- 辅助首页翻译、变更日志和仓库级第三方声明现统一放在 `docs/repository/`；根目录只保留主要的
  英文 Markdown README。

### 移除

- 从公开文档中移除独立的贡献和安全策略页面；issue 与 pull-request 模板仍保留在 `.github/`。

## [0.1] - 2026-07-30

### 新增

- 首个正式 GitHub release，包含冻结的 `model-v0` user-inference package。
- 双语首页 README、MIT license、citation metadata、third-party notices 和 baseline CI。

[未发布]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.2...HEAD
[0.2]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.1...v0.2
[0.1]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1
