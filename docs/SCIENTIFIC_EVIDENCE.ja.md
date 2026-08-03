[English](SCIENTIFIC_EVIDENCE.md) | [简体中文](SCIENTIFIC_EVIDENCE.cn.md) | **日本語**

# 科学的エビデンスと解釈の境界

[ドキュメント一覧](README.ja.md) | [リポジトリ README](repository/README.ja.md) |
[再現性](REPRODUCIBILITY.ja.md)

このページでは、どの結果を使用すべきか、主要な数値が何を示すか、エビデンスがどの程度
強いか、そして本プロジェクトが現時点では何を主張できないか、という四つの問いに順番に
答えます。これは凍結済みのプロトコルと結果ファイルを置き換えるものではなく、その要約です。

## どの結果を使用すべきですか？

| 科学的結果 | エンコーダーシステム | 現在のステータス | 推奨用途 |
| --- | --- | --- | --- |
| **Model V0.1 Candidate** (`model-v0.1-candidate`) | H1/H2 に ESM-2 3B、H3 に ESM-C 6B | `recommended_for_external_confirmation` | **新規スクリーニングに推奨する現在の結果** |
| **Model V0** (`model-v0`) | H1/H2/H3 に ESM-C 6B | 公開済み・凍結済み | 正式な再現可能ベースラインおよびサポート対象のフォールバック |

「推奨」は、現在のスクリーニング経路と Train-CV による候補選定を表します。Model V0.1
Candidate が前向き外部テストに合格したことや、Model V0 を置き換えたことを意味しません。
Model V0 は非推奨のバージョンではなく、引き続き主要な科学的成果です。

## 主要な開発時の数値

以下の二つの表は、Train のみを用いた異なる開発プロトコルに由来します。V0 と V0.1 の比較は
同じ行の中だけで行い、二つの表をまたいで値を比較しないでください。

### 共通五折 Train-CV による候補選定

| 指標 ↑ | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: |
| 総合スコア `S`（平均 ± SE） | `0.9971 ± 0.0009` | **`0.9976 ± 0.0010`** |

両モデルとも、`S = 0.60·H1 AP + 0.30·H2 AP + 0.10·H3 macro-F1` です。表示された不確実性は、
共通五折のスコアの標本標準偏差を `sqrt(5)` で割った値であり、信頼区間ではありません。
公開済み V0 スナップショットは、H1 AP `0.998 ± 0.000`、H2 AP `1.000 ± 0.000`、H3
known-class macro-F1 `0.981 ± 0.010`（いずれも平均 ± SE）でした。太字は選定された候補を示す
ものであり、統計的有意性を主張するものではありません。

### 独立した巡回式 component-holdout 監査

| 全コンポーネント感度（記述的；fold-locked） | 陽性コンポーネント（n） | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: | ---: |
| H1 encoder DJR readout | 392 | `0.728` | `0.925` |
| H1 operational detector | 392 | `0.978` | `0.995` |
| End-to-end MCP cascade | 209 | `0.914` | `0.914` |

各サイクルでは三つの適合 fold、次の fold を較正、さらに一つを評価に使用します。手法、タスク、
サイクルごとに、公称 99.5% 特異度目標で別々の閾値を較正し、そのサイクルの評価 fold に変更せず
適用します。コンポーネント内ではレコードごとの検出値を平均し、その後、表では五つの評価 fold に
含まれる各ホールドアウトコンポーネントに同じ重みを与えます。これは監査のペア付き全コンポーネント
レポートで使用された集約方法です。

記述的な差が最も大きいのは H1 encoder readout です。凍結済みプロトコルの下でタスク適応型
検出器を適合して適用すると差は小さくなり、監査ではエンドツーエンドの MCP 感度に差は
観察されません。H3 は二つのシステム間で変わらないため、この監査から除外されました。

### 0.800 が現れた理由

凍結済み出力には、同じエンドツーエンド検出に対する二つの妥当なコンポーネント単位の要約と、
一つのレコードプール比較が含まれています。

| 集約方法 | Model V0 | Model V0.1 Candidate | 意味 |
| --- | ---: | ---: | --- |
| Equal-fold macro | `0.800` | `0.800` | fold 感度 `1/0/1/1/1` の平均 |
| All held-out components | `0.913876` | `0.913876` | `191/209` コンポーネントを検出；上記の全コンポーネント表 |
| All held-out records | `0.645833` | `0.645833` | `217/336` レコードを検出；コンポーネントを推定対象とした値ではない |

各 fold には `47/18/47/49/48` の陽性コンポーネントが含まれていました。このため equal-fold
平均では、18-component の第二 fold が最終値の 20% を占めます。一方、全コンポーネント推定では、
209 components のそれぞれに同じ重みを与えます。以前の README では `0.800` を単に
「感度」と呼んでいたため、この違いが隠れていました。

第二 fold のゼロは較正分解能の崖によるものであり、119 MCP 陽性の順位が条件付き H2 較正陰性より
低かったことを意味しません。両モデルとも、それらの H1 および H2 生スコアは、対応する較正陰性の
最大値を上回っていました。しかし H2 陰性の較正サブセットには、一つの独立コンポーネントに由来する
62 records しか含まれなかったため、経験的裾部のエビデンスは
`log10(63) = 1.7993405494535817` で飽和しました。cascade endpoint では、12 個の V0 較正陰性と
15 個の V0.1 較正陰性がその飽和スコアを共有し、情報源とコンポーネントで均衡化した同点ブロックの
質量はそれぞれ `0.007199` と `0.008380` で、許容される `0.005` を上回りました。このため、凍結済みの
保守的な `score >= threshold` 規則は閾値を次の浮動小数点値 `1.7993405494535819` に移し、同点全体を
棄却しました。したがって、`0.800` の計算は内部的には再現可能ですが、説明を伴わない公開 recall 値
としては不適切です。

この説明と代替集約は、[V0 parent pointer](../benchmarks/plm_vs_classical_v0/FULL_ARTIFACT_POINTER.json) と
[V0/V0.1 audit pointer](../benchmarks/ultra_remote_v0_v01/FULL_ARTIFACT_POINTER.json) に記録された、
アーカイブ済みの全行台帳に照らして検証しました。V0 親台帳は SHA-256
`d21bf8534a04b98a11f7502ce275dc6ff346b43d4433ba5551c223e77d904fdb` と一致し、V0.1 台帳は
`b27a96a9ea7c26ab2c47ae2b3a7d5156cb775a9eab935a6cd17a87caed6ed2fa` と一致しました。独立した再計算により、
表示されている全 fold 閾値、fold 感度、評価特異度、および上記の全コンポーネント値が再現されました。
アーカイブマニフェストは SHA-256
`6273f88a618726046162f9e83cbfb447602796c0e9bb7d68af92440faf023ab7`
（V0 parent benchmark）および
`dcd33fa981f4064a027e9d27a184cba947bfd16f3c2c85030e0288d509215384`（V0/V0.1 audit）と一致しました。

## エビデンスの階層

| エビデンス | ステータス | 答えられること | 答えられないこと |
| --- | --- | --- | --- |
| 14-model V0 selection | 凍結済みの開発時選択 | どの単一エンコーダーシステムが Model V0 として選ばれたか | 外部データへの汎化 |
| Schema 5 Amendment D | 20/20 gates PASS | 同じ四つの情報源に由来するファミリーメンバーにおける、八つのモデルと九つのカスケードの選択後整合性 | 独立 Test の性能、同等性、またはモデル選択へのフィードバック |
| PLM versus classical V0 | Internal cross-fit PASS | 宣言された情報量の制約下における Train コンポーネント間の検索性能差 | 外部データにおける優越性 |
| Ultra-remote V0/V0.1 audit | PASS；formal claim blocked | 内部ホールドアウトと低カバレッジストレス層における記述的挙動 | 正式な `<20% identity` 結論 |
| Prospective external Test | **未実施** | — | Model V0 または Model V0.1 Candidate の公開品質の汎化性能 |

## これらの結果が確立していないこと

- Model V0 と Model V0.1 Candidate のいずれにも、新しい前向き外部テストはありません。
- 過去の Test 結果は ESM-2 650M のみに適用され、all-ESM-C-6B V0 システム、Schema 5 nominee、
  Model V0.1 Candidate には適用されません。
- ペア付き fold 較正システムはすべて、少なくとも一つの評価 fold で意図した 99.5% 特異度を
  満たしていません。したがって感度差は記述的であり、特異度を揃えた改善ではありません。
- BLAST で定義した strict `qcov≥80%, identity<20%` stratum には、一つの独立した陽性コンポーネント
  しか含まれず、正式な ultra-remote 結論には少なすぎます。
- H3 は V0.1 における改善ではありません。両システムは同じ ESM-C 6B H3 model を使用します。
- このエビデンスは、Model V0.1 Candidate が Model V0 を置き換えたことや、外部データで PLMs が
  古典的手法を上回ることを示していません。
- `mcp::unknown/other` は、サポート対象の二つの門のいずれかへの強制的な割り当てを棄却します。
  これは汎用的な未知ウイルス検出器または分布外検出器ではありません。

## 詳細なエビデンス

### 公開済み Model V0

- データ：560 viral MCP-DJRs、500 cellular DJRs、5,000 HardNeg タンパク質、5,000 background
  タンパク質。

#### 開発用サンプル構成

凍結済み開発データセットには、**11,060 exact-sequence-unique representative proteins** が含まれます。
以下の簡潔な一覧と展開可能な分類表が、`Design-0728.pptx` の slide 5 を再現した公開 sample list
です。11,060 行の構築 manifest はローカルのソースデータパスを含むため、このリポジトリでは
配布しません。公開記録には、代わりに集計数と checksum で固定されたエビデンス成果物を使用します。

| データセット群 | N | 構成と構築方法 |
| --- | ---: | --- |
| Viral DJR-MCP | 560 | Gold 65 と Silver_R3 495；陽性情報源の詳細は下記 |
| Cellular DJR | 500 | GH172/DUF2961 64；PHM/PAM 290；PNGase F 85；SIDT/SID-1/ChUP 56；DeCLIC-like DJR NTD 5 |
| Hard non-DJR | 5,000 | PPT の 36-seed 構築セットから拡張した、構造的裏付けがある β-sheet-rich のウイルスおよび細胞性 non-DJR decoys |
| Background non-DJR | 5,000 | 他の三群との配列、HMM、構造上の関連性を除外した後に保持された Swiss-Prot representatives |
| **合計** | **11,060** | 凍結済み component-safe 分割前の exact-sequence-unique representatives |

cellular-DJR と HardNeg の構築概要では、`qTM > 0.7` と `LDDT > 0.5` による非ウイルス構造拡張を
使用しています。リポジトリには最終的な 5,000 行の HardNeg 一覧が含まれ、その上流メタデータは
checksum で固定されていますが、36 PPT seed families の簡潔な行単位の一覧は含まれていません。
したがって、その seed count は構築時の注記であり、リポジトリだけで完全に監査できる一覧では
ありません。

| ウイルスエビデンス階層 | N | 情報源 |
| --- | ---: | --- |
| Gold | 65 | 15 実験 PDB 構造；49 RefSeq 注釈付き MCP；virion-proteomics support を持つ 1 分離ウイルス由来 GenBank MCP |
| Silver_R3 | 495 | 436 MetaVR タンパク質；18 GenBank 候補；41 文献由来候補 |

MetaVR および RefSeq/GenBank Silver candidates について、PPT は高いウイルス信頼度、HMM の裏付け
（`E < 0.1`、bit score `> 10`）、length `> 200 aa`、Gold clusters からの分離、PDB Golds との
構造類似性（`qTM ≥ 0.60`、`tTM ≥ 0.60`、`LDDT ≥ 0.50`）を記録しています。

陽性カタログには、次の門レベルの群が含まれます。

| 陽性分類群 | N |
| --- | ---: |
| Nucleocytoviricota | 415 |
| Preplasmiviricota | 117 |
| Produgelaviricota | 26 |
| Literature-only, unclassified | 2 |
| **合計** | **560** |

<details>
<summary>PPT に基づく目 / 末端分類群別サンプル一覧</summary>

| 門 | 綱 | 目 / 末端分類群 | Gold | Silver_R3 | 合計 |
| --- | --- | --- | ---: | ---: | ---: |
| Nucleocytoviricota | Megaviricetes | Algavirales | 25 | 161 | 186 |
| Nucleocytoviricota | Megaviricetes | Imitervirales | 9 | 122 | 131 |
| Nucleocytoviricota | Megaviricetes | Mamonoviridae† | 1 | 0 | 1 |
| Nucleocytoviricota | Megaviricetes | Pimascovirales | 7 | 55 | 62 |
| Nucleocytoviricota | Mriyaviricetes | Yaraviridae† | 1 | 18 | 19 |
| Nucleocytoviricota | Pokkesviricetes | Asfuvirales | 2 | 8 | 10 |
| Nucleocytoviricota | Pokkesviricetes | Chitovirales | 1 | 5 | 6 |
| Preplasmiviricota | Aquintoviricetes | Archintovirales | 2 | 6 | 8 |
| Preplasmiviricota | Pharingeaviricetes | Rowavirales | 1 | 2 | 3 |
| Preplasmiviricota | Polintoviricetes | Amphintovirales | 2 | 2 | 4 |
| Preplasmiviricota | Tectiliviricetes | Kalamavirales | 2 | 3 | 5 |
| Preplasmiviricota | Virophaviricetes | Divpevirales | 0 | 1 | 1 |
| Preplasmiviricota | Virophaviricetes | Lavidavirales | 3 | 5 | 8 |
| Preplasmiviricota | Virophaviricetes | Mividavirales | 1 | 5 | 6 |
| Preplasmiviricota | Virophaviricetes | Priklausovirales | 2 | 80 | 82 |
| Produgelaviricota | Ainoaviricetes | Lautamovirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Atroposvirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Belfryvirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Coyopavirales | 0 | 1 | 1 |
| Produgelaviricota | Belvinaviricetes | Vinavirales | 3 | 19 | 22 |
| Literature-only | Unclassified | *Abadenavirae*-like<sup>*</sup> | 0 | 2 | 2 |

† 目が割り当てられていない ICTV の末端科。アスタリスクは ICTV MSL41 の目ではなく、文献のみに
基づく作業クレードであることを示します。SHA-256 が同一のタンパク質はそれぞれ一度だけ数えています。
この表示では、PPT は四つの目をまたぐ別名を、カタログで指定された主要分類群に割り当てています。

</details>

[split summary](../data/processed/v0/split_summary.json)、
[dataset contract](../data/processed/v0/v0_dataset.json)、および
[source-file checksums](../data/processed/v0/source_files.tsv) は、同じ凍結済みデータセットの簡潔な
機械可読 provenance を提供します。

- 分割：Train/Validation/Test = **6,634 / 2,212 / 2,214**。分割前に exact-sequence、source、component、
  MMseqs2 の関係を統合しました。条件を満たす残存 cross-split edge = 0 です。
- 選択：14 representation models は共通の Train-only 五折 component map を使用しました。
  three-head Validation gates と paired one-SE rule の後、ESM-C 6B が選択されました（`S=0.997145`）。

| ヘッド | タスク | 分類器 | 温度 | 閾値 |
| --- | --- | ---: | ---: | ---: |
| H1 | DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | viral MCP-DJR / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

H2 は H1 がタンパク質を DJR と分類した後にのみ実行され、H3 は H2 がそれを viral MCP と分類した後に
のみ実行されます。

### Model V0.1 Candidate の選定とトレードオフ

九つの混合候補を事前登録し、既存の Train-CV 結果だけで順位付けしました。四情報源の堅牢性解析では
再順位付けしていません。選定された候補は H1/H2 に ESM-2 3B、H3 に ESM-C 6B を使用し
（`S=0.997645`）、all-6B に対する Holm 補正済み情報源警告は `0/4` です。これは四情報源での
非劣性または同等性を確立するものではありません。

| システム | ウイルス | 細胞 | 背景 | 対応 HardNeg | 常時実行 / 最悪時 GPU s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen all ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| Mixed nominee | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

四つの情報源列は完全な想定経路でのメンバー正解率であり、一つのプールスコアではありません。
候補が回収するウイルス strict clusters は 52/69 で、all-6B の 55/69 より少なく、H3 に到達する
配列には二つ目のエンコーダーが必要です。ステータスは引き続き
`recommended_for_external_confirmation` で、`released_v0_change_permitted=0` です。

### Ultra-remote 開発監査

Train のみの全コンポーネントホールドアウトでは、H1 encoder sensitivity は V0 と比較して V0.1 で
`+0.197` 異なります。BLAST で定義した `qcov<80%` stress stratum では `+0.260`（95% CI
0.206–0.317）です。H1 operational detector の差は `+0.017` にとどまり、H2 とエンドツーエンド MCP
cascade の差はゼロです。上記の特異度とサンプルサイズの制限により、正式なステータスは
`PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE` です。

### PLM と古典的検索手法の比較

このベンチマークでは、6,634 Train レコードに対して巡回式 3-fit/1-calibration/1-evaluation
component cross-fitting を使用します。値は、99.5% 特異度目標に較正された閾値での fold-macro
component AP / sensitivity です。

| 手法 | H1 | H2 |
| --- | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 |
| Component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 |
| ESM-2 650M cosine, contextual | 0.9515 / 0.8954 | 0.9965 / 0.9977 |

H1 では、ESM-C cosine と四つの古典的基準手法のペア差の信頼区間はすべて負です。H2 と H1→H2
endpoint では区間がゼロをまたぎ、singleton components における低 FPR 分解能の制約を受けます。
これは representation-retrieval comparison であり、公開済み supervised tool の外部性能では
ありません。validator は点推定値を再計算しましたが、10,000 bootstrap replicates のすべてを
独立には再実行していません。

## 正式なエビデンスの参照先

1. [Model V0.1 Candidate パッケージ](../user-inference-v0.1/) および
   [公開済み Model V0 パッケージ](../user-inference-v0/)。
2. [候補選定](../results/validation_family_robustness_v0_schema5_mixed_heads/candidate_nomination.tsv)
   および [Train-CV 候補要約](../results/validation_family_robustness_v0_schema5_mixed_heads/train_cv_candidate_summary.tsv)。
3. [V0 モデル選択の図と provenance](../results/figures/project_v0/model_benchmark_metric_revision_1/)。
4. [V0/V0.1 監査レポート](../benchmarks/ultra_remote_v0_v01/results/REPORT.md)、
   [全コンポーネント感度](../benchmarks/ultra_remote_v0_v01/results/stratum_sensitivity.tsv)、
   [equal-fold 手法要約](../benchmarks/ultra_remote_v0_v01/results/method_summary.tsv)、および
   [ペア比較](../benchmarks/ultra_remote_v0_v01/results/paired_v0_v01.tsv)。
5. [Schema 5 の簡潔な結果](../results/validation_family_robustness_v0_schema5_mixed_heads/)。
6. [PLM と古典的手法のベンチマーク](../benchmarks/plm_vs_classical_v0/)。
7. [簡潔な科学レポート](research/PROJECT_V0_FINAL_REPORT.md)。
8. [完全なワークフローとプロトコルの境界](research/WORKFLOW_V0.md)。
