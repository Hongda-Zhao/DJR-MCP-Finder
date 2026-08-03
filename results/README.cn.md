[English](README.md) | **简体中文** | [日本語](README.ja.md)

# Git 中包含的结果

本仓库只跟踪阅读和审核已发布 V0 分析所需的精简、checksum-bound 证据：

- `figures/project_v0/`
- `validation_family_robustness_v0_schema5_mixed_heads/`
- public-checkout validator 和 `PROJECT_V0_RELEASE_CHECKSUMS.sha256` 所需的小型 checksum、fold
  与 comparison 文件

大型生成输出、embedding、原始 intermediate 文件和模型 cache 继续由根目录 `.gitignore` 排除。
在适用情况下，它们的 identity 保留在 release checksum 与 provenance 记录中。

特别需要注意，`data/processed/v0/CHECKSUMS.sha256` 和
`postsplit_integrity_v0/CHECKSUMS.sha256` 是 archive identity inventory。干净的 Git checkout
刻意不包含前者的 38 个 dataset target 或后者的 15 个 integrity-audit target；使用
`sha256sum -c` 运行这两个 manifest 前，必须先恢复 checksum-bound archive。
