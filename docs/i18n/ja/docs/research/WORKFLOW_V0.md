<!-- i18n-mirror: non-authoritative translation; source=docs/research/WORKFLOW_V0.md -->

> **翻訳について：** この翻訳は閲覧用です。凍結済みの中国語原文を正式版とします。

# DJR-MCP Finder project V0：完全ワークフロー

ステータス：主要リリースの **all ESM-C 6B は凍結済み**です。Schema 5 Amendment D は、八モデル／
mixed Head を四情報源で解析する、現在最も広範な補助解析です。Schema 4 は二モデルの連続性
ベースラインとして保持します。いずれの robustness 解析も独立 Test ではなく、V0 にフィードバック
することもできません。

```text
data-curation V3 -> project V0
 -> 11,060 representatives
 -> component-safe Train / Validation / Test
 -> 14-model shared Train-CV
 -> Validation calibration + gates + paired one-SE
 -> freeze all ESM-C 6B
 -> user inference release
 -> post-freeze schema 4 / schema 5 diagnostics (read-only)
```

## 1. 三つの cascade Head

```text
protein
 └─ H1: DJR?
     ├─ no  -> non_djr
     └─ yes -> H2: viral morphogenesis-associated?
               ├─ no  -> cellular DJR / none
               └─ yes -> H3: known phylum or reject
```

| Head | 学習範囲 | タスク | 主要開発指標 |
| --- | --- | --- | --- |
| H1 | 全タンパク質 | DJR / non-DJR | AP |
| H2 | DJR | VMA-DJR / cellular DJR | AP；Validation では macro-F1 も確認 |
| H3 | 十分なサンプルを持つ二つの VMA phyla | Nucleocytoviricota / Preplasmiviricota + reject | known-class macro-F1 |

H3 の 560 件の VMA-DJR は、Nucleocytoviricota 415、Preplasmiviricota 117、Produgelaviricota 26、
literature-unclassified 2 で構成されます。前二クラスの合計 532 件が既知クラスの fitting に参加し、
残りの 28 件は reject diagnostic にだけ使用します。`unknown/other` は「二つの既知クラスのいずれにも
強制的に入れない」という意味であり、新しいウイルスや新しい phylum の発見を意味しません。

## 2. データと component-safe split

| source set | representatives | H1 | H2 |
| --- | ---: | --- | --- |
| VMA-DJR data-curation V3 | 560 | positive | positive |
| cellular DJR | 500 | positive | negative |
| hard non-DJR | 5,000 | negative | N/A |
| background non-DJR | 5,000 | negative | N/A |
| total | **11,060** | — | — |

上流 V3 には 564 件の official cluster rows があり、exact-sequence の重複除去後には 560 件の
モデリング陽性が残ります。バージョン対応は常に `data-curation V3 -> project V0` です。

分割前に、次の関係の推移閉包を取ります。

1. 正規化後に完全同一の配列；
2. 同一 source cluster；
3. 既存の legacy/global component；
4. identity≥30%、双方向 coverage≥80% の qualifying MMseqs2 relation。

完全な component は一つの split にだけ入れることができます。

| split | records | DJR / non-DJR | VMA-DJR |
| --- | ---: | ---: | ---: |
| Train | 6,634 | 634 / 6,000 | 336 |
| Validation | 2,212 | 212 / 2,000 | 112 |
| Test | 2,214 | 214 / 2,000 | 112 |

全グラフには 27,427 nodes と、モデリング代表を含む 9,262 個の global components があります。
quarantined model representatives=0、full-search residual qualifying cross-split edges=0 です。この
ゲートは強い相同性による漏洩リスクを減らしますが、30% identity 未満に遠隔相同性が存在しないことを
証明するものではありません。

## 3. 14-model benchmark

すべてのモデルは、同じ manifest、split、Train-only `global_component_id` 5-fold map を読み込みます。
Checkpoint revision、precision、window、stride、pooling、checksum は固定します。長い配列は全長を
覆う sliding window で処理し、padding と special token は residue mean に含めません。

```text
S = 0.60 * CV H1 raw-score AP
  + 0.30 * CV H2 raw-score AP
  + 0.10 * CV H3 known-class macro-F1
```

Validation gate では、各 Head の fresh ESM-2 650M baseline に対する低下が 0.01 以下であることを
要求します。gate 通過後、共通 fold に paired one-SE を適用します。速度は、定義が完全に比較可能な
場合にだけ最終段階のコスト判定基準として使用します。

順位指標には raw `decision_function` を使用しなければなりません。旧 Figure 1a は sigmoid probability
から AP を計算し、正確な 0/1 に飽和したため、誤って `0.857107` を生成しました。同じ ESM-2 650M
fold predictions の raw-score AP は `0.997917` です。これは数値上の修正であり、新しいデータや
新しい生物学的エビデンスではありません。

| model | rank | `S` | gate |
| --- | ---: | ---: | --- |
| **ESM-C 6B** | 1 | **0.997145** | PASS / selected |
| ESM-2 3B | 2 | 0.994873 | PASS |
| ESM-C 300M | 3 | 0.993444 | PASS |
| ESM-2 650M | 8 | 0.990376 | baseline PASS |

完全な 14-model 表は `results/model_benchmark_v0_metric_revision_1/model_comparison.tsv` にあります。

## 4. 較正、凍結パラメータ、Test 境界

Temperature は probability scale だけを変え、raw-score の順位は変えません。H1 threshold は
Validation で MCC を最大化し、H2 は macro-F1 を最大化します。H3 reject threshold は Validation の
既知クラスだけを使用し、known acceptance が 0.95 付近になるようにします。rare/unclassified records
は H3 threshold の選択に参加しません。

| Head | classifier | temperature | decision/reject threshold |
| --- | ---: | ---: | ---: |
| H1 | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

過去の 2,214-record Test は ESM-2 650M に対してだけ開かれました。同じ凍結 prediction の数値追跡値は
H1 AP=0.998068、AUROC=0.999724、FPR@95% recall=0 ですが、これらを ESM-C 6B に帰属させることは
できません。現在の all-6B と schema 5 の全候補は `test_status=not_evaluated` です。新しい
prospective/external Test は、プロトコルを先に凍結した後、一度だけ開く必要があります。

## 5. HardNeg 情報源の復元

V0 に使用した過去の四バッチ DAG は、凍結済み入力から完全に再実行されています。

```text
172,346 raw
 -> 42,266 strict rows / 42,264 unique
 -> 36,138 Tier1 members
 -> 10,880 representatives
 -> 10,878 H1-negative pass + 2 quarantine
 -> 5,000 selected
```

93/93 search units の検証が完了し、A/B member map は一致しました。retained representatives、selected
artifacts、再構築結果はバイト単位で同一または意味的に同等です。G0–G6 は 7/7 PASS、ステータスは
`FULL_OPERATIONAL_RECOVERY_PASS` です。後に行った六バッチ拡張の 57,708 Tier1 / 18,819
representatives は別の探索であり、V0 には含まれません。

復元結果は、selected HardNeg clusters にだけ matched members を提供します。11,060 件の代表、split、
モデル、パラメータ、Test は変更しません。旧 5,878 pass-but-unselected representatives は過去の
unpaired sensitivity であり、selected-cluster members として示してはなりません。

## 6. Schema 4：二モデルの連続性ベースライン

Schema 4 は、凍結済み all-6B と ESM-2 650M に対して、四情報源かつ適用可能な Head の
matched-family baseline を構築します。

| source | legal clusters / members / blocks | all-6B full path | ESM-2 650M |
| --- | ---: | ---: | ---: |
| viral | 69 / 13,054 / 32 | 0.9536 | 0.9325 |
| cellular | 43 / 391 / 12 | 0.8791 | 0.9997 |
| background | 1,000 / 3,000 / 893 | 0.9948 | 0.9974 |
| selected HardNeg | 382 / 3,478 / 237 | 0.9978 | 1.0000 |

四情報源を統合した総合スコアは作りません。統計では equal dependence block→source cluster→member
の重み付け、固定 seed 20260724、10,000 回の paired bootstrap を使用します。negative-only 情報源は
specificity/FPR だけを報告し、AP、AUROC、F1 は計算しません。すべての member−representative delta
の 95% CI が 0 を含みます。all-6B の主な弱点は cellular H1 です。

Schema 4 の独立検証は PASS です。22 endpoints が一致して再計算され、predictions=92,844、
expected paths=39,846、HardNeg H2/H3=0、Test=0 です。現在は schema 5 の checksum-bound continuity
baseline であり、最新かつ最も広範な結論ではありません。

## 7. Schema 5：八モデルと mixed Head

### 7.1 固定設計

Schema 5 は schema 4 と同じ四情報源の有効 cohort を使用し、高コストの拡張を、元の 14-model
benchmark で固定 candidate boundary を満たした 8 個のモデルに限定します。ESM-2 650M/3B、
ESM-C 300M/600M/6B、ProtT5-XL-U50、ProstT5、ESM3-open 1.4B です。

第一層は 8 個の homogeneous systems、第二層は事前登録済みの 9 個の mixed candidates だけです。

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

H1/H2 は encoder を共有します。H1→H2 を通過して viral path に到達した場合にだけ、二つ目の H3
encoder を呼び出します。任意の 8³ 組合せは検索していません。candidate ordering には既存の共通
Train-CV `S` だけを使用します。robustness は all-6B に対する source-specific inferiority warning だけを
確認し、各情報源内で Holm 補正を行います。

### 7.2 Homogeneous 結果

| system | viral | cellular | background | matched HardNeg |
| --- | ---: | ---: | ---: | ---: |
| ESM-2 650M | 0.9325 | 0.9997 | 0.9974 | **1.0000** |
| ESM-2 3B | 0.8949 | **1.0000** | 0.9985 | 0.9998 |
| ESM-C 300M | 0.9060 | 0.9620 | 0.9907 | 0.9988 |
| ESM-C 600M | 0.9063 | 0.8790 | 0.9966 | **1.0000** |
| ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 |
| ProtT5-XL-U50 | 0.9084 | 0.7960 | 0.9991 | 0.9958 |
| ProstT5 | 0.9078 | 0.9877 | 0.9989 | **1.0000** |
| ESM3-open 1.4B | **0.9685** | 0.8885 | 0.9989 | **1.0000** |

四情報源すべてで勝つ homogeneous model はありません。情報源間のトレードオフは実在し、事後的な
平均によって隠してはなりません。

### 7.3 Mixed nominee とコスト

| candidate | Train-CV `S` | always-on s·seq⁻¹ | worst-case s·seq⁻¹ |
| --- | ---: | ---: | ---: |
| **H1/H2 ESM-2 3B + H3 ESM-C 6B** | **0.997645** | **0.023524** | 0.083055 |
| all ESM-C 6B | 0.997145 | 0.059531 | **0.059531** |
| H1/H2 ESM-2 650M + H3 ESM-C 6B | 0.996813 | **0.007405** | 0.066935 |

nominee=`h12_esm2_3b__h3_esmc_6b`：

| source | expected path (95% CI) | strict clusters |
| --- | ---: | ---: |
| viral | 0.9537 (0.9131–0.9872) | 52/69 |
| cellular | 1.0000 (1.0000–1.0000) | 43/43 |
| background | 0.9985 (0.9963–1.0000) | 997/1,000 |
| matched HardNeg | 0.9998 (0.9995–1.0000) | 381/382 |

all-6B に対する Holm-corrected warnings は `0/4` ですが、これは四情報源の
non-inferiority/equivalence の証明ではありません。viral strict clusters は all-6B の 55/69 より少なく、
H3 worst-case では二つの encoders を実行する必要があります。正式なステータスは
`recommended_for_external_confirmation` にすぎず、`released_v0_change_permitted=0` です。

### 7.4 H3 境界

nominee の H3 は all-6B と同じです。Nucleocytoviricota F1=0.9792、Preplasmiviricota F1=1.0000、
Produgelaviricota reject=6/7（2 parents/blocks）、literature-unclassified=1/1（1 parent、推定可能な CI
なし）です。二群は分ける必要があり、pooled 7/8 は secondary diagnostic にすぎません。

## 8. Schema 5 の完全性

- result status=`complete_eight_model_nine_candidate_four_source`；independent validation **20/20 gates PASS**、289 endpoints を一致して再計算；
- 18 個の新規 materialization receipts + 6 個の reuse attestations = 24/24；
- schema 4 の 92,844 keys、464,220 numeric strings は、凍結済み Python 3.11.7／四スレッド数値演算子で exact replay し、numeric/semantic/derived-decision mismatches=0；
- single-model predictions=371,376；system predictions=789,174；expected paths=338,691；bootstrap rows=680,000；Test records=0；
- Amendment D は、predictions、thresholds、CV scores、candidate order など 7 個の正式 contract artifacts について Amendment C とバイト単位で同一；H3 subgroup endpoints は凍結済み manifest から独立に再計算；
- compact result 17/17 checksum PASS；元の a–e figure package 11/11 PASS。アクティブな主図は読み取り専用 head-focus companion を使用：top release 4/4、ディレクトリ内 13/13 checksum PASS；56 Head endpoints、32 path cells、9 recipes、4 nominee diagnostics は正式結果とフィールド単位で一致し、新しい科学的結論を生成しない。

Amendments A–D の failure closure、数値演算子、表示 contract の詳細は
`VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_PROTOCOL.md` に保持し、主要ワークフローでは
繰り返しません。

## 9. 完了済みの PLM-vs-classical 内部 benchmark

### 9.1 設計と公平性の境界

この benchmark は凍結済み Train の 6,634 records だけを使用します。既存の五つの
`global_component_id` folds が、3-fit/reference、1-calibration、1-evaluation を巡回して担当します。
同じサイクルの reference/profile/model は calibration または evaluation を読み込みません。
Validation/Test prediction rows はいずれも 0 です。

三つのタスクは H1 DJR detection、H2 VMA|DJR、VMA end-to-end です。Controlled primary トラックでは、
ESM-C 6B cosine、BLASTP、DIAMOND、MMseqs2、component-HMMER が同じ positive reference IDs を共有し、
ESM-2 650M は別個の controlled PLM context です。PSI-BLAST、metadata-family HMM、outer fold ごとに
再 fitting する supervised ESM-C は、異なる supplementary/operational tracks に属し、controlled
headline には混ぜません。

Primary metrics は、五つの evaluation folds の component-balanced AP macro-average と、独立した
calibration fold で 99.5% specificity-target threshold を選択した後の evaluation sensitivity です。
99.9% は `RESOLUTION_LIMITED_SECONDARY` としてのみ扱い、FP-per-million は推定できません。

### 9.2 正式な内部結果

| method | H1 AP / sens. | H2 AP / sens. | VMA e2e AP / sens. |
| --- | ---: | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 | 0.9528 / 0.9301 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 | 0.9544 / 0.9401 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 | 0.9497 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 | 0.9317 / 0.9078 |
| component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 | 0.9660 / 0.9569 |
| ESM-2 650M cosine, context | 0.9515 / 0.8954 | 0.9965 / 0.9977 | 0.9906 / 0.9859 |

ESM-C cosine と四つの classical anchors の比較では、H1 AP と sensitivity delta の 95% CI はすべて
負であり、H2 と e2e の事前登録済み CI はすべて 0 をまたぎます。これは「ESM-C cosine retrieval が
古典的ツールより高感度」という主張を支持しません。また、凍結済み supervised V0 classifier の
外部性能と同じものでもありません。

### 9.3 検証と制限

- validation=PASS；250,236 query-score rows、27 primary rows、12 paired deltas；Test/Validation rows=0；
- 点推定値は独立実装で再計算；`bootstrap_recomputed=false` であり、validator は CI schema、range、order、replicate count、registry だけを確認するため、10,000 bootstrap のすべてを独立に再実行したと記載できない；
- fold 3 の 62 個の cellular negatives は一つの component だけに属し、fold 2 の 119 VMA positives は 18 components だけに属するため、H2/e2e low-FPR intervals は conditional/resolution-limited；
- equal task-specific references は未知の PLM pretraining exposure を解消しない；
- 完全な元リリースの 20,424 件の checksum は PASS。アクティブコピーでは 3 個の figure source-data TSV が欠落していたが、凍結済み結果から決定論的に再構築した後、SHA は元の manifest と項目ごとに一致し、完全な compact figure release を復元。

内部 P0/development comparison は完了しました。source-component-disjoint external lockbox、99.9%
specificity/FPM、より完全な PLMSearch/pLM-BLAST/hybrid matrix は、引き続き prospective planned
ステータスです。

## 10. V0/V0.1 ultra-remote 開発監査

V0.1 は H1/H2 encoder だけを ESM-2 3B に変更し、H3 は引き続き ESM-C 6B を使用します。同じ
Train-only cyclic cross-fit を再利用し、raw cosine encoder と、同じ classifier family の
task-adapted detector を比較します。

| endpoint | all holdout Δ(v0.1−v0) | `qcov<80%` | `qcov≥80%, 20–30% identity` |
| --- | ---: | ---: | ---: |
| H1 encoder sensitivity | +0.197 | +0.260 (0.206–0.317) | +0.046 (0.013–0.086) |
| H1 detector sensitivity | +0.017 | +0.028 (0.011–0.049) | 0.000 |
| H2 encoder sensitivity | +0.049 | +0.062 (0.020–0.112) | +0.024 (0.001–0.057) |
| H2 detector sensitivity | 0.000 | 0.000 | 0.000 |

encoder signal は operational detector の利得に比例して変換されません。すべての paired systems は
少なくとも一つの fold で実際の 99.5% specificity に達していません。V0.1 H2 detector の
minimum-fold specificity=0.5426、V0 は 0.8599 です。strict `qcov≥80%, identity<20%` stratum には
1 個の independent positive component しかなく、事前登録した合計 100／fold 当たり 20 の閾値を
下回ります。BLAST-defined strata 自体にも method-conditioned bias があります。

Validation ステータスは `PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE` です。プロセスは
PASS ですが、matched-specificity、external Test、formal ultra-remote claims はすべて成立しません。
V0.1 development workflow は released V0 から隔離しなければなりません。

## 11. アクティブファイル、アーカイブ、実行場所

| role | active path |
| --- | --- |
| frozen model benchmark | `results/model_benchmark_v0_metric_revision_1/` |
| schema 5 compact results | `results/validation_family_robustness_v0_schema5_mixed_heads/` |
| schema 5 publication companion | `results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/` |
| PLM/classical compact benchmark | `benchmarks/plm_vs_classical_v0/` |
| V0/V0.1 compact audit | `benchmarks/ultra_remote_v0_v01/` |
| frozen model identity | `results/model_benchmark_v0_metric_revision_1/esmc_6b/FROZEN_MODEL_CHECKSUMS.sha256` |
| released user inference V0 | `user-inference-v0/` |
| unreleased user inference V0.1 candidate | `user-inference-v0.1/` |
| portable root research entrypoints | `scripts/run_v0_dataset.py`; `scripts/run_postsplit_integrity_audit.py` |

次の完全な schema 5 と schema 4 のパスは、元の gds2 generation の凍結済み provenance です。

- `/aptmp/hongda/DJRMCP_Develope/project-V0__validation-family-robustness-schema5-mixed-heads__20260728/schema5_v1_amendment_d/`
- `/aptmp/hongda/DJRMCP_Develope/project-V0__validation-family-robustness-schema4__20260728/schema4_v1/`

PLM benchmark の 7.6GB work/logs/databases と、ultra-remote の大規模な work/TIFF は、2026-07-29 の
日付付き checksum-bound archives にあります。アクティブパスには、protocol、code、正式 summary
tables、validation、PNG/PDF/SVG、source data だけを残します。

GPU は encoder embedding に使用し、statistics、checksum、大部分の validation は CPU 作業です。
ユーザー向けの二つのパッケージは GitHub checkout に含まれ、エントリーポイントは次のとおりです。

```bash
cd user-inference-v0
bash scripts/run_user_fasta.sh INPUT.faa OUTPUT_DIR cuda

cd ../user-inference-v0.1
bash workstation/run_user_fasta.sh INPUT.faa OUTPUT_DIR GPU_INDEX
```

V0.1 は引き続き `recommended_for_external_confirmation` の candidate package であり、V0 を置き換えません。
元の `/aptmp/hongda/DJRMCP_Develope/user-inference-V0` と
`hongda-133:/lab/hongda/user-inference-V0` は、過去の validation/deployment locations を記録するだけで、
現在の checkout の runtime dependencies ではありません。新しい解析は、V0 のモデル、三つの Head、
temperature、threshold、window、pooling を変更していません。

通常のユーザー予測は PBS、`qsub`、HPC scheduler に依存しません。

### 11.1 可搬パスと凍結済み provenance

リポジトリは任意の絶対パスに checkout できます。非凍結 launcher は `DJRMCP_PROJECT_ROOT`、
`DJRMCP_ARCHIVE_ROOT`、`DJRMCP_DATABASE_ROOT`、`DJRMCP_SOFTWARE_ROOT`、`DJRMCP_VENV_ROOT` を
使用します。既定の project root は script location から推定します。
凍結済み config は provenance と checksum の意味を維持するため、元の `/aptmp/...` 値を保持し、
その場で編集してはなりません。`scripts/render_portable_config.py` でローカル JSON/YAML copy を生成し、
launcher の `*_CONFIG` 環境変数から渡します。完全な例は `README.md` と `.env.example` にあります。

root の dataset 構築と split 後の integrity audit は、それぞれ `scripts/run_v0_dataset.py` と
`scripts/run_postsplit_integrity_audit.py` から scheduler なしで起動します。checksum-bound の
`benchmarks/*/pbs/` launcher は通常の runtime entrypoint ではなく、任意の歴史的 HPC replay evidence
としてのみ保持されます。Benchmark evidence bundle 内では削除または書き換えないでください。

GitHub packaging に際し、上記の可搬 launcher、documentation、release allowlist に対する source-level
manifests を再生成しました。これは科学的結果の再計算ではありません。凍結済みモデル、thresholds、
config、compact numerical evidence、その内部 artifact checksums は変わりません。元の gds2 entry
points の同一性は、日付付き archive provenance に残ります。

Schema-5 Amendment D の exact-numeric replay は、引き続き過去の Python/BLAS operator を確認します。
その `legacy_schema4_numerical_operator.venv_root` は通常の保存パスではなく、provenance contract です。
同じ attested environment でなければ fail closed しますが、リポジトリ内の compact evidence の閲覧や
検証には影響しません。production Test ledger も固定された外部 administrator registry に保持され、
公開 checkout が path override によって新しい Test authorization を得ることはできません。

## 12. 公表可能な範囲と次期バージョンのゲート

V0 で報告可能なのは、component-safe dataset、14-model development selection、凍結済み all-6B tool、
schema 5 family-neighbour robustness、Train-only と明記した内部 homology comparisons です。報告できない
のは、all-6B または V0.1 held-out Test performance、古典的ツールに対する PLM の外部優越性、formal
ultra-remote superiority、普遍的 unknown virus detection、clinical/diagnostic use です。

V1 に更新する前に、次を凍結する必要があります。

1. 現在の Train/Validation family から独立し、distance label が比較対象の手法で定義されない external lockbox；
2. 十分な strict `<20% identity` positive components（合計≥100、各 fold≥20）；
3. source-specific endpoints、99.9% specificity/FPM、multiplicity、power；
4. all-6B と V0.1 の一度限りの Test ledger、および accuracy/cost acceptance rules；
5. external gates の通過後にだけ、公開モデルと user-inference package の変更を許可すること。
