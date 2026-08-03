<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/PROTOCOL.md -->

> 本译文仅供阅读；冻结的英文源文件是正式且权威的版本。

# 冻结方案：PLM 与经典远程同源方法的比较

## 范围与结论边界

这是一项内部方法开发对比。它可以确定在项目数据上进行 component cross-fitting 时观察到了什么，但不能证明外部优效性。Validation 已用于早期模型开发，受保护的 Test split 不在本次范围内。PLM 的 pretraining exposure 无法完全获知，因此，相同的 task-specific reference 并不意味着总 pretraining information 相同。

## Cohort 与泄漏控制

- Cohort：冻结 Train split 中的 6,634 条记录。
- Outer fold：以 `global_component_id` 为 key 的现有五折 map。
- 对于 evaluation fold *k*，calibration fold 为 `k mod 5 + 1`；其余三个 fold 是唯一可用于 fitting/reference 的数据。
- Calibration 和 evaluation 使用完全相同的 fitted model/reference/profile，且二者都不能进入 fitting、MSA 或 PSSM iteration。
- 在一个 fold 内，任何 component 都不能同时出现在 query 和 reference 中。
- BLASTP、DIAMOND、MMseqs2、cosine retrieval、HMMER 和 PSI-BLAST 对同一 task 和 fold 共用完全相同的 reference-ID manifest。
- HMM MSA 和 PSI-BLAST enrichment database 只能包含 reference ID。
- Validation 和 Test 记录不得作为 query、reference、profile member、threshold-fitting row 或 metric row。

## 任务

| ID | Positive | Negative | Eligible rows | Reference set |
|---|---|---|---|---|
| `h1_djr` | viral VMA + cellular DJR | hard + background non-DJR | all Train | outer-Train DJR |
| `h2_vma_conditional` | viral VMA | cellular DJR | Train DJR only | outer-Train VMA |
| `vma_end_to_end` | viral VMA | cellular DJR + hard + background | all Train | outer-Train VMA |

## 方法

- `esmc6b_cosine` 和 `esm2_650m_cosine`：与 outer-Train positive reference 的 maximum cosine；mean embedding 是固定的项目 artifact。
- `blastp`：maximum bit score，BLAST+ 2.17.0。
- `diamond_ultra`：maximum bit score，DIAMOND 2.2.4 `--ultra-sensitive`。
- `mmseqs_s7.5`：maximum bit score，MMseqs2 18-8cc5c，sensitivity 7.5，一次 iteration。
- `hmmer_component`：maximum full-sequence HMM bit score；每个 positive global component 对应一个 Train-only model。Singleton model 会被保留并计数。
- `hmmer_family`：使用 Train-only metadata group 的相同 score。由于人工整理的 grouping 提供了额外 supervision，因此单独报告。
- `psiblast_longest_seed_positiveDB_3iter`：每个 positive component 使用一个确定性的 longest seed，对 outer-Train positive-only database 进行至多三次 iteration，inclusion E-value 为 0.002，在 enrichment 期间不执行 per-subject HSP truncation，然后使用冻结 PSSM 搜索 calibration 和 evaluation fold。
- `esmc6b_supervised`：使用项目的冻结设置，为每个 outer fold 重新 fitting H1/H2 model。End-to-end score 取 nested-cross-fitted empirical H1 和 H2 negative-tail evidence 的较小值进行组合。

No-hit 是合法的 negative infinity score。Tool 或 parser failure 属于 missing/NA，会使正式 aggregation 失效。

## Metric 与 weighting

### 内部 low-FPR endpoint 修订

Section 12 将 99.9% specificity 保留给未来统计功效充分的外部 Benchmark。当前内部 cohort 无法可靠分辨该 endpoint（尤其是只有 298 个 cellular negative 的 H2），因此 protocol V0 预注册 99.5% 作为其内部 primary，并仅将 99.9% 保留为 `RESOLUTION_LIMITED_SECONDARY`。这项修订不会改变未来的外部 endpoint。

### Aggregation 前的经验分辨率审计

对冻结 fold 进行的 score-independent audit 发现了额外的 H2 限制。Fold 3 包含 62 条 cellular-DJR negative 记录，但只有一个 `global_component_id`（`V0GC_96fb96e7e076c167`）。当 fold 3 为 cycle 2 进行 calibration 时，每条 H2 negative 记录的 weight 为 1/62（1.61%），因此 99%、99.5% 和 99.9% threshold 都要求经验 false positive 为零。当 fold 3 在 cycle 3 中被评价时，H2 specificity 只有一个独立 negative component。由于 component bootstrap 会以 multiplicity one 保留 stratum 的唯一成员，它无法估计该 source 的 component 间变异。

冻结的 99.5% estimand 不会在事后更改。相反，受影响的 sensitivity estimate 和 paired interval 会在机器可读输出和报告中标记为 conditional 与 resolution-limited。Fold 2 也有 119 条 VMA-positive 记录，但只有 18 个 positive component；因此，所有 primary table 均保留 fold range 和 record/component count。这些限制意味着不能把内部 H2 low-FPR endpoint 视为稳定的外部 specificity estimate。

Primary metric 是 fold-macro component-balanced average precision，以及 99.5% source-balanced specificity 下的 sensitivity。每个 component 先获得相同 mass，其记录共同分配该 mass。对于 threshold calibration，negative source 先获得相同 mass，然后同一 source 内的 component 再获得相同 mass。

Threshold 只使用 cycle 的专用 calibration fold，并以配对 evaluation fold 所用的相同 reference/model 进行 scoring。Inclusive tie 采用保守处理。Sensitivity 也会在 99% 和 99.9% 下显示；后者始终标记为 `RESOLUTION_LIMITED_SECONDARY`。FP-per-million endpoint 无法估计。

Fold-macro component-balanced AP 和 calibrated sensitivity 的 paired uncertainty 都使用 10,000 次共同的 component resample。每个 replicate 抽取一个 global component-multiplicity vector，并在 task、cycle、method 和两个 metric 间重复使用。每个 method 的 calibration threshold 都会在该 draw 内重新计算。Paired percentile-bootstrap interval 仅作描述性报告；bootstrap sign fraction 不会标记为 null-hypothesis P value，也不会提出 family-wise superiority claim。

## 停止条件

如果 controlled method 之间的任何 reference checksum/ID contract 不同、query component 泄漏到 reference/profile、inclusion ledger 包含 non-reference ID、Test/Validation prediction row 不为零、method failure 被编码为 no-hit、缺少预期 score，或把 99.9%/FP-per-million 表述为稳定 primary estimate，正式 summarization 将失败。
