[English](README.md) | **简体中文** | [日本語](README.ja.md)

# Git 中包含的结果

本仓库只跟踪阅读和审核已发布 V0 分析所需的精简、checksum-bound 证据：

- `figures/project_v0/`
- `validation_family_robustness_v0_schema5_mixed_heads/`
- 公开仓库验证程序所需的小型校验和、数据折和比较文件

大型生成输出、嵌入、原始中间文件和模型缓存继续由根目录 `.gitignore` 排除。在适用情况下，
它们的身份信息保留在专用的数据集、模型、基准测试或结果清单中。

特别需要注意，`data/processed/v0/CHECKSUMS.sha256` 和
`postsplit_integrity_v0/CHECKSUMS.sha256` 是 archive identity inventory。干净的 Git checkout
刻意不包含前者的 38 个 dataset target 或后者的 15 个 integrity-audit target；使用
`sha256sum -c` 运行这两个 manifest 前，必须先恢复 checksum-bound archive。
