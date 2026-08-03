<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/PROTOCOL.md -->

本译文仅供阅读；冻结的英文源文档为权威版本。

# 冻结协议

## 目的

评估将 v0 H1/H2 encoder（ESM-C 6B）替换为 v0.1 candidate（ESM-2 3B）是否会改善
远缘 component 检索或监督检测，同时明确指出当前数据集在哪些方面不足以回答严格的
ultra-remote 问题。

## 数据划分

- 仅使用 Train split：五个全局冻结 component folds 中共 6,634 条记录。
- 对于 evaluation fold `k`，下一个 fold 用于 calibration，其余三个 folds 用作 fit/reference
  folds。
- 在一个 cycle 中，任何 component 都不得跨越 fit/reference、calibration 或 evaluation role。
- Validation 与 Test 的 prediction count 必须保持为零。

## 方法层级

1. **受控 encoder/readout：** 对完全相同的 fit-fold DJR 或 viral MCP positive reference IDs
   取 maximum cosine。
2. **任务适配 detector：** H1/H2 classifier family、hyperparameter、training label、fold、seed
   和 thresholding rule 完全相同；只有 embedding 发生变化。
3. **经典方法背景：** BLASTP、DIAMOND ultra-sensitive、MMseqs2、component HMM、PSI-BLAST
   和 family HMM score 直接复用，不重新拟合或重新评分。

PSI-BLAST 与 family HMM 获得的信息比受控 pairwise methods 更具任务特异性，因此仍作为
描述性的次要 comparator。

## 阈值与 endpoint

- 每个 method/fold 的 threshold 使用所有符合条件的 calibration negatives 锁定，目标
  specificity 为 99.5%，权重按 source 与 component 平衡。
- threshold 原样应用于 evaluation fold 和每个 difficulty stratum；不允许针对 stratum 重新校准。
- Encoder endpoint：在 `FPR in [0, 0.005]` 范围内按 component/source 平衡的 normalized partial
  AUROC。当任何按 source 平衡的 independent negative-component unit 大于 0.005 时，直接抑制该
  endpoint，而不是进行插值。
- Detector endpoint：锁定 threshold 下按 component 平衡的 sensitivity，并同时报告实际 evaluation
  specificity。若 specificity gate 失败，则不能把 sensitivity gain 称为 matched-specificity
  improvement。
- 描述性 strata 的不确定性采用 paired evaluation-component bootstrap，calibration threshold 固定；
  不包含 calibration uncertainty。只有 v0 和 v0.1 在全部五个 evaluation folds 中都达到实际
  99.5% specificity 时，paired delta 才可称为 matched-specificity improvement。

## 难度分层

| 分层 | 定义 | 状态 |
|---|---|---|
| Component holdout | 所有 held-out positive components | 主要的开发泛化；不自动等同于 ultra-remote |
| Low-coverage stress | 最佳 evaluation-cycle BLAST hit 的 qcov <80% | 描述性、由 BLAST 定义的 proxy |
| Twilight identity | qcov >=80% 且 20% <= identity <30% | 描述性、由 BLAST 定义 |
| Identity <20%, any coverage | 最佳 BLAST identity <20% | 探索性 case series |
| Strict ultra-remote proxy | qcov >=80% 且 identity <20% | 仅为探索性 case series |

最佳 BLAST hit 按 parent benchmark 中已经冻结、宽松 E-value 1000 search 的 maximum bit score
选择。不会刻意把 no-hit subset 用作 headline，因为用一个受比较 method 的失败来定义 cohort，
会对该 method 产生 selection bias。

## 正式 ultra-remote 声明所需的证据

- 独立 stratifier，且该 stratifier 不作为参与评分的 competitor。
- 总体至少 100 个 positive independent components，每个 fold 至少 20 个。
- 每个 source/fold 最好至少有 600 个 calibration-negative components，以支持可信的 99.5%
  specificity gate。
- External lockbox calibration 与 Test；label 或 score 开启后不得调参。
