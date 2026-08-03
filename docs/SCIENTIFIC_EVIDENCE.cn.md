[English](SCIENTIFIC_EVIDENCE.md) | **简体中文** | [日本語](SCIENTIFIC_EVIDENCE.ja.md)

# 科学证据与解释边界

[文档导航](README.cn.md) | [仓库 README](repository/README.cn.md) |
[可复现性](REPRODUCIBILITY.cn.md)

本页依次回答四个问题：应使用哪个结果、核心数值说明了什么、证据有多强，以及本项目目前
尚不能作出哪些结论。本页是对已冻结协议和结果文件的概述，而非替代它们。

## 应使用哪个结果？

| 科学结果 | 编码器系统 | 当前状态 | 推荐用途 |
| --- | --- | --- | --- |
| **Model V0.1 Candidate** (`model-v0.1-candidate`) | ESM-2 3B 用于 H1/H2；ESM-C 6B 用于 H3 | `recommended_for_external_confirmation` | **新筛选任务的当前首选结果** |
| **Model V0** (`model-v0`) | ESM-C 6B 用于 H1/H2/H3 | 已发布并冻结 | 正式的可复现基线和受支持的备选方案 |

“首选”描述的是当前筛选路径和 Train-CV 提名结果。这并不表示 Model V0.1 Candidate 已经
通过前瞻性外部 Test，也不表示其已取代 Model V0。Model V0 仍是主要科学结果，而不是
已弃用版本。

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

### 为什么会出现 0.800

冻结输出包含对同一组端到端检测结果的两种有效但不同的 component 层级汇总，另有一种
按记录汇总的对照：

| 聚合方式 | Model V0 | Model V0.1 Candidate | 含义 |
| --- | ---: | ---: | --- |
| 等权折宏平均 | `0.800` | `0.800` | 折 sensitivity `1/0/1/1/1` 的均值 |
| 全部留出 components | `0.913876` | `0.913876` | 检出 `191/209` 个 components；对应上方全 component 表 |
| 全部留出记录 | `0.645833` | `0.645833` | 检出 `217/336` 条记录；这不是 component estimand |

各折分别包含 `47/18/47/49/48` 个阳性 components。因此，等权折平均让包含 18 个 component
的第二折占最终数值的 20%，而全 component 估计则给予 209 个 components 中的每一个相同
权重。早期 README 只把 `0.800` 称为“sensitivity”，掩盖了这一区别。

第二折为零是校准分辨率悬崖所致；这并不表示 119 个 MCP 阳性的排序低于 conditional-H2
校准阴性。对两个模型而言，其 H1 和 H2 原始得分均高于相应校准阴性的最大值。不过，H2 阴性
校准子集包含来自仅一个独立 component 的 62 条记录，因此经验尾部证据饱和于
`log10(63) = 1.7993405494535817`。在 cascade 端点，12 个 V0 和 15 个 V0.1 校准阴性具有
这一饱和得分；经来源和 component 平衡后，每个并列得分块的质量分别为 `0.007199` 和
`0.008380`，高于允许值 `0.005`。因此，冻结的保守 `score >= threshold` 规则将阈值移至下一
浮点数值 `1.7993405494535819`，并拒绝整个并列得分块。因此，`0.800` 的计算可在内部复现，
但不适合作为未经限定的公开 recall 数值。

上述澄清和替代聚合方式已使用 [V0 parent pointer](../benchmarks/plm_vs_classical_v0/FULL_ARTIFACT_POINTER.json)
及 [V0/V0.1 audit pointer](../benchmarks/ultra_remote_v0_v01/FULL_ARTIFACT_POINTER.json) 所记录的完整归档逐行
账本进行核验。V0 parent 账本与 SHA-256
`d21bf8534a04b98a11f7502ce275dc6ff346b43d4433ba5551c223e77d904fdb` 一致；V0.1 账本与
`b27a96a9ea7c26ab2c47ae2b3a7d5156cb775a9eab935a6cd17a87caed6ed2fa` 一致。独立重算复现了
上方展示的每一个折阈值、折 sensitivity、评估 specificity 和全 component 数值。归档 manifest
与 SHA-256 `6273f88a618726046162f9e83cbfb447602796c0e9bb7d68af92440faf023ab7`
（V0 parent benchmark）及
`dcd33fa981f4064a027e9d27a184cba947bfd16f3c2c85030e0288d509215384`（V0/V0.1 audit）一致。

## 证据层级

| 证据 | 状态 | 可以回答什么 | 不能回答什么 |
| --- | --- | --- | --- |
| 14-model V0 selection | 冻结的开发阶段选择 | 哪个单一编码器系统被选为 Model V0 | 外部泛化能力 |
| Schema 5 Amendment D | 20/20 gates PASS | 来自相同四个来源的家族成员上，八个模型和九个 cascades 的选择后一致性 | 独立 Test 表现、等效性，或反馈至模型选择 |
| PLM versus classical V0 | Internal cross-fit PASS | 在已声明信息预算下，Train components 上的检索差异 | 外部优越性 |
| Ultra-remote V0/V0.1 audit | PASS；正式声明受阻 | 内部留出和低覆盖 stress strata 上的描述性行为 | 正式的 `<20% identity` 结论 |
| Prospective external Test | **未运行** | — | Model V0 或 Model V0.1 Candidate 的发布级泛化能力 |

## 这些结果尚不能证明什么

- Model V0 和 Model V0.1 Candidate 均没有新的前瞻性外部 Test。
- 历史 Test 结果只适用于 ESM-2 650M，不适用于全 ESM-C-6B V0 系统、Schema 5 nominee 或
  Model V0.1 Candidate。
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
| Viral DJR-MCP | 560 | Gold 65 加 Silver_R3 495；阳性来源详情见下方 |
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
| Silver_R3 | 495 | 436 个 MetaVR 蛋白；18 个 GenBank candidates；41 个文献来源 candidates |

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

| 门 | 纲 | 目 / 末级分类单元 | Gold | Silver_R3 | 总计 |
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

H2 仅在 H1 将蛋白分类为 DJR 后运行；H3 仅在 H2 将其分类为 viral MCP 后运行。

### Model V0.1 Candidate 的提名与权衡

九个 mixed candidates 已预注册，并且仅根据现有 Train-CV 结果排序。four-source robustness
analysis 未对它们重新排序。获提名模型使用 ESM-2 3B 处理 H1/H2、ESM-C 6B 处理 H3
（`S=0.997645`）；其 Holm 校正后的来源警告为 `0/4`（相对于 all-6B）。这并不能证明
four-source non-inferiority 或 equivalence。

| 系统 | 病毒 | 细胞 | 背景 | 匹配 HardNeg | 常开 / 最坏情况 GPU s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen all ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| Mixed nominee | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

四个来源列给出的是 full-expected-path member accuracies，而不是一个合并得分。nominee 找回
52/69 个 viral strict clusters，少于找回 55/69 个的 all-6B，并且需要第二个编码器来处理
到达 H3 的序列。其状态仍为 `recommended_for_external_confirmation`，且
`released_v0_change_permitted=0`。

### Ultra-remote 开发审计

在仅使用 Train 的全 component holdout 上，H1 encoder sensitivity 的差异为 `+0.197`
（V0.1 相对于 V0）。BLAST 定义的 `qcov<80%` stress stratum 差异为 `+0.260`（95% CI
0.206–0.317）。H1 operational detector 的差异仅为 `+0.017`，而 H2 和端到端 MCP cascade
差异为零。由于上述 specificity 和 sample-size 限制，正式状态为
`PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`。

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
2. [Candidate nomination](../results/validation_family_robustness_v0_schema5_mixed_heads/candidate_nomination.tsv)
   和 [Train-CV candidate summary](../results/validation_family_robustness_v0_schema5_mixed_heads/train_cv_candidate_summary.tsv)。
3. [V0 model-selection figure and provenance](../results/figures/project_v0/model_benchmark_metric_revision_1/)。
4. [V0/V0.1 audit report](../benchmarks/ultra_remote_v0_v01/results/REPORT.md)、
   [all-component sensitivities](../benchmarks/ultra_remote_v0_v01/results/stratum_sensitivity.tsv)、
   [equal-fold method summary](../benchmarks/ultra_remote_v0_v01/results/method_summary.tsv)，以及
   [paired comparisons](../benchmarks/ultra_remote_v0_v01/results/paired_v0_v01.tsv)。
5. [Schema 5 compact results](../results/validation_family_robustness_v0_schema5_mixed_heads/)。
6. [PLM versus classical benchmark](../benchmarks/plm_vs_classical_v0/)。
7. [精简科学报告](research/PROJECT_V0_FINAL_REPORT.md)。
8. [完整工作流程与协议边界](research/WORKFLOW_V0.md)。
