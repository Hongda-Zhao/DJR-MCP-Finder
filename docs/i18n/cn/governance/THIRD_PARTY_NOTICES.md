<!-- i18n-mirror: non-authoritative translation; source=docs/repository/THIRD_PARTY_NOTICES.md -->

> **翻译说明：** 本译文仅供阅读；如有差异，以源语言原文为准。

# 第三方声明与许可证范围

除非文件另有说明，根目录的 [`LICENSE`](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/LICENSE)
适用于项目自行创作的源代码、文档、配置、图表和原创的捆绑线性分类器 head artifacts。

该许可证不会为外部 model checkpoints、software、datasets、protein sequences、structures、database
content 或 trademarks 重新授予许可。这些材料仍受其各自条款约束。本仓库中的 references、accessions、
checksums 和衍生科学结果，并不表示底层第三方源材料以 MIT 许可重新分发。

## 模型与运行时软件

| 组件 | 上游条款 | 在本仓库中的分发方式 |
| --- | --- | --- |
| [`Biohub/ESMC-6B`](https://huggingface.co/Biohub/ESMC-6B) | MIT；请查阅上游 model card 和 [Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/) | Checkpoint 需另行下载，本仓库不重新分发。 |
| [`Biohub/transformers`](https://github.com/Biohub/transformers) | Apache-2.0 | 从固定的上游 Git revision 安装；不包含 vendored source。 |
| [`facebook/esm2_t36_3B_UR50D`](https://huggingface.co/facebook/esm2_t36_3B_UR50D) | MIT | 仅由尚未发布的 V0.1 candidate 使用；checkpoint 需另行下载。 |
| `pyproject.toml` 文件中声明的 Python dependencies | 每个 dependency 保留其上游 license 和 notices。 | 通过 Python package tooling 安装；本仓库不包含 vendored source。 |

正式 V0 bundle 还在
[`user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md`](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md)
附带一份特定于该 release 的声明。

## 数据与数据库引用

研究 workflow 记录 NCBI、UniProt、AlphaFold DB、ICTV materials、MGnify 和站点本地 archives 等外部
资源的 provenance。用户必须从其权威提供方获取这些资源，并遵守提供方当前的 licenses、attribution
requirements、access policies 和 terms of use。精简的 GitHub release 不会授予对这些外部资源的
额外权利。
