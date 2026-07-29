# v0 / v0.1 超远缘开发评测报告

## 一句话结论

本次计算可以回答 v0.1 在**冻结 component 分折**和**BLAST 定义的低覆盖压力层**上是否优于 v0，
但不能回答严格超远缘优越性：`qcov >=80% 且 identity <20%` 的独立正 component 计数为
`{'h1_djr': 1, 'h2_vma_conditional': 1, 'vma_end_to_end': 1}`，远低于预注册的 100 个下限。

## v0.1 相对 v0：全部 component-holdout

| 任务 | encoder 灵敏度差 | 监督检测器灵敏度差 | encoder specificity | detector specificity |
| --- | --- | --- | --- | --- |
| h1_djr | +0.197 | +0.017 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |
| h2_vma_conditional | +0.049 | +0.000 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |
| vma_end_to_end | +0.049 | +0.000 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |

差值为 v0.1 减 v0。只有双方五个评价 folds 都守住实际 99.5% specificity 才标为 matched；
否则差值只是固定 calibration 阈值下的描述，不能叫 matched-specificity 提升。这里证明的也只是
Train-only component-level 泛化，不等于严格超远缘。

## BLAST-defined 低覆盖压力层（qcov <80%）

| 任务 | 比较层 | 独立 components | 灵敏度差 | 95% paired CI |
| --- | --- | --- | --- | --- |
| h1_djr | encoder | 264 | +0.260 | [+0.206, +0.317] |
| h1_djr | task_adapted_detector | 264 | +0.028 | [+0.011, +0.049] |
| h2_vma_conditional | encoder | 100 | +0.062 | [+0.020, +0.112] |
| h2_vma_conditional | task_adapted_detector | 100 | +0.000 | [+0.000, +0.000] |
| vma_end_to_end | encoder | 100 | +0.063 | [+0.020, +0.113] |
| vma_end_to_end | task_adapted_detector | 100 | +0.000 | [+0.000, +0.000] |

此层只做描述：低覆盖可能来自短同源片段、domain fusion、截短或真正远缘；并且分层来自
被比较的 BLAST，因此不能用于正式宣称 PLM 胜过 BLAST。

## BLAST-defined twilight 层（qcov >=80%，20% <= identity <30%）

| 任务 | 比较层 | 独立 components | 灵敏度差 | 95% paired CI |
| --- | --- | --- | --- | --- |
| h1_djr | encoder | 113 | +0.046 | [+0.013, +0.086] |
| h1_djr | task_adapted_detector | 113 | +0.000 | [+0.000, +0.000] |
| h2_vma_conditional | encoder | 106 | +0.024 | [+0.001, +0.057] |
| h2_vma_conditional | task_adapted_detector | 106 | +0.000 | [+0.000, +0.000] |
| vma_end_to_end | encoder | 106 | +0.025 | [+0.001, +0.057] |
| vma_end_to_end | task_adapted_detector | 106 | +0.000 | [+0.000, +0.000] |

这是当前最接近远缘、同时仍有一定样本量的 identity 分层，但它仍由 BLAST 定义，所以只作
描述性结果；真正 `<20%` 的严格层仍只有个案。

## 如何解读 v0 与 v0.1

- `esm2_3b_cosine` 对 `esmc6b_cosine`：只比较 encoder 的检索几何，信息预算相同。
- `esm2_3b_supervised` 对 `esmc6b_supervised`：相同训练标签、分类器 family、超参数、fold 与
  阈值协议，最接近 H1/H2 实际检测器的公平比较。
- H3 没有参与：v0 和 v0.1 都使用同一个 ESM-C 6B H3，而且 H3 是 phylum 分类而非远缘检出。
- 任何在 99.5% specificity gate 失败的方法，其灵敏度不能称为“matched-specificity 提升”。

## 当前能与不能下的结论

能：内部开发集上的 component-holdout 泛化、低 FPR pAUROC、低覆盖压力层的描述性差值。

不能：外部 Test 提升、结构确认的超远缘提升、用 BLAST-failure 选样后再宣称优于 BLAST。
正式结论需要方法独立的结构/人工证据 lockbox，至少 100 个正 components、每 fold 至少 20 个。
