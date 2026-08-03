<!-- i18n-mirror: non-authoritative translation; source=.github/pull_request_template.md -->

> **翻译说明：** 本译文仅供阅读；如有差异，以源语言原文为准。

## 摘要

<!-- 修改了什么、面向哪些人，以及为什么修改？ -->

## 范围

- [ ] 科研流程
- [ ] 正式 `model-v0` 推理
- [ ] `model-v0.1-candidate` 推理
- [ ] 文档/社区文件
- [ ] 打包或发布自动化

## 验证

<!-- 列出准确的命令和结果。优先使用 make targets。 -->

- [ ] `make lint`
- [ ] 相关测试
- [ ] 相关冒烟检查
- [ ] 打包元数据或捆绑文件发生变化时运行 `make package-check`
- [ ] 所有 GitHub Actions 检查均为绿色

## 科学与发布边界

- [ ] 本次修改未暗中改变冻结的 encoders、heads、thresholds、routing 或 evidence status。
- [ ] 任何受 checksum 约束的文件发生变化时，均同步更新其所属的 checksum manifest。
- [ ] identifier 或 version 发生变化时，`release-manifest.json`、`docs/VERSIONING.md` 和 `docs/repository/CHANGELOG.md` 保持一致。
- [ ] 面向用户的声明仍限定在 `docs/SCIENTIFIC_EVIDENCE.md` 所规定的范围内。

## 安全与数据

- [ ] 未包含 secrets、private sequences、checkpoints、raw datasets、caches 或生成的 environments。
- [ ] 新增的 input、path、deserialization 和 overwrite 行为均经过明确的安全审查。

## 审查者备注

<!-- 剩余风险、有意推迟的工作，或需要手动完成的 GitHub/PyPI 配置。 -->
