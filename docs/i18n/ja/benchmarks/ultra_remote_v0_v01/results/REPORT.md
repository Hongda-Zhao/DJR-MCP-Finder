<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/results/REPORT.md -->

この翻訳は閲覧の便宜のみを目的としています。凍結された中国語の原文が正式な文書です。

# v0 / v0.1 ultra-remote 開発評価レポート

## 一文の結論

この解析では、**凍結 component fold** と **BLAST-defined low-coverage stress stratum** において
v0.1 が v0 より優れているかを評価できます。しかし、厳密な ultra-remote superiority には
答えられません。`qcov >=80% 且 identity <20%` の independent positive-component count は
`{'h1_djr': 1, 'h2_vma_conditional': 1, 'vma_end_to_end': 1}` であり、事前登録した下限 100 を
大きく下回ります。

## v0.1 の v0 に対する差：すべての component holdout

| Task | Encoder sensitivity difference | Supervised-detector sensitivity difference | Encoder specificity | Detector specificity |
| --- | --- | --- | --- | --- |
| h1_djr | +0.197 | +0.017 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |
| h2_vma_conditional | +0.049 | +0.000 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |
| vma_end_to_end | +0.049 | +0.000 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |

差は v0.1 minus v0 です。両方の system が五つすべての evaluation fold で実際の 99.5%
specificity を維持した場合にのみ matched と表示します。それ以外の差は、固定 calibration
threshold 下での descriptive result であり、matched-specificity improvement とは呼べません。
ここで示されるのは Train-only component-level generalization だけであり、厳密な ultra-remote
generalization ではありません。

## BLAST-defined low-coverage stress stratum（qcov <80%）

| Task | Comparison layer | Independent components | Sensitivity difference | 95% paired CI |
| --- | --- | --- | --- | --- |
| h1_djr | encoder | 264 | +0.260 | [+0.206, +0.317] |
| h1_djr | task_adapted_detector | 264 | +0.028 | [+0.011, +0.049] |
| h2_vma_conditional | encoder | 100 | +0.062 | [+0.020, +0.112] |
| h2_vma_conditional | task_adapted_detector | 100 | +0.000 | [+0.000, +0.000] |
| vma_end_to_end | encoder | 100 | +0.063 | [+0.020, +0.113] |
| vma_end_to_end | task_adapted_detector | 100 | +0.000 | [+0.000, +0.000] |

この stratum は descriptive にのみ使用します。low coverage は、短い homologous segment、
domain fusion、truncation、真の remote relatedness のいずれによっても生じ得ます。また、比較対象
である BLAST が stratification を定義するため、PLM が BLAST より優れているという正式な主張には
使用できません。

## BLAST-defined twilight stratum（qcov >=80%、20% <= identity <30%）

| Task | Comparison layer | Independent components | Sensitivity difference | 95% paired CI |
| --- | --- | --- | --- | --- |
| h1_djr | encoder | 113 | +0.046 | [+0.013, +0.086] |
| h1_djr | task_adapted_detector | 113 | +0.000 | [+0.000, +0.000] |
| h2_vma_conditional | encoder | 106 | +0.024 | [+0.001, +0.057] |
| h2_vma_conditional | task_adapted_detector | 106 | +0.000 | [+0.000, +0.000] |
| vma_end_to_end | encoder | 106 | +0.025 | [+0.001, +0.057] |
| vma_end_to_end | task_adapted_detector | 106 | +0.000 | [+0.000, +0.000] |

これは、一定の sample size を保ちながら、現在もっとも remote homology に近い identity
stratum です。しかし、依然として BLAST-defined であるため、descriptive result にとどまります。
真の `<20%` strict stratum には、引き続き case-level evidence しかありません。

## v0 と v0.1 の解釈方法

- `esm2_3b_cosine` 対 `esmc6b_cosine`：同じ information budget で、encoder の retrieval
  geometry だけを比較します。
- `esm2_3b_supervised` 対 `esmc6b_supervised`：同じ training label、classifier family、
  hyperparameter、fold、threshold protocol を使用し、H1/H2 operational detector にもっとも
  近い公平な比較です。
- H3 は含めません。v0 と v0.1 は同じ ESM-C 6B H3 を使用し、H3 は remote-homology detector
  ではなく phylum classifier です。
- 99.5% specificity gate に失敗した method の sensitivity を「matched-specificity improvement」
  と呼ぶことはできません。

## 現時点で導ける結論と導けない結論

導ける結論：internal development set における component-holdout generalization、low-FPR pAUROC、
low-coverage stress stratum の descriptive difference。

導けない結論：external Test での改善、structure-confirmed ultra-remote improvement、BLAST-failure
で sample を選択した後の BLAST に対する superiority。正式な結論には、method-independent な
structure/manual evidence lockbox、少なくとも 100 positive component、各 fold で少なくとも 20
component が必要です。
