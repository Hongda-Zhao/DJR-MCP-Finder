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
| **Model V0.1 Candidate** | H1/H2 に ESM-2 3B、H3 に ESM-C 6B | 実験的候補。独立した外部検証は未実施 | **探索的スクリーニングで現在優先する実験的候補モデル** |
| **Model V0** | H1/H2/H3 に ESM-C 6B | 公開済み・凍結済み | 再現可能なベースラインおよびサポート対象の代替モデル |

「優先する実験的候補」は、現在の探索的スクリーニング経路と Train-CV の結果を表します。
Model V0.1 Candidate が独立した外部検証を受けたことや、Model V0 を置き換えたことを
意味しません。Model V0 は非推奨のバージョンではなく、引き続き主要な科学的成果です。

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

## エビデンスの階層

| エビデンス | ステータス | 答えられること | 答えられないこと |
| --- | --- | --- | --- |
| 14-model V0 selection | 凍結済みの開発時選択 | どの単一エンコーダーシステムが Model V0 として選ばれたか | 外部データへの汎化 |
| 四情報源ファミリー頑健性解析 | 事前定義した20項目の確認をすべて通過 | 同じ四つの情報源に由来するファミリーメンバーにおける、八つのモデルと九つのカスケードの選択後整合性 | 独立 Test の性能、同等性、またはモデル選択へのフィードバック |
| PLM versus classical V0 | 内部クロスフィット確認に合格 | 宣言された情報量の制約下における Train コンポーネント間の検索性能差 | 外部データにおける優越性 |
| V0/V0.1 低類似性監査 | 内部確認に合格。記述的な解釈に限定 | 内部ホールドアウトと低カバレッジストレス層における記述的挙動 | 正式な `<20% identity` 結論 |
| 独立した外部検証 | **未実施** | — | Model V0 または Model V0.1 Candidate の公開品質の汎化性能 |

## これらの結果が確立していないこと

- Model V0 と Model V0.1 Candidate のいずれも、独立した外部検証を受けていません。
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
| Viral DJR-MCP | 560 | Gold 65 と Silver 495；陽性情報源の詳細は下記 |
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
| Silver | 495 | 436 MetaVR タンパク質；18 GenBank 候補；41 文献由来候補 |

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

| 門 | 綱 | 目 / 末端分類群 | Gold | Silver | 合計 |
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

公開されている [dataset contract](../configs/v0_dataset.json)、
[dataset checksum manifest](../data/processed/v0/CHECKSUMS.sha256)、および
[post-split audit checksums](../results/postsplit_integrity_v0/CHECKSUMS.sha256) は、同じ凍結済み
データセットと監査の簡潔な機械可読 provenance を提供します。

- 分割：Train/Validation/Test = **6,634 / 2,212 / 2,214**。分割前に exact-sequence、source、component、
  MMseqs2 の関係を統合しました。条件を満たす残存 cross-split edge = 0 です。
- 選択：14 representation models は共通の Train-only 五折 component map を使用しました。
  three-head Validation gates と paired one-SE rule の後、ESM-C 6B が選択されました（`S=0.997145`）。

| ヘッド | タスク | 分類器 | 温度 | 閾値 |
| --- | --- | ---: | ---: | ---: |
| H1 | DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | viral MCP-DJR / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

Model V0 は共有する一つの ESM-C 6B 埋め込みから全配列の H1 と H2 の生スコアを計算します。
H2 の結果は H1 陽性の場合だけ実際のカスケード判定に用い、H3 は H1/H2 の両方が陽性の
配列だけで計算します。

### Model V0.1 Candidate の選定とトレードオフ

九つのエンコーダー構成を、既存の Train-CV 結果だけで比較しました。四情報源の頑健性解析は
整合性の確認に使用し、再順位付けには使用していません。Model V0.1 Candidate は H1/H2 に
ESM-2 3B、H3 に ESM-C 6B を使用し（`S=0.997645`）、Model V0 に対する Holm 補正済みの
情報源警告はありません。これは四情報源での非劣性または同等性を確立するものではありません。

| システム | ウイルス | 細胞 | 背景 | 対応 HardNeg | 常時実行 / 最悪時 GPU s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Model V0（all ESM-C 6B） | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| Model V0.1 Candidate | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

四つの情報源列は完全な想定経路でのメンバー正解率であり、一つのプールスコアではありません。
Model V0.1 Candidate が回収するウイルスの厳密な配列クラスターは 52/69 で、Model V0 の
55/69 より少なく、H3 に到達する配列には二つ目のエンコーダーが必要です。探索的
スクリーニングで優先する実験的候補ですが、独立した外部検証は未実施であり、公開済み
Model V0 を置き換えるものではありません。

### Ultra-remote 開発監査

Train のみの全コンポーネントホールドアウトでは、H1 encoder sensitivity は V0 と比較して V0.1 で
`+0.197` 異なります。BLAST で定義した `qcov<80%` stress stratum では `+0.260`（95% CI
0.206–0.317）です。H1 operational detector の差は `+0.017` にとどまり、H2 とエンドツーエンド MCP
cascade の差はゼロです。少なくとも一つの評価 fold が目標特異度を満たさず、strict
ultra-remote stratum には独立した陽性コンポーネントが一つしかないため、これらの結果は
記述的な解釈に限られ、正式な ultra-remote の主張を支持しません。

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
2. [公開済み結果の案内](../results/README.ja.md)および
   [V0 図表コレクション](../results/figures/project_v0/README.md)。
3. [V0/V0.1 監査レポート](../benchmarks/ultra_remote_v0_v01/results/REPORT.md)、
   [全コンポーネント感度](../benchmarks/ultra_remote_v0_v01/results/stratum_sensitivity.tsv)、
   [ペア比較](../benchmarks/ultra_remote_v0_v01/results/paired_v0_v01.tsv)。
4. [PLM と古典的手法のベンチマーク](../benchmarks/plm_vs_classical_v0/)。
5. [簡潔な科学レポート](research/PROJECT_V0_FINAL_REPORT.md)。
6. [完全なワークフローとプロトコルの境界](research/WORKFLOW_V0.md)。
