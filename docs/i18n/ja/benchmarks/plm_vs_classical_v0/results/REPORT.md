<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/results/REPORT.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# 内部 CROSS-FITTED 開発 BENCHMARK — 外部 TEST ではありません

これは内部の循環 component-cross-fitted 開発比較であり、外部での優越性を主張するものではありません。Headline は事前に固定されています。ESM-C 6B cosine retrieval を、登録済みの各 classical anchor と個別に比較し、post-hoc に最良の baseline を選択しません。

## 経験的分解能 audit

Endpoint は引き続き 99.5% specificity に固定しますが、その経験的分解能を、無条件の low-FPR evidence として扱わず、別に報告します。

| Task | Sensitivity inference status | Zero-FP granularity cycles | Singleton calibration sources | Singleton evaluation sources | Low-positive-component folds |
|---|---|---|---|---|---|
| h1_djr | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP | 1,2,3,4,5 | none | none | none |
| h2_vma_conditional | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED | 1,2,3,4,5 | cycle 2 / cal fold 3: cellular_djr_none 62/1 records/components | fold 3: cellular_djr_none 62/1 records/components | fold 2: 119/18 records/components |
| vma_end_to_end | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED | 1,2,3,4,5 | cycle 2 / cal fold 3: cellular_djr_none 62/1 records/components | fold 3: cellular_djr_none 62/1 records/components | fold 2: 119/18 records/components |

具体的には、fold 3 は cellular-DJR negative record を 62 件含みますが、global component は一つだけです。Cycle 2 では、これが H2 calibration source です。各 row が negative mass の 1/62 を持つため、99%、99.5%、99.9% のすべてで、経験的 false positive をゼロにする必要があります。同じ source は、fold 3 を評価するとき、一つの独立した negative component になります。
一つの component からなる fold/source stratum では、bootstrap multiplicity が一に固定されます。したがって component 間の calibration/evaluation variation は推定できず、影響を受ける sensitivity delta interval は、観察されたその component を条件とします。Fold 2 にも独立した VMA-positive component が 18 個（119 record）しかないため、aggregate value には fold range と component count を併記する必要があります。

## Controlled primary comparison

AP は、五つの evaluation-fold component-balanced AP 値の macro-average です。Sensitivity は各 cycle 専用の calibration fold を 99.5% source-balanced specificity で使用します。その interval は paired global-component bootstrap delta interval であり、上記の resolution status の制約を受けます。

| Task | Classical anchor | ESM-C cosine AP | Anchor AP | AP delta (95% CI) | ESM-C sensitivity | Anchor sensitivity | Sensitivity delta (95% CI) | Sensitivity status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| h1_djr | blastp | 0.8719 | 0.9392 | -0.0672 (-0.0998, -0.0347) | 0.7340 | 0.8692 | -0.1353 (-0.1899, -0.0523) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | diamond_ultra | 0.8719 | 0.9406 | -0.0687 (-0.1024, -0.0345) | 0.7340 | 0.9025 | -0.1686 (-0.2170, -0.0979) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | mmseqs_s7.5 | 0.8719 | 0.9319 | -0.0600 (-0.0932, -0.0256) | 0.7340 | 0.8805 | -0.1466 (-0.2034, -0.0722) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | hmmer_component | 0.8719 | 0.9542 | -0.0823 (-0.1119, -0.0521) | 0.7340 | 0.9016 | -0.1676 (-0.2236, -0.1023) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h2_vma_conditional | blastp | 0.9861 | 0.9829 | +0.0032 (-0.0102, +0.0211) | 0.9306 | 0.9443 | -0.0138 (-0.0599, +0.0307) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | diamond_ultra | 0.9861 | 0.9806 | +0.0054 (-0.0112, +0.0268) | 0.9306 | 0.9317 | -0.0011 (-0.0479, +0.0434) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | mmseqs_s7.5 | 0.9861 | 0.9751 | +0.0109 (-0.0051, +0.0303) | 0.9306 | 0.9119 | +0.0187 (-0.0367, +0.0685) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | hmmer_component | 0.9861 | 0.9911 | -0.0050 (-0.0194, +0.0102) | 0.9306 | 0.9569 | -0.0263 (-0.0712, +0.0179) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | blastp | 0.9528 | 0.9544 | -0.0017 (-0.0328, +0.0334) | 0.9301 | 0.9401 | -0.0100 (-0.0557, +0.0343) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | diamond_ultra | 0.9528 | 0.9497 | +0.0031 (-0.0294, +0.0398) | 0.9301 | 0.9317 | -0.0015 (-0.0471, +0.0439) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | mmseqs_s7.5 | 0.9528 | 0.9317 | +0.0211 (-0.0140, +0.0600) | 0.9301 | 0.9078 | +0.0223 (-0.0300, +0.0746) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | hmmer_component | 0.9528 | 0.9660 | -0.0132 (-0.0427, +0.0203) | 0.9301 | 0.9569 | -0.0267 (-0.0708, +0.0197) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |

## その他の controlled-primary PLM comparator

この controlled PLM comparator を、登録済み classical anchor の代わりには使用しません。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| esm2_650m_cosine | h1_djr | 0.9515 (0.9152–0.9744) | 0.8954 (0.8371–0.9432) |
| esm2_650m_cosine | h2_vma_conditional | 0.9965 (0.9827–1.0000) | 0.9977 (0.9894–1.0000) |
| esm2_650m_cosine | vma_end_to_end | 0.9906 (0.9639–1.0000) | 0.9859 (0.9400–1.0000) |

## Resource-augmented secondary

PSI-BLAST は iterative positive-database enrichment を使用し、secondary のままです。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| psiblast_longest_seed_positiveDB_3iter | h1_djr | 0.9705 (0.9365–0.9958) | 0.9493 (0.8958–0.9894) |
| psiblast_longest_seed_positiveDB_3iter | h2_vma_conditional | 0.9982 (0.9913–1.0000) | 0.9750 (0.9574–1.0000) |
| psiblast_longest_seed_positiveDB_3iter | vma_end_to_end | 0.9899 (0.9685–1.0000) | 0.9750 (0.9574–1.0000) |

## Metadata-grouped secondary

Family-grouped HMMER は固定された grouping metadata を使用し、secondary のままです。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| hmmer_family | h1_djr | 0.9971 (0.9915–1.0000) | 0.9957 (0.9890–1.0000) |
| hmmer_family | h2_vma_conditional | 0.9994 (0.9971–1.0000) | 0.9806 (0.9444–1.0000) |
| hmmer_family | vma_end_to_end | 0.9931 (0.9829–1.0000) | 0.9806 (0.9444–1.0000) |

## Operational supervised、記述のみ

Supervised ESM-C system は labelled negative から学習するため、primary の対象にはなりません。

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| esmc6b_supervised | h1_djr | 0.9945 (0.9846–0.9999) | 0.9753 (0.8923–1.0000) |
| esmc6b_supervised | h2_vma_conditional | 1.0000 (1.0000–1.0000) | 1.0000 (1.0000–1.0000) |
| esmc6b_supervised | vma_end_to_end | 0.8723 (0.6297–0.9792) | 0.8000 (0.0000–1.0000) |

PSI-BLAST は resource-augmented secondary evidence、family-grouped HMMER は metadata secondary evidence、supervised ESM-C は operational descriptive evidence のみです。
Pooled raw AP は secondary diagnostic としてのみ維持します。99.9% ladder は `RESOLUTION_LIMITED_SECONDARY` であり、この cohort から FP-per-million は推定できません。
両方の primary metric の uncertainty には、10,000 回の paired global-component replicate を使用しました。Delta 95% interval だけを報告し、bootstrap sign fraction を P value として提示せず、Holm adjustment も生成しません。
Source-specific calibration/evaluation check、distance stratum、approximate MDE、profile construction、reference contract、runtime receipt は、付属する TSV file にあります。
