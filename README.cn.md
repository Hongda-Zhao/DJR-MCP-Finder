[English](README.md) | **简体中文**

# DJR-MCP Finder

[![CI](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml/badge.svg)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Release](https://img.shields.io/github/v/release/Hongda-Zhao/DJR-MCP-Finder?display_name=tag)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**使用冻结的三级蛋白语言模型分类器，从蛋白 FASTA 中检测 double-jelly-roll major capsid
protein。** DJR-MCP Finder 面向病毒学与生物信息学使用者，提供可审计的 DJR、病毒形态发生相关
DJR 及两个受支持病毒门的第一轮筛查。

## 两条当前主要结果线

V0 与 V0.1 都是项目当前的主要结果。两者处理相同的三级任务，但使用不同的冻结 encoder 系统，
并提供相互独立的命令行包。

| 结果 | 冻结系统 | 状态 | 用户入口 |
| --- | --- | --- | --- |
| **Model V0** | H1/H2/H3 均使用 ESM-C 6B | 已发布、可复现的基线 | [`djrmcp-predict`](user-inference-v0/README.cn.md) |
| **Model V0.1** | H1/H2 使用 ESM-2 3B；H3 使用 ESM-C 6B | 当前 mixed-encoder 结果；需要外部确认 | [`djrmcp-predict-v01`](user-inference-v0.1/README.cn.md) |

两个版本在推理时都不会训练或重新调参。V0.1 与 V0 并列展示，但不会改写已发布 V0 bundle 的
身份和证据记录。

## 从 FASTA 到可审计结果

```mermaid
flowchart LR
    A["蛋白 FASTA"] --> B["选择冻结的 V0 或 V0.1 bundle"]
    B --> H1{"H1：是否为 DJR？"}
    H1 -- "否" --> N["non_djr"]
    H1 -- "是" --> H2{"H2：是否与 VMA 相关？"}
    H2 -- "否" --> D["djr_non_vma"]
    H2 -- "是" --> H3{"H3：是否属于受支持的门？"}
    H3 --> P1["vma::Nucleocytoviricota"]
    H3 --> P2["vma::Preplasmiviricota"]
    H3 --> U["vma::unknown/other"]
```

`vma::unknown/other` 只是通过 H1/H2 后的 reject option，不是普适未知病毒或 OOD detector。

## 核心 benchmark 概览

![V0 与 V0.1 remote-component 开发 benchmark](benchmarks/ultra_remote_v0_v01/figures/ultra_remote_v0_v01.svg)

在仅使用 Train 的 component holdout 中，V0.1 将 H1 encoder sensitivity 从 `0.734` 提升到
`0.924`，FPR ≤0.005 下的 normalized partial AUROC 从 `0.655` 提升到 `0.889`；task-adapted
H1 detector 从 `0.975` 变为 `0.994`，而本次审计中的 H2 与端到端 detector sensitivity 持平。
这些是内部、固定阈值的开发结果：每组配对系统都至少在一个 fold 未达到实际 99.5% specificity，
严格 `<20% identity` 分层也只有 1 个独立阳性 component。完整解释见
[benchmark 报告](benchmarks/ultra_remote_v0_v01/results/REPORT.md)和
[科研证据边界](docs/SCIENTIFIC_EVIDENCE.md)。

## 快速开始：两个版本的仅 CPU 合同检查

Python 3.12+ 可以在不下载 encoder 或 PyTorch 的情况下校验两个结果版本：

```bash
git clone https://github.com/Hongda-Zhao/DJR-MCP-Finder.git
cd DJR-MCP-Finder

python3.12 -m venv .venv
source .venv/bin/activate

make setup-v0 setup-v01
make test-v0 smoke-v0
make test-v01 smoke-v01
```

尚未验证原生 Windows。完整推理使用 Linux、Docker 与 NVIDIA GPU；请分别阅读
[V0 工作站指南](user-inference-v0/workstation/README.cn.md)或
[V0.1 工作站指南](user-inference-v0.1/workstation/README.cn.md)。V0 建议至少 24 GB GPU 显存；
V0.1 使用两个相互隔离、固定版本的 encoder runtime。

## 输出示例

每次运行生成 `predictions.tsv`、`run_metadata.json` 和 `CHECKSUMS.sha256`。下表仅展示 schema，
不是 benchmark 结果。

| protein_id | H1 DJR 概率 | H2 VMA 概率 | H3 prediction | final_prediction |
| --- | ---: | ---: | --- | --- |
| candidate_001 | 0.997 | 0.981 | Nucleocytoviricota | `vma::Nucleocytoviricota` |
| cellular_djr_002 | 0.994 | 0.082 | not_reached | `djr_non_vma` |
| background_003 | 0.006 | 0.021 | not_reached | `non_djr` |

完整输入输出合同见 [V0](user-inference-v0/README.cn.md) 与
[V0.1](user-inference-v0.1/README.cn.md) 用户指南。

## Release、模型与包版本

以下标识描述不同层次，不应互换：

| 层次 | 当前标识 | 含义 |
| --- | --- | --- |
| 仓库 release | [`v0.1.0`](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1.0) | GitHub 软件发布的 SemVer |
| 科学结果 | `model-v0` | [`user-inference-v0/`](user-inference-v0/README.cn.md) 中已发布的全 ESM-C-6B 结果 |
| 科学结果 | `model-v0.1-candidate` | [`user-inference-v0.1/`](user-inference-v0.1/README.cn.md) 中当前的 mixed-encoder 结果；需要外部确认 |
| Bundle revision | `model-v0-esmc6b-r1` | 不可变模型内容与 export revision |
| Python distribution | 例如 `djrmcp-user-inference==0.1.0` | 单个可安装包的 PEP 440 版本 |

完整规则与机器可读映射见 [`docs/VERSIONING.md`](docs/VERSIONING.md) 和
[`release-manifest.json`](release-manifest.json)。

## 选择正确入口

| 目标 | 入口 | 环境 |
| --- | --- | --- |
| 使用已发布的 V0 结果 | [`user-inference-v0/`](user-inference-v0/README.cn.md) | Python 3.10+ 检查；Linux/Docker/NVIDIA 推理 |
| 使用当前 V0.1 结果 | [`user-inference-v0.1/`](user-inference-v0.1/README.cn.md) | Python 3.12+、两个隔离模型环境 |
| 审计研究证据 | [科研证据与限制](docs/SCIENTIFIC_EVIDENCE.md) | 证据层次、指标和 claim boundary |
| 从本地 archive 复现 | [复现指南](docs/REPRODUCIBILITY.md) | 冻结输入、软件和 HPC 资源 |
| 贡献代码或文档 | [`CONTRIBUTING.md`](CONTRIBUTING.md) | Python 3.12+ contributor 环境 |

## 贡献者统一命令

根目录 `Makefile` 是本地开发的统一入口：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make setup
make check
```

运行 `make help` 可查看 `setup`、`test`、`lint`、`smoke`、`build` 与包验证等独立 target。
CI 使用相同的 target-level contract。

## 文档导航

- [文档地图](docs/README.md)
- [架构与命令清单](docs/ARCHITECTURE.md)
- [科研证据与限制](docs/SCIENTIFIC_EVIDENCE.md)
- [研究复现](docs/REPRODUCIBILITY.md)
- [版本与发布命名](docs/VERSIONING.md)
- [引用信息](CITATION.cff)
- [变更记录](CHANGELOG.md)

## 科学与许可边界

V0 与 V0.1 都没有新的 prospective external Test。当前分数是在开发数据分布下校准的 model
score，不是自然蛋白组中的 prevalence-adjusted probability。大规模发现仍需独立假阳性评估及结构/人工
验证。解释结果前请阅读[科研证据与限制](docs/SCIENTIFIC_EVIDENCE.md)。

项目原创材料采用 [MIT License](LICENSE)。外部 checkpoint、软件、数据集、数据库内容和商标保留各自
条款，不因本仓库而重新授权。参见[第三方声明](THIRD_PARTY_NOTICES.md)和[安全策略](SECURITY.md)。
