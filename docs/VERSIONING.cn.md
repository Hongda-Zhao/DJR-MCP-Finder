# 版本与命名约定

[English](VERSIONING.md) | **简体中文** | [日本語](VERSIONING.ja.md)

[文档导航](README.cn.md) | [仓库 README](repository/README.cn.md) |
[发布清单](../release-manifest.json)

本项目包含软件 Release、Python distribution、科学模型、冻结 artifact bundle 以及数据整理版本。
它们各自按不同节奏更新，因此无法用同一个版本号安全地表示所有层次。

## 简要说明

| 用户可见名称 | 机器标识 | 含义 |
| --- | --- | --- |
| **Model V0.1 Candidate** | `model-v0.1-candidate` | 探索性筛查的优先实验候选；仍待独立外部验证 |
| **Model V0** | `model-v0` | 已发布并冻结的科学基线，同时作为受支持的备用方案 |
| 仓库 Release `v0.1` | `repository_release.tag` | GitHub 软件 Release 的版本，并非科学模型结论 |
| Candidate 包 `0.2.1` | `djrmcp-user-inference-v01==0.2.1` | Candidate 推理 distribution 的工程修订版本，并不表示“Model V0.2” |

机器元数据和证据记录必须始终使用完整科学 ID `model-v0.1-candidate`。面向用户的导航只有在相邻表格或句子明确说明其是等待外部确认的 Candidate 时，才可以使用较短的 **V0.1**。正式显示名为 **Model V0.1 Candidate**。

优先使用 Model V0.1 Candidate 进行新筛查，并不意味着它已经成为正式确认的模型，也不表示 Model V0 已被弃用。

## 规范层次

| 层次 | 格式 | 示例 | 何时变更 |
| --- | --- | --- | --- |
| 仓库/软件 Release | `vMAJOR.MINOR` | `v0.1` | GitHub 软件 Release 系列发生变化时 |
| Python distribution | PEP 440 版本 | `djrmcp-user-inference==0.1.0` | 对应的可安装包发生变化时 |
| 科学模型 | `model-v<scientific line>[-candidate]` | `model-v0`、`model-v0.1-candidate` | 冻结模型身份或证据状态发生变化时 |
| Bundle 修订 | `<model-id>-<encoder>-rN` | `model-v0-esmc6b-r1` | 导出文件或打包修订发生变化时 |
| 数据整理 | `data-curation-vN` | `data-curation-v3` | 数据集构建约定发生变化时 |

在元数据中使用小写机器 ID，在科学文本中使用上述正式显示名。

## 当前映射

| 组件 | 版本 / ID | 状态 |
| --- | --- | --- |
| GitHub 仓库 | `v0.1` | 已发布的软件快照 |
| 研究流程 distribution | `djrmcp-finder==0.1.0` | Alpha 软件 |
| 正式推理 distribution | `djrmcp-user-inference==0.1.0` | 打包 `model-v0` |
| Candidate 推理 distribution | `djrmcp-user-inference-v01==0.2.1` | `model-v0.1-candidate` 的工程修订版本 |
| 正式 bundle | `model-v0-esmc6b-r1` | 已发布并冻结 |
| Candidate bundle | `model-v0.1-mixed-r1` | 需要外部确认 |

Candidate 包版本 `0.2.1` 并不表示该科学模型已作为 V0.2 发布。包版本不会被降级，也不会被强制设为与仓库 tag 相同。

## 机器可读的权威来源

[`release-manifest.json`](../release-manifest.json) 是这些层次之间唯一的紧凑映射。以下命令会验证它是否与每个 `pyproject.toml`、运行时版本来源、`py.typed` 标记、bundle `release.json` 和科学状态字段一致：

```bash
python scripts/check_project_metadata.py
```

不要在 `__init__.py` 中再次写入包版本。运行时代码通过 `importlib.metadata` 读取已安装的 distribution 元数据；未安装的源码 checkout 会报告 `0.0.0.dev0`，而不会伪装成已发布版本。

## 变更规则

### 仓库 Release

仓库 Release 使用简洁的 `MAJOR.MINOR` 标签。向后兼容的能力和已打包 Candidate 变更增加 MINOR；不兼容的公共 CLI、输出 schema 或包 API 变更增加 MAJOR。补丁级工程修订继续体现在 Python distribution 和 bundle 版本中，而不会为仓库 Release 增加第三段版本号。

在 `release-manifest.json` 中更新仓库版本和 tag，更新 `docs/repository/CHANGELOG.md`，通过
`make check`，合并到 `main`，然后创建对应的 annotated tag。

### Python distribution

只修改发生变化的 distribution。更新其 `pyproject.toml` 以及 `release-manifest.json` 中对应的条目。包级 Release Candidate 使用 PEP 440 预发布版本，例如 `0.3.0rc1`。绝不能从包版本推断科学证据状态。

### 科学模型

新的模型 ID 必须具备冻结的模型卡、完整的 bundle 元数据与 checksum、明确声明的证据状态，并满足 [`WORKFLOW_V0.md`](research/WORKFLOW_V0.md) 中的科学发布门槛。若工程重构保留了所有冻结参数，则不会产生新的模型 ID。

### Bundle 修订

当导出文件或非模型 bundle 元数据发生变化、而模型行为保持不变时，增加 `rN`。如果分类器权重、阈值、路由或 encoder 发生变化，应创建新的科学模型身份，而不是把变化隐藏在 bundle 修订中。

## Tag Release 门槛

Release workflow 只接受与清单中仓库 tag 匹配的 tag。它会构建并验证三个 distribution 的 wheel 和 sdist，然后将它们附加到 GitHub Release。PyPI 上传功能有意保持禁用，直到包名完成预留，并通过受保护的 GitHub environment 配置 Trusted Publishing。

## 中文摘要

仓库 Release、Python 包、科学模型和 bundle revision 是不同层次。当前正式显示名为 **Model V0.1 Candidate**，机器 ID 必须写作 `model-v0.1-candidate`；它是探索性筛查的优先实验候选，但仍待独立外部验证。**Model V0**（`model-v0`）仍是已发布、冻结的正式基线。仓库 tag `v0.1` 与 candidate package `0.2.1` 都不是科学模型证据状态。所有映射由 `release-manifest.json` 集中维护并由 CI 校验。
