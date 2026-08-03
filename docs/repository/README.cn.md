[English](../../README.md) | **简体中文** | [日本語](README.ja.md)

[![CI](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Hongda-Zhao/DJR-MCP-Finder?display_name=tag&sort=semver&label=release&color=2ea44f)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

# DJR-MCP Finder

**从蛋白 FASTA 中筛选 double-jelly-roll major capsid protein（DJR-MCP）候选，并判断其是否属于项目支持的病毒门。**

DJR-MCP 是 *Varidnaviria* 的特征性衣壳蛋白。即使明显的序列相似性已经减弱，其 double-jelly-roll 结构信号仍可能保留，因此可作为发现和分类多样 DNA 病毒的重要标志。

| 输入 | 输出 | 适用人群 |
| --- | --- | --- |
| 氨基酸 FASTA | 每条蛋白的 DJR/MCP 分数与最终标签 | 希望筛查病毒蛋白或 contig 预测蛋白的病毒学和生物信息学用户 |

> **Model V0.1 Candidate 是当前优先用于探索性筛查的实验候选模型；Model V0 是已发布、冻结且可复现的基线。** V0.1 仍待独立外部验证，不取代也不弃用 V0。

## 预测流程

![DJR-MCP Finder prediction workflow](../assets/readme/readme_workflow.svg)

两版均按 H1→H2→H3 作最终决策，但实际计算路径不同。Model V0 利用一次共享的 ESM-C 6B 表征为每条序列计算 H1 和 H2 原始分数；只有 H1 阳性时，H2 结果才参与实际级联。Model V0.1 对所有序列计算 H1，仅对 H1 阳性序列计算 H2。两版都只对 H1/H2 双阳性序列计算 H3。所有分数、门控状态和最终标签均写入 `predictions.tsv`；这些标签用于筛查，不代表结构确认。

## 快速开始

推荐环境：Linux、Docker、NVIDIA Container Toolkit 和 CUDA GPU；建议至少 24 GB 显存并支持 BF16。

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

V0.1 使用 V0 的冻结镜像作为基础，因此首次克隆仓库后需要先完成 V0 构建。上面的空值只跳过本地重建后必然变化的历史 Docker 镜像 ID 检查；版本、环境和校验和检查仍会执行。预测主体由 Python 实现，Docker 用于隔离 H1/H2 与 H3 所需的两个固定运行环境。

普通 FASTA 预测不需要 PBS、`qsub` 或 HPC 调度系统。

第一次预测会下载固定版本的模型权重。结果位于：

```text
run_output/my_sample/
├── predictions.tsv
├── run_metadata.json
└── CHECKSUMS.sha256
```

最终标签为 `non_djr`、`djr_non_mcp`、`mcp::Nucleocytoviricota`、`mcp::Preplasmiviricota` 或 `mcp::unknown/other`。其中 `mcp::unknown/other` 仅表示序列通过 H1/H2，但 H3 未将其可靠分入两个受支持的病毒门；它不是通用的未知病毒检测器。

## 核心开发性能与 Benchmark

开发证据按“数据组成 → 评估设计 → V0 模型选择 → V0/V0.1 对比”展开。

### 开发数据

![Development data composition and component-safe frozen split](../assets/readme/readme_development_data.svg)

四个证据组共包含 11,060 条去除完全重复序列后的代表蛋白，冻结拆分为 Train 6,634、Validation 2,212 和 Test 2,214。Validation/Test 是开发数据内的冻结分区；下面的模型选择只使用 Train，并不构成新的独立外部测试。

### 共享五折设计

![Shared component-safe five-fold Train CV](../assets/readme/readme_shared_train_cv.svg)

所有 14 个 encoder 与后续 V0.1 混合候选使用同一份 component-safe 折映射；每个 component 恰好被留出评估一次，最终报告五折均值 ± SE。

### V0 的 14-model Benchmark

![V0 model-selection benchmark across 14 candidate encoders](../assets/readme/readme_v0_model_selection.svg)

ESM-C 6B 在全部编码器对比中被选为 Model V0。排名第二的 ESM-2 3B 后续用于 V0.1 的 H1/H2，而 H3 仍沿用 V0 的 ESM-C 6B；因此 V0.1 是混合编码器候选模型，不是图中的第 15 个单编码器模型。

### V0 与 V0.1：改变了什么

Model V0 利用一次 ESM-C 6B 表征为每条序列计算 H1 和 H2，只对 H1/H2 双阳性序列计算 H3。Model V0.1 Candidate 则是混合编码器级联：ESM-2 3B 及其自身冻结的 H1/H2 输出头、温度参数和阈值负责 DJR/MCP 筛选；只有通过两级判定门的序列才会运行 ESM-C 6B，并沿用与 V0 完全相同的 H3 病毒门分类与拒判输出头。

![Model V0 and Model V0.1 architecture and frozen-component comparison](../assets/readme/readme_v0_v01_architecture.svg)

| 对比项 | Model V0 | Model V0.1 Candidate |
| --- | --- | --- |
| 项目定位 | 已发布、冻结且可复现的正式基线 | 优先用于探索性筛查的实验候选模型；仍待独立外部验证 |
| H1/H2 | ESM-C 6B 表征、输出头与校准 | ESM-2 3B 表征，以及对应的新冻结输出头与校准 |
| H3 | ESM-C 6B 病毒门分类与拒判输出头 | 与 V0 逐字节相同的 H3 模型文件与校准 |
| 执行方式 | 为所有序列计算 H1/H2 原始分数；H2 受实际级联控制；H3 仅计算双阳性序列 | 为所有序列计算 H1；H2 仅计算 H1 阳性序列；第二编码器和 H3 仅计算双阳性序列 |
| 输出来源记录 | `predictions.tsv` 20 个字段 | 23 个字段，新增三个输出头编码器字段 |

图中的判定门数值是各版本独立冻结的校准阈值，不是性能分数；不能根据阈值更高或更低直接判断模型更强或更严格。两版保留相同的三段最终决策语义和五种最终标签，但 V0.1 的执行路径及来源与版本记录更明确。

#### 平均性能

![Model V0 and Model V0.1 Candidate Train-only development benchmark](../assets/readme/readme_train_cv_performance.svg)

图中为五折均值 ± SE；横轴明确截取为 0.968–1.000。V0.1 更换的是整套 H1/H2 组件；H2 AP 恰好相同，H3 则因复用同一模型文件而完全相同。

| Train-only 五折 CV ↑ | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: |
| H1 AP | `0.9985 ± 0.0003` | **`0.9993 ± 0.0004`** |
| H2 AP | `1.0000 ± 0.0000` | `1.0000 ± 0.0000` |
| H3 known-phylum macro-F1 | `0.9806 ± 0.0095` | `0.9806 ± 0.0095` |
| 综合分数 `S` | `0.9971 ± 0.0009` | **`0.9976 ± 0.0010`** |

`S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 macro-F1`。V0.1 的 H1 AP 平均提高 `0.000833`；由于 H2/H3 不变，综合分数的平均差 `+0.000500` 正好来自 `0.60 × ΔH1`。粗体表示候选模型选定，不表示统计显著性。

#### 五折逐折变化

![Paired fold-level H1 AP and Composite S comparison for Model V0 and Model V0.1 Candidate](../assets/readme/readme_v0_v01_fold_detail.svg)

V0.1 在五折中的四折提高、一折降低；`S` 的 paired-fold 平均差为 `+0.000500`，paired SE 为 `0.000349`。这张图只是共享 Train-CV 上的描述性候选选择证据，不是显著性检验，也不是新的 prospective external Test。

## 输出示例

`predictions.tsv` 为每条输入蛋白保留分数、级联状态和最终标签。以下为字段格式示例：

| protein_id | head1_djr_probability | head2_mcp_probability | head3_prediction | final_prediction |
| --- | ---: | ---: | --- | --- |
| candidate_001 | 0.997 | 0.981 | Nucleocytoviricota | `mcp::Nucleocytoviricota` |
| cellular_djr_002 | 0.994 | 0.082 | not_reached | `djr_non_mcp` |
| background_003 | 0.006 | NA | not_reached | `non_djr` |

## 结果边界

- 输出是用于后续验证的筛查候选，不是结构确认。
- V0.1 的优先实验候选定位来自仅使用 Train 的开发期 CV，尚未进行独立外部验证。
- 分数不是按自然样本实际流行率校正的概率；大规模筛查仍需要独立假阳性评估以及结构或人工复核。

## 仓库目录功能

| 目录 | 功能 |
| --- | --- |
| [`.github/`](../../.github/) | 持续集成、Release 自动化以及 Issue/PR 模板 |
| [`benchmarks/`](../../benchmarks/) | 带校验和的基准测试协议、精简结果和图表 |
| [`configs/`](../../configs/) | 数据集、模型选择和验证配置 |
| [`data/`](../../data/) | 已发布清单、数据划分约定和完整性记录 |
| [`docs/`](../) | 科研证据、复现、架构、版本说明和多语言文档 |
| [`results/`](../../results/) | 精简公开结果、模型身份以及图表来源与版本记录 |
| [`scripts/`](../../scripts/) | 可移植的 Python 科研流程、验证、模型评估和绘图工具 |
| [`src/`](../../src/) | 核心 `djrmcp-finder` Python 研究包 |
| [`tests/`](../../tests/) | 自动化测试和工程合同检查 |
| [`user-inference-v0/`](../../user-inference-v0/) | 已发布、冻结的 Model V0 正式基线包 |
| [`user-inference-v0.1/`](../../user-inference-v0.1/) | 优先用于探索性筛查的 Model V0.1 Candidate 推理包 |

详细使用方法见 [Model V0.1 Candidate](../../user-inference-v0.1/README.cn.md) 与 [Model V0](../../user-inference-v0/README.cn.md) 用户指南；数据、方法和证据边界见 [科研证据说明](../SCIENTIFIC_EVIDENCE.cn.md)。

## 引用

如果在研究中使用 DJR-MCP Finder，请按照 [`CITATION.cff`](../../CITATION.cff) 引用本软件，并注明使用的是 Model V0 还是 Model V0.1 Candidate。

项目原创代码和文档采用 [MIT License](../../LICENSE)。
