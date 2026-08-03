<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/PROTOCOL.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# 固定 protocol：PLM と従来型 remote homology の比較

## 範囲と主張の境界

これは内部の手法開発比較です。Project data 上の component-cross-fitting で観察された内容を示すことはできますが、外部での優越性は示せません。Validation は以前のモデル開発で使用されており、保護された Test split は対象外です。PLM の pretraining exposure は完全には把握できないため、task-specific reference が同じでも、pretraining information の総量が同じとは限りません。

## Cohort と leakage control

- Cohort：固定 Train split の 6,634 record。
- Outer fold：`global_component_id` を key とする既存の five-fold map。
- Evaluation fold *k* に対し、calibration は fold `k mod 5 + 1` です。残る三つの fold だけを fitting/reference data とします。
- Calibration と evaluation は同じ fitted model/reference/profile を使用し、どちらも fitting、MSA、PSSM iteration に入ることはできません。
- 一つの fold 内で、同じ component が query と reference の両方に存在してはいけません。
- BLASTP、DIAMOND、MMseqs2、cosine retrieval、HMMER、PSI-BLAST は、task と fold ごとに同じ reference-ID manifest を共有します。
- HMM MSA と PSI-BLAST enrichment database に含められるのは reference ID だけです。
- Validation と Test record は、query、reference、profile member、threshold-fitting row、metric row として受け付けません。

## Task

| ID | Positive | Negative | Eligible rows | Reference set |
|---|---|---|---|---|
| `h1_djr` | viral VMA + cellular DJR | hard + background non-DJR | all Train | outer-Train DJR |
| `h2_vma_conditional` | viral VMA | cellular DJR | Train DJR only | outer-Train VMA |
| `vma_end_to_end` | viral VMA | cellular DJR + hard + background | all Train | outer-Train VMA |

## 手法

- `esmc6b_cosine` と `esm2_650m_cosine`：outer-Train positive reference に対する maximum cosine。Mean embedding は固定された project artifact です。
- `blastp`：maximum bit score、BLAST+ 2.17.0。
- `diamond_ultra`：maximum bit score、DIAMOND 2.2.4 `--ultra-sensitive`。
- `mmseqs_s7.5`：maximum bit score、MMseqs2 18-8cc5c、sensitivity 7.5、一回の iteration。
- `hmmer_component`：maximum full-sequence HMM bit score。Positive global component ごとに一つの Train-only model を使用します。Singleton model も保持して count します。
- `hmmer_family`：Train-only metadata group を使う同じ score です。Curated grouping が追加の supervision を与えるため、別に報告します。
- `psiblast_longest_seed_positiveDB_3iter`：positive component ごとに決定論的な longest seed を一つ選び、outer-Train positive-only database に対して最大三回 iteration します。Inclusion E-value は 0.002 で、enrichment 中に per-subject HSP truncation を行わず、その後、固定 PSSM で calibration fold と evaluation fold を検索します。
- `esmc6b_supervised`：project の固定設定を使い、outer fold ごとに H1/H2 model を再 fitting します。End-to-end score は、nested-cross-fitted の empirical H1 と H2 negative-tail evidence の最小値で結合します。

No-hit は正当な negative infinity score です。Tool または parser failure は missing/NA であり、正式な aggregation を無効にします。

## Metric と weighting

### 内部 low-FPR endpoint の修正

Section 12 は、99.9% specificity を、将来の十分な power を持つ外部 Benchmark のために予約しています。現在の内部 cohort では、この endpoint を確実に分解できません（特に H2 の cellular negative は 298 件だけです）。そのため protocol V0 は、内部 primary として 99.5% を事前登録し、99.9% は `RESOLUTION_LIMITED_SECONDARY` としてのみ維持します。この修正は、将来の外部 endpoint を変更しません。

### Aggregation 前の経験的分解能 audit

固定 fold に対する score-independent audit で、H2 にもう一つの制約が判明しました。Fold 3 は cellular-DJR negative record を 62 件含みますが、`global_component_id` は一つだけです（`V0GC_96fb96e7e076c167`）。Fold 3 が cycle 2 を calibration するとき、各 H2 negative record の weight は 1/62（1.61%）なので、99%、99.5%、99.9% threshold のすべてで、経験的 false positive をゼロにする必要があります。Fold 3 を cycle 3 で評価するとき、H2 specificity の独立した negative component は一つだけです。Component bootstrap は stratum の唯一の member を multiplicity one で保持するため、この source の component 間 variation を推定できません。

固定された 99.5% estimand を post hoc に変更することはありません。代わりに、影響を受ける sensitivity estimate と paired interval を、マシン可読な出力と report で conditional かつ resolution-limited と表示します。Fold 2 にも VMA-positive record が 119 件ありますが、positive component は 18 個だけです。そのため、すべての primary table に fold range と record/component count を保持します。これらの制約により、内部 H2 low-FPR endpoint を安定した外部 specificity estimate として扱うことはできません。

Primary metric は、fold-macro component-balanced average precision と、99.5% source-balanced specificity での sensitivity です。各 component はまず同じ mass を受け、その record がその mass を共有します。Threshold calibration では、negative source が同じ mass を受け、その source 内の component がさらに同じ mass を受けます。

Threshold は cycle 専用の calibration fold だけを使い、paired evaluation fold と同じ reference/model に対して score します。Inclusive tie は保守的に処理します。Sensitivity は 99% と 99.9% でも示します。後者は常に `RESOLUTION_LIMITED_SECONDARY` と表示します。FP-per-million endpoint は推定できません。

Fold-macro component-balanced AP と calibrated sensitivity の paired uncertainty は、いずれも 10,000 回の共通 component resample を使用します。各 replicate は一つの global component-multiplicity vector を抽出し、task、cycle、method、両方の metric で再利用します。各 method の calibration threshold は、その draw 内で再計算します。Paired percentile-bootstrap interval は記述的に報告します。Bootstrap sign fraction を null-hypothesis P value と表示せず、family-wise superiority claim も行いません。

## 停止条件

Controlled method 間で reference checksum/ID contract が一つでも異なる、query component が reference/profile に leak する、inclusion ledger に non-reference ID が含まれる、Test/Validation prediction row がゼロでない、method failure が no-hit として encode される、期待される score がない、または 99.9%/FP-per-million が安定した primary estimate として提示される場合、正式な summarization は失敗します。
