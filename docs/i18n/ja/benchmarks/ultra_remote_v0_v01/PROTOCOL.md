<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/PROTOCOL.md -->

この翻訳は閲覧の便宜のみを目的としています。凍結された英語の原文が正式な文書です。

# 凍結 protocol

## 目的

v0 H1/H2 encoder（ESM-C 6B）を v0.1 candidate（ESM-2 3B）に置き換えることで、
remote-component retrieval または supervised detection が改善するかを推定します。同時に、
現在の dataset が厳密な ultra-remote の問いに答えるには弱すぎる箇所を明示します。

## Data partition

- Train split のみ：グローバルに凍結された五つの component fold に 6,634 record。
- evaluation fold `k` に対して、次の fold を calibration とし、残りの三つを fit/reference fold
  とします。
- 一つの cycle 内で、component が fit/reference、calibration、evaluation の role をまたぐことは
  できません。
- Validation と Test の prediction count はゼロのままにする必要があります。

## Method layer

1. **Controlled encoder/readout：** 完全に同一の fit-fold DJR または viral MCP positive
   reference ID に対する maximum cosine。
2. **Task-adapted detector：** H1/H2 classifier family、hyperparameter、training label、fold、seed、
   thresholding rule は同一で、embedding だけが変わります。
3. **Classical context：** BLASTP、DIAMOND ultra-sensitive、MMseqs2、component HMM、PSI-BLAST、
   family HMM score は、再 fitting や再 scoring を行わず再利用します。

PSI-BLAST と family HMM は、controlled pairwise method より task-specific な情報を多く受け取る
ため、descriptive secondary comparator のままです。

## Threshold と endpoint

- 各 method/fold の threshold は、source と component で balance した weight を用い、対象
  specificity 99.5% で、適格な calibration negative のすべてから lock します。
- threshold は evaluation fold と各 difficulty stratum に変更せず適用します。stratum ごとの
  recalibration は認められません。
- Encoder endpoint：`FPR in [0, 0.005]` における component/source-balanced normalized partial
  AUROC。source-balanced independent negative-component unit のいずれかが 0.005 より大きい
  場合は、interpolate せず suppress します。
- Detector endpoint：lock された threshold での component-balanced sensitivity と、実際の
  evaluation specificity。specificity gate が失敗した場合、sensitivity gain を
  matched-specificity improvement と呼ぶことはできません。
- descriptive stratum の uncertainty は、calibration threshold を固定した paired
  evaluation-component bootstrap です。calibration uncertainty は含みません。v0 と v0.1 の
  両方が五つすべての evaluation fold で実際の 99.5% specificity を満たさない限り、paired delta
  を matched-specificity improvement とは呼びません。

## Difficulty stratum

| Stratum | 定義 | ステータス |
|---|---|---|
| Component holdout | すべての held-out positive component | 主な開発 generalization；自動的に ultra-remote とはならない |
| Low-coverage stress | 最良の evaluation-cycle BLAST hit の qcov <80% | descriptive で BLAST-defined の proxy |
| Twilight identity | qcov >=80% かつ 20% <= identity <30% | descriptive で BLAST-defined |
| Identity <20%, any coverage | 最良の BLAST identity <20% | exploratory case series |
| Strict ultra-remote proxy | qcov >=80% かつ identity <20% | exploratory case series のみ |

最良の BLAST hit は、parent benchmark ですでに凍結された permissive E-value 1000 search から、
maximum bit score により選択します。no-hit subset は意図的に headline に使用しません。比較対象
method の失敗によって cohort を定義すると、その method に不利な selection bias が生じるためです。

## 正式な ultra-remote claim に必要な証拠

- scored competitor に含まれない独立 stratifier。
- 全体で少なくとも 100 positive independent component、各 fold で少なくとも 20。
- 信頼できる 99.5% specificity gate のため、source/fold ごとに少なくとも 600
  calibration-negative component が望まれます。
- External lockbox calibration と Test。label または score を開いた後は tuning しません。
