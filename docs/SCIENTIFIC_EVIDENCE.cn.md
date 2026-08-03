[English](SCIENTIFIC_EVIDENCE.md) | **简体中文** | [日本語](SCIENTIFIC_EVIDENCE.ja.md)

# 科学证据与解释边界

[文档导航](README.cn.md) | [仓库 README](repository/README.cn.md) |
[可复现性](REPRODUCIBILITY.cn.md)

本页依次回答四个问题：应使用哪个结果、核心数值说明了什么、证据有多强，以及本项目目前
尚不能作出哪些结论。本页是对已冻结协议和结果文件的概述，而非替代它们。

## 应使用哪个结果？

| 科学结果 | 编码器系统 | 当前状态 | 推荐用途 |
| --- | --- | --- | --- |
| **Model V0.1 Candidate** | ESM-2 3B 用于 H1/H2；ESM-C 6B 用于 H3 | 实验候选；仍待独立外部验证 | **当前优先用于探索性筛查的实验候选模型** |
| **Model V0** | ESM-C 6B 用于 H1/H2/H3 | 已发布并冻结 | 可复现基线和受支持的备选方案 |

“优先实验候选”描述的是当前探索性筛查路径和 Train-CV 结果。这并不表示 Model V0.1
Candidate 已通过独立外部验证，也不表示其已取代 Model V0。Model V0 仍是主要科学结果，
并非已弃用版本。

## 核心开发数值

下方两张表来自不同的仅使用 Train 的开发协议。只能在同一行内比较 V0 与 V0.1；不要跨表
比较数值。

### 共享五折 Train-CV 提名

| 指标 ↑ | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: |
| 综合得分 `S`（均值 ± SE） | `0.9971 ± 0.0009` | **`0.9976 ± 0.0010`** |

对两个模型均有 `S = 0.60·H1 AP + 0.30·H2 AP + 0.10·H3 macro-F1`。所示不确定性为五个共享折
得分的样本标准差除以 `sqrt(5)`，并非置信区间。已发布 V0 快照的 H1 AP 为
`0.998 ± 0.000`、H2 AP 为 `1.000 ± 0.000`、H3 已知类别 macro-F1 为 `0.981 ± 0.010`
（均值 ± SE）。粗体表示获提名的候选模型，并不代表统计显著性声明。

### 独立的循环 component-holdout 审计

| 全 component sensitivity（描述性；按折锁定） | 阳性 components（n） | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: | ---: |
| H1 编码器 DJR 读出 | 392 | `0.728` | `0.925` |
| H1 实际检测器 | 392 | `0.978` | `0.995` |
| 端到端 MCP cascade | 209 | `0.914` | `0.914` |

每个循环使用三个拟合折、下一个折进行校准，以及一个评估折。每种方法、任务和循环均在名义
99.5% specificity 目标下单独校准阈值，随后将该阈值原样应用于该循环的评估折。在每个
component 内，先对记录检测结果取平均；随后表格在全部五个评估折中给予每个留出 component
相同权重。这就是审计的配对全 component 报告所采用的聚合方式。

最大的描述性差异出现在 H1 编码器读出。按照冻结协议拟合并应用任务适配检测器后，这一差异
减小；审计未观察到端到端 MCP sensitivity 差异。两个系统的 H3 相同，因此未纳入本次审计。

## 证据层级

| 证据 | 状态 | 可以回答什么 | 不能回答什么 |
| --- | --- | --- | --- |
| 14-model V0 selection | 冻结的开发阶段选择 | 哪个单一编码器系统被选为 Model V0 | 外部泛化能力 |
| 四来源家族稳健性分析 | 20 项预设检查全部通过 | 来自相同四个来源的家族成员上，八个模型和九个 cascades 的选择后一致性 | 独立 Test 表现、等效性，或反馈至模型选择 |
| PLM versus classical V0 | 内部交叉拟合检查通过 | 在已声明信息预算下，Train components 上的检索差异 | 外部优越性 |
| V0/V0.1 低相似性审计 | 内部检查通过；仅作描述性解释 | 内部留出集和低覆盖压力分层上的描述性行为 | 正式的 `<20% identity` 结论 |
| 独立外部验证 | **未运行** | — | Model V0 或 Model V0.1 Candidate 的发布级泛化能力 |

## 这些结果尚不能证明什么

- Model V0 和 Model V0.1 Candidate 均未进行独立外部验证。
- 每个配对的按折校准系统都在至少一个评估折中未达到预期的 99.5% specificity；因此，
  sensitivity 差异是描述性的，而不是 specificity 匹配条件下的改进。
- BLAST 定义的严格 `qcov≥80%, identity<20%` stratum 只包含一个独立阳性 component——数量
  太少，无法得出正式的 ultra-remote 结论。
- H3 并非 V0.1 的改进：两个系统使用相同的 ESM-C 6B H3 模型。
- 证据并未表明 Model V0.1 Candidate 已经取代 Model V0，也未表明 PLMs 在外部数据上优于
  classical methods。
- `mcp::unknown/other` 表示拒绝强制归入两个受支持的 phyla。它不是通用的未知病毒或
  out-of-distribution 检测器。

## 详细证据

### 已发布的 Model V0

- 数据：560 个病毒 MCP-DJRs、500 个细胞 DJRs、5,000 个 HardNeg 蛋白，以及 5,000 个
  background 蛋白。

#### 开发样本构成

冻结的开发数据集包含 **11,060 条 exact-sequence-unique representative proteins**。
下方精简清单与可展开的分类表共同构成公开 sample list，复现了 `Design-0728.pptx` 第 5 页的内容。
包含 11,060 行的构建 manifest 因含有本地源数据路径而不随仓库发布；公开记录改由汇总数量和经
checksum 绑定的证据产物组成。

| 数据集组别 | N | 构成与构建方式 |
| --- | ---: | --- |
| Viral DJR-MCP | 560 | Gold 65 加 Silver 495；阳性来源详情见下方 |
| Cellular DJR | 500 | GH172/DUF2961 64；PHM/PAM 290；PNGase F 85；SIDT/SID-1/ChUP 56；DeCLIC-like DJR NTD 5 |
| Hard non-DJR | 5,000 | 由 PPT 中 36-seed 构建集扩展得到的、具结构支持且富含 β-sheet 的病毒及细胞非 DJR decoys |
| Background non-DJR | 5,000 | 对其他三个组别完成 sequence、HMM 及 structure relatedness 排除后保留的 Swiss-Prot representatives |
| **总计** | **11,060** | 冻结的 component-safe split 之前的 exact-sequence-unique representatives |

Cellular-DJR 与 HardNeg 的构建概要使用 `qTM > 0.7` 和 `LDDT > 0.5` 进行非病毒结构扩展。
仓库包含最终的 5,000 行 HardNeg 清单，并以 checksum 固定其上游元数据，但不包含 PPT 中
36 个 seed families 的精简逐行清单；因此，该 seed 数量属于构建说明，而不是可由仓库完整审计
的列表。

| 病毒证据层级 | N | 来源 |
| --- | ---: | --- |
| Gold | 65 | 15 个实验 PDB 结构；49 个 RefSeq 注释 MCPs；1 个具有 virion-proteomics 支持的分离病毒 GenBank MCP |
| Silver | 495 | 436 个 MetaVR 蛋白；18 个 GenBank candidates；41 个文献来源 candidates |

对于 MetaVR 和 RefSeq/GenBank Silver candidates，PPT 记录了高病毒置信度、HMM 支持
（`E < 0.1`、bit score `> 10`）、长度 `> 200 aa`、与 Gold clusters 分离，以及与 PDB Golds
的结构相似性（`qTM ≥ 0.60`、`tTM ≥ 0.60`、`LDDT ≥ 0.50`）。

阳性 catalog 覆盖以下 phylum-level groups：

| 阳性分类 | N |
| --- | ---: |
| Nucleocytoviricota | 415 |
| Preplasmiviricota | 117 |
| Produgelaviricota | 26 |
| Literature-only, unclassified | 2 |
| **总计** | **560** |

<details>
<summary>PPT 中按目 / 末级分类单元整理的样本列表</summary>

| 门 | 纲 | 目 / 末级分类单元 | Gold | Silver | 总计 |
| --- | --- | --- | ---: | ---: | ---: |
| Nucleocytoviricota | Megaviricetes | Algavirales | 25 | 161 | 186 |
| Nucleocytoviricota | Megaviricetes | Imitervirales | 9 | 122 | 131 |
| Nucleocytoviricota | Megaviricetes | Mamonoviridae† | 1 | 0 | 1 |
| Nucleocytoviricota | Megaviricetes | Pimascovirales | 7 | 55 | 62 |
| Nucleocytoviricota | Mriyaviricetes | Yaraviridae† | 1 | 18 | 19 |
| Nucleocytoviricota | Pokkesviricetes | Asfuvirales | 2 | 8 | 10 |
| Nucleocytoviricota | Pokkesviricetes | Chitovirales | 1 | 5 | 6 |
| Preplasmiviricota | Aquintoviricetes | Archintovirales | 2 | 6 | 8 |
| Preplasmiviricota | Pharingeaviricetes | Rowavirales | 1 | 2 | 3 |
| Preplasmiviricota | Polintoviricetes | Amphintovirales | 2 | 2 | 4 |
| Preplasmiviricota | Tectiliviricetes | Kalamavirales | 2 | 3 | 5 |
| Preplasmiviricota | Virophaviricetes | Divpevirales | 0 | 1 | 1 |
| Preplasmiviricota | Virophaviricetes | Lavidavirales | 3 | 5 | 8 |
| Preplasmiviricota | Virophaviricetes | Mividavirales | 1 | 5 | 6 |
| Preplasmiviricota | Virophaviricetes | Priklausovirales | 2 | 80 | 82 |
| Produgelaviricota | Ainoaviricetes | Lautamovirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Atroposvirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Belfryvirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Coyopavirales | 0 | 1 | 1 |
| Produgelaviricota | Belvinaviricetes | Vinavirales | 3 | 19 | 22 |
| Literature-only | Unclassified | *Abadenavirae*-like<sup>*</sup> | 0 | 2 | 2 |

† 未指定 order 的 ICTV terminal family。星号表示文献中的工作 clade，而不是 ICTV MSL41
order。每个 SHA-256 相同的蛋白只计数一次；在此展示中，PPT 将四个跨 order aliases 归至
catalog 指定的 primary taxon。

</details>

公开的 [dataset contract](../configs/v0_dataset.json)、
[dataset checksum manifest](../data/processed/v0/CHECKSUMS.sha256) 和
[post-split audit checksums](../results/postsplit_integrity_v0/CHECKSUMS.sha256) 为同一冻结数据集及其
审计提供精简的机器可读 provenance。

- 划分：Train/Validation/Test = **6,634 / 2,212 / 2,214**。划分前合并了 exact-sequence、source、
  component 和 MMseqs2 relationships；剩余符合条件的跨划分边数 = 0。
- 选择：14 个 representation models 共享一个仅使用 Train 的五折 component map。通过
  three-head Validation gates 和 paired one-SE rule 后，ESM-C 6B 被选中（`S=0.997145`）。

| 输出头 | 任务 | 分类器 | 温度 | 阈值 |
| --- | --- | ---: | ---: | ---: |
| H1 | DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | viral MCP-DJR / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

Model V0 利用一次共享的 ESM-C 6B 表征为每条序列计算 H1 和 H2 原始分数。只有 H1 阳性时，
H2 结果才参与实际级联；H3 只对 H1/H2 双阳性序列计算。

### Model V0.1 Candidate：选择与权衡

九种编码器组合仅依据现有 Train-CV 结果进行比较。四来源稳健性分析只用于一致性检查，
不用于重新排序。Model V0.1 Candidate 使用 ESM-2 3B 处理 H1/H2、ESM-C 6B 处理 H3
（`S=0.997645`）；相对于 Model V0，没有 Holm 校正后的来源警告。这并不能证明四来源条件下
的 non-inferiority 或 equivalence。

| 系统 | 病毒 | 细胞 | 背景 | 匹配 HardNeg | 常开 / 最坏情况 GPU s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Model V0（全 ESM-C 6B） | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| Model V0.1 Candidate | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

四个来源列给出的是 full-expected-path member accuracies，而不是一个合并得分。Model V0.1
Candidate 找回 52/69 个严格病毒序列簇，少于 Model V0 的 55/69，并且需要第二个编码器
处理到达 H3 的序列。它仍是探索性筛查的优先实验候选，尚待独立外部验证，也不取代已发布的
Model V0。

### Ultra-remote 开发审计

在仅使用 Train 的全 component holdout 上，H1 encoder sensitivity 的差异为 `+0.197`
（V0.1 相对于 V0）。BLAST 定义的 `qcov<80%` stress stratum 差异为 `+0.260`（95% CI
0.206–0.317）。H1 operational detector 的差异仅为 `+0.017`，而 H2 和端到端 MCP cascade
差异为零。由于至少一个评估折未达到目标 specificity，且严格 ultra-remote stratum 仅包含
一个独立阳性 component，这些结果只能作描述性解释，不能支持正式的 ultra-remote 声明。

### PLM versus classical retrieval

此 benchmark 使用循环的 3-fit/1-calibration/1-evaluation component cross-fitting，作用于
6,634 条 Train 记录。数值为 fold-macro component AP / sensitivity，阈值按 99.5% specificity 目标
校准。

| 方法 | H1 | H2 |
| --- | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 |
| Component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 |
| ESM-2 650M cosine, contextual | 0.9515 / 0.8954 | 0.9965 / 0.9977 |

对于 H1，ESM-C cosine 相对全部四个 classical anchors 的配对 delta confidence intervals
均为负值。对于 H2 和 H1→H2 endpoint，区间跨越零，并受 singleton components 的低 FPR
分辨率限制。这是 representation-retrieval 比较，而不是已发布 supervised tool 的外部表现。
validator 重新计算了 point estimates，但没有独立重跑全部 10,000 次 bootstrap replicates。

## 权威证据入口

1. [Model V0.1 Candidate package](../user-inference-v0.1/) 和
   [released Model V0 package](../user-inference-v0/)。
2. [已发布结果导航](../results/README.cn.md)和
   [V0 图表集合](../results/figures/project_v0/README.cn.md)。
3. [V0/V0.1 audit report](../benchmarks/ultra_remote_v0_v01/results/REPORT.md)、
   [all-component sensitivities](../benchmarks/ultra_remote_v0_v01/results/stratum_sensitivity.tsv)、
   [paired comparisons](../benchmarks/ultra_remote_v0_v01/results/paired_v0_v01.tsv)。
4. [PLM versus classical benchmark](../benchmarks/plm_vs_classical_v0/)。
5. [精简科学报告](research/PROJECT_V0_FINAL_REPORT.md)。
6. [完整工作流程与协议边界](research/WORKFLOW_V0.md)。
