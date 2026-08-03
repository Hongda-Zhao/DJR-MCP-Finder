<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/DECISIONS.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# 设计决策与排除项

## 为什么采用 3/1/1，而不是普通的五折 OOF thresholding？

普通 OOF ranking 足以计算 fold-specific AP；但是，如果使用其他四个 OOF fit 的 score 来 calibration fold *k*，就会间接重复使用这些 model/reference library 中的 fold *k*。这也会在大小不同的 maximum-similarity database 之间交换 threshold。因此，循环设计使用三个 fit/reference fold、一个专用 calibration fold 和一个 evaluation fold。每个原始 component 都会被评价一次、用于 calibration 一次，但不会在同一 cycle 中同时承担两种角色。

## 为什么 supervised ESM-C 和 family HMM 不在 controlled headline 中？

Supervised ESM-C system 会从 labelled negative 学习，而 controlled retriever 只接收 positive reference FASTA。另一方面，family HMM grouping 会使用人工整理的 family/taxonomy 元数据。两者都是实用的 operational system，但如果把它们混入 controlled representation comparison，就会混淆 sensitivity 差异的来源。

ESM-C 6B 及其 classifier hyperparameter 是在先前使用这些 fold/Validation 的开发过程中选定的。因此，即使每个循环 fit 本身都不会让 calibration 和 evaluation component 进入 training，其 operational row 仍标记为 `selected_model_descriptive_only`。

## 为什么不使用历史 project HMM bundle？

它们早于冻结 split，并参与过数据整理或排除逻辑。因此，对于这个 cohort，其结果会构成循环论证。这里只允许使用每个 cycle 内部构建的 Train-only profile；历史 bundle 可以留待未来在真正的外部 cohort 上评价。

## 为什么这里以 99.5% specificity 为 primary？

当前内部 cohort 的 negative component 太少，无法稳定估计 99.9% specificity，尤其是 conditional H2。未来外部 Benchmark 的 endpoint 仍为 99.9%；本内部 protocol 明确修订为以 99.5% 作为 primary endpoint，并将 99.9% 标记为 resolution-limited secondary。

## 为什么部分 99.5% sensitivity interval 标记为 conditional？

冻结 fold map 主要按 record 而不是独立 component 平衡。在 fold 3 中，全部 62 条 cellular-DJR negative 都属于一个 component。该 fold 是 cycle 2 的 H2 calibration fold，也是 cycle 3 的 H2 evaluation fold。因此，cycle-2 calibration 在 99.5% 下不能容许哪怕一条 false-positive record，而 single-component bootstrap stratum 无法表示 component 间 uncertainty。End-to-end VMA calibration 在其他 negative source 之外还包含同一个 cellular source，因此继承了相应的 source-specific 限制。

我们保留预注册的 estimand，并在单独的 resolution-status field 中公开该限制；不会悄悄放宽 FPR 目标，也不会把 conditional interval 当成外部 low-FPR evidence。

## 为什么已部署的 PLMSearch 不在 primary matrix 中？

gds2 PLMSearch module 是一个未提交的 2024 CPU 部署，基于 ESM-1b 和在外部训练的 SCOP/CATH similarity model。它会截断超过 1,022 residue 的序列，并且 score 具有方向性。这些性质使其适合作为未来 exploratory resource tier，但不能直接取代 project embedding 用于 controlled comparison。Primary PLM retrieval track 使用经过完整 checksum 冻结的 ESM-C 6B 和 ESM-2 650M embedding。gds2 上没有安装 pLM-BLAST。
