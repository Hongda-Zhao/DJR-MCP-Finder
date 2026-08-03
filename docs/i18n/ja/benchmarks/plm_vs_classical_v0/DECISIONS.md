<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/DECISIONS.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# 設計上の決定と除外事項

## 通常の five-fold OOF thresholding ではなく、3/1/1 を採用する理由

通常の OOF ranking は fold-specific AP には十分です。しかし、他の四つの OOF fit の score を使って fold *k* を calibration すると、それらの model/reference library 内で fold *k* を間接的に再利用することになります。また、規模が異なる maximum-similarity database 間で threshold を交換することにもなります。そのため循環 design では、三つの fit/reference fold、一つの専用 calibration fold、一つの evaluation fold を使用します。各元 component は一度評価され、一度 calibration に使われますが、同じ cycle 内で両方の役割を担うことはありません。

## Supervised ESM-C と family HMM を controlled headline に含めない理由

Supervised ESM-C system は labelled negative から学習しますが、controlled retriever が受け取るのは positive reference FASTA だけです。一方、family HMM grouping は、curated family/taxonomy metadata を使用します。どちらも有用な operational system ですが、controlled representation comparison に混在させると、sensitivity 差の由来が交絡します。

ESM-C 6B と classifier hyperparameter は、これらの fold/Validation を含む以前の開発で選択されました。各 cyclic fit 自体は calibration と evaluation component を training から除外していますが、その operational row は `selected_model_descriptive_only` と表示されます。

## 過去の project HMM bundle を使用しない理由

それらは固定 split より前に作成され、curation または exclusion logic に関与していました。この cohort で使用すると結果が循環的になります。ここで使用できるのは各 cycle 内で構築した Train-only profile だけです。過去の bundle は、将来、真に外部の cohort で評価できます。

## ここで 99.5% specificity を primary とする理由

現在の内部 cohort には、99.9% specificity を安定して推定できるだけの negative component がありません。特に conditional H2 で不足しています。将来の外部 Benchmark endpoint は引き続き 99.9% です。この内部 protocol では primary endpoint を 99.5% に明示的に修正し、99.9% を resolution-limited secondary と表示します。

## 一部の 99.5% sensitivity interval を conditional と表示する理由

固定 fold map は、独立 component より主に record 数で balance されています。Fold 3 の cellular-DJR negative 62 件は、すべて一つの component に属します。この fold は cycle 2 の H2 calibration fold であり、cycle 3 の H2 evaluation fold でもあります。そのため、cycle-2 calibration は 99.5% で false-positive record を一件も許容できません。また、single-component bootstrap stratum では component 間 uncertainty を表現できません。End-to-end VMA calibration は、他の negative source とともにこの cellular source を含むため、対応する source-specific limitation を継承します。

事前登録済みの estimand は維持し、その制約を別個の resolution-status field で公開します。FPR target を暗黙に緩和したり、conditional interval を外部 low-FPR evidence として扱ったりはしません。

## デプロイ済み PLMSearch を primary matrix に含めない理由

gds2 の PLMSearch module は、ESM-1b と外部で学習された SCOP/CATH similarity model を中心とする、commit されていない 2024 CPU deployment です。1,022 residue を超える配列を truncate し、score には方向性があります。この性質から、将来の exploratory resource tier としては有用ですが、project embedding の controlled な代替にはなりません。Primary PLM retrieval track は、完全に checksum で固定された ESM-C 6B と ESM-2 650M embedding を使用します。pLM-BLAST は gds2 にインストールされていません。
