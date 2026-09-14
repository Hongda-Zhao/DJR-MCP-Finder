[English](../../README.md) | **简体中文** | [日本語](README.ja.md)

[![CI](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Hongda-Zhao/DJR-MCP-Finder?display_name=tag&sort=semver&label=release&color=2ea44f)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

# DJR-MCP Finder

DJR-MCP Finder 从蛋白 FASTA 文件中筛选双果冻卷主要衣壳蛋白（double-jelly-roll major capsid protein，DJR-MCP）候选，为每条蛋白输出各阶段分数和最终标签，并在有足够支持时归入 Nucleocytoviricota 或 Preplasmiviricota。

- [Model V0.1 Candidate](../../user-inference-v0.1/README.cn.md) 是目前优先用于探索性筛查的实验候选模型。它用 ESM-2 3B 筛选 DJR/MCP，沿用 V0 冻结的 ESM-C 6B 输出头进行病毒门分类。
- [Model V0](../../user-inference-v0/README.cn.md) 是已发布、冻结的基线模型，全程使用 ESM-C 6B，仍受支持。

两个版本都尚未经过独立外部验证。

## 预测流程

![DJR-MCP Finder 预测流程](../assets/readme/readme_workflow.svg)

三个阶段依次识别 DJR 候选（H1）、区分 MCP 与其他 DJR 蛋白（H2），最后判断所属病毒门，或返回 `unknown/other`（H3）。两版的具体计算路径见上方用户指南。

## 快速开始

推荐使用 Linux、Docker、NVIDIA Container Toolkit，以及至少有 24 GB 显存、支持 BF16 的 CUDA GPU。普通 FASTA 预测不需要 HPC 调度系统。

```bash
git clone https://github.com/Hongda-Zhao/DJR-MCP-Finder.git
cd DJR-MCP-Finder/user-inference-v0
bash workstation/build.sh

cd ../user-inference-v0.1
DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh

bash workstation/run_user_fasta.sh \
  /absolute/path/to/proteins.faa \
  run_output/my_sample \
  0
```

先构建 V0，因为 V0.1 以它的 Docker 镜像为基础。将 `DJRMCP_EXPECTED_BASE_IMAGE_ID` 留空，可在本地重建后跳过历史镜像 ID 检查；版本、环境和校验和检查仍会执行。

第一次预测会下载固定版本的模型权重。

## 输出

结果保存在：

```text
run_output/my_sample/
├── predictions.tsv
├── run_metadata.json
└── CHECKSUMS.sha256
```

`predictions.tsv` 记录每条蛋白的分数、各阶段判定和最终标签。以下为 V0.1 的部分字段格式示例：

| protein_id | head1_djr_probability | head2_mcp_probability | head3_prediction | final_prediction |
| --- | ---: | ---: | --- | --- |
| candidate_001 | 0.997 | 0.981 | Nucleocytoviricota | `mcp::Nucleocytoviricota` |
| cellular_djr_002 | 0.994 | 0.082 | not_reached | `djr_non_mcp` |
| background_003 | 0.006 | NA | not_reached | `non_djr` |

五种标签为 `non_djr`、`djr_non_mcp`、`mcp::Nucleocytoviricota`、`mcp::Preplasmiviricota` 和 `mcp::unknown/other`。最后一种表示序列通过了 H1/H2，但无法可靠归入两个受支持的病毒门，不能据此认定发现了新病毒或未知病毒。

筛查结果需要后续结构或人工复核。分数未按自然样本中的实际流行率校正；大规模筛查还需独立评估假阳性。

## 模型评估

开发数据包含 11,060 条去除完全重复序列后的蛋白，划分为 Train（6,634）、Validation（2,212）和 Test（2,214）。下表仅使用 Train 数据，两版采用相同的五折划分，同一 component 的序列不会跨折。数值为均值 ± 标准误。

| 仅训练集五折交叉验证 | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: |
| H1 AP | `0.9985 ± 0.0003` | `0.9993 ± 0.0004` |
| H2 AP | `1.0000 ± 0.0000` | `1.0000 ± 0.0000` |
| H3 known-phylum macro-F1 | `0.9806 ± 0.0095` | `0.9806 ± 0.0095` |
| 综合分数 `S` | `0.9971 ± 0.0009` | `0.9976 ± 0.0010` |

`S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 macro-F1`。V0.1 的 H1 AP 均值略高，H2 AP 相同，H3 则复用同一模型。这些开发结果用于选择候选模型，不能据此认定差异具有统计显著性，也不能代表外部数据上的表现。

数据组成、14 个编码器的比较及其他评估见[科研证据说明](../SCIENTIFIC_EVIDENCE.cn.md)。

## 文档

- [Model V0.1 Candidate](../../user-inference-v0.1/README.cn.md) 与 [Model V0](../../user-inference-v0/README.cn.md) 用户指南
- [复现说明](../REPRODUCIBILITY.cn.md)：已发布的数据、模型和科研流程
- [代码架构](../ARCHITECTURE.cn.md)与[完整文档索引](../README.cn.md)

## 引用与许可

如在研究中使用 DJR-MCP Finder，请按照 [`CITATION.cff`](../../CITATION.cff) 引用，并注明使用的模型版本。

项目原创代码和文档采用 [MIT License](../../LICENSE)。
