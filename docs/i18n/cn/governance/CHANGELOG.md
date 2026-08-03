<!-- i18n-mirror: non-authoritative translation; source=docs/repository/CHANGELOG.md -->

> **翻译说明：** 本译文仅供阅读；如有差异，以源语言原文为准。

# 变更日志

DJR-MCP Finder 所有值得记录的工程变更均记录于此。科学证据的修订仍由其冻结的 protocols 和
checksum manifests 管理。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)。仓库发布采用简洁的
`MAJOR.MINOR` 标签；可安装的 Python distributions 保留各自独立的 PEP 440 versions。

## [未发布]

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

[未发布]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.1...HEAD
[0.1]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1
