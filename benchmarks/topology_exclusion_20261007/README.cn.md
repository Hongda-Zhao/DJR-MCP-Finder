# 拓扑排除与开发集重训（2026-10-07）

[English](README.md) | **简体中文** | [日本語](README.ja.md)

这是已完成的**探索性研究实验**，不是模型发布，也不证明污染已被清除。记录包括参考树复核、用户选择的广义排除名单，以及 ESM-C 6B / ESM-2 650M 的开发集重训。已发布模型的编码器、Head、阈值、路由和版本均不变。

## 操作与数据

在先前移除 8 条的 550 叶 AA / 3Di 树上，按 Class 和 Phylum 检查无根内部边的两侧、单条异类、支持率及包含距离并列的近邻。复核得到 22 条候选：最高优先 5 条、支持不足但重点关注 4 条、特殊拓扑 3 条、弱信号或上下文敏感 10 条。最高优先为 Imitervirales_C0475、Priklausovirales_C0052、C0082、Asfuvirales_C0011 和 Gold Chitovirales_C0003。

按用户要求，22 条全部剪出，包括弱信号及已知实验结构参考，累计 **30 条移除、528 条保留**。这是原树剪枝展示，没有重新运行 FoldMason / IQ-TREE；支持率来自原始 558 条分析，合并路径不显示旧支持率。移除长枝可改变 midpoint 根位置。

30 条通过序列 SHA 精确匹配正式 11060 行模型 manifest。其中 **16 条 Train、7 条 Validation** 从三个 Head 的开发数据全部排除；**7 条 Test 仅登记待审，保持不变且不计算性能**。新 manifest 为 11037 行：Train 6618、Validation 2205、Test 2214。VMA-DJR 分别 320 / 105 / 112，H3 已知类分别 305 / 100 / 106。

原建模正例有 560 条，其中两条 literature-only 序列未进入 558 叶树，继续保留。不能把 528 条全投入 Train。复用经过校验的冻结 embedding，生成逐行一致的子集；重新拟合六个分类 Head，使用同一套新冻结的 Train-only 组件分组五折，并重新校准温度和阈值。这不是 PLM 微调。

## 结果与边界

| 模型 | CV H1 AP | CV H2 AP | CV H3 macro-F1 |
| --- | ---: | ---: | ---: |
| ESM-C 6B | 0.997021 | 1.000000 | 0.994888 |
| ESM-2 650M | 0.996198 | 1.000000 | 0.912663 |

Validation H1 AP 为 0.992544 / 0.999746，H3 closed-set macro-F1 为 1.000000 / 0.986094；并非 6B 在所有 Head 上都更好。两模型各拒识 100 条已知类中的 4 条；unknown 诊断只有 5 条，各拒识 4 条但对象不同。

这些是所选超参数的**条件式、逐 Head 开发指标**，不是完整级联或 Test 性能。超参数用同一 CV 选择，Validation 用于校准。名单是在查看全参考树后确定的，包含划入 Test 的参考，因此即使保留 Test 行，也不能称为前瞻性的未见评估。没有进行固定评价样本的原集/排除集控制实验，不能据此断言去污染提高了泛化能力或替换正式模型。同 Class 内的旧 Order 冲突仍待审。

## 文件与核验

- [22 条复核名单](topology/review_candidates_22.tsv)、[5 条优先名单](topology/priority_audit_5.tsv)、[逐层级证据](topology/candidate_rank_evidence.tsv)、[窗口敏感性](topology/window_sensitivity.tsv)。
- [累计 30 条](pruning/removed_tip_ids.txt)、[保留 528 条](pruning/retained_tip_ids.txt)、[剪枝核验](pruning/pruning_QA.tsv)。
- [3Di 完整图](pruning/figures/Three_Phylum_3DI_midpoint_rectangular_full_taxonomy_only.pdf)、[AA 完整图](pruning/figures/Three_Phylum_AA_midpoint_rectangular_full_taxonomy_only.pdf)、[双树对照](pruning/figures/Three_Phylum_AA_3Di_midpoint_comparison_taxonomy_only.pdf)。
- [训练映射](retraining/exclusion_crosswalk_30.tsv)、[源 manifest 审计](retraining/source_manifest_audit.json)、[对照表](retraining/comparison.tsv)、[训练摘要](retraining/RESULTS_SUMMARY.json)、[准备核验](retraining/PREPARED.json)。

仓库根目录运行，不需要原始序列或模型文件：

```bash
python scripts/validate_topology_exclusion_evidence.py
python -m pytest -q tests/test_topology_exclusion_evidence.py
```

## 完整复现的条件

`recorded_scripts/` 是**本次运行的站点专用脚本记录**，不是便携默认入口或自动 CI 工作流。它们引用原工作区的 `outputs/` 布局和 `/aptmp/hongda/` 历史归档。Git 中的精简证据包不能代替完整序列、向量和运行环境。

拓扑重放需恢复原始 `Three_Phylum_RefOnly_FoldMason_IQTREE_20260924`、先前 8 条筛查及 `Three_Phylum_pruned8_20261007` 输入，在原工作区依次运行 `topology/recheck.R`、`attachment.R`、`summarize.py`。R 筛查依赖 ape；绘图还需 phangorn、ggplot2、patchwork、分类注释、配色、元数据和未比对 FAA。树哈希及核验值在 manifest 中。

训练重放须选择**全新输出目录**，同时调整脚本中的 `ROOT`、`BASE`、`ARCHIVE` 和 PBS 运行/环境路径，不能直接覆盖历史目录。准备脚本验证原 manifest 哈希、30 条匹配、原始 FAA 和两个向量 bundle 校验和，再筛选开发集、保留 Test、保存代码快照、建立向量子集及 CV folds。随后按配置调用各模型的 `calibrate_benchmark_model.py`；finalizer 核验六个模型校验和及指标分母。所需版本和代码哈希记录在 `PREPARED.json` 与 calibration 中。

历史运行目录：`/aptmp/hongda/DJR-MCP-Finder/experiments/pruned30_dev_20261007`。作业 5147398 / 5147399 / 5147400 均 Exit 0，耗时 33 / 17 / 13 秒。工作站 rx1000 可用，但迁移检查时 CPU 作业已经完成，未重复运行。

本 PR **不包含原始序列、embedding、模型 checkpoint、环境或个体 Test 预测**。模型路径和代码哈希是服务器产物的来源记录；精简验证器不能重新验证未收录的模型字节。`CHECKSUMS.sha256` 仅覆盖本实验包，不改变正式 release 校验和。使用新 Head 必须配套其自身 calibration 与编码器约定。
