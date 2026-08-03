<!-- i18n-mirror: non-authoritative translation; source=docs/research/VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_PROTOCOL.md -->
> この翻訳は閲覧専用です。凍結された英語原文を正本とします。

# Project V0 八モデル／混合ヘッド Validation-family ロバストネスプロトコル

ステータス：schema 5、凍結済み解析計画、補助的な開発エビデンス。本プロトコルは
schema 4 を置き換えず、リリース済み V0 モデルを変更せず、独立した Test 評価を
構成するものでもない。

解析 ID：`project_v0_validation_family_robustness_schema5_mixed_heads`。

## 0. スコアリング前修正 A

ラベルを使用しない埋め込みの実体化が開始された後、ただし schema-5 の予測、
エンドポイント、bootstrap 結果、モデル比較のいずれも存在する前に、独立した契約
監査を完了した。修正 A は、マッチドファミリーにおける rare-H3 の分母（8 件の
メンバー関係／3 親。代表レベルベンチマークの 5 レコードとは異なる）を訂正し、
六件の明示的な再利用証明を要求し、再開レシートの検証を強化し、schema-4 継続性
バリデーター／結果マニフェストをチェックサムで拘束する。八モデル、九混合候補、
入力バイト、凍結済みヘッド／閾値、CV 指名規則、bootstrap シード、Test=0 境界は
変更されていない。元の実体化プロトコル／設定スナップショット（SHA256
`81aedf...881b6f` および `441990...adb94`）は引き続きアーカイブされる。修正後の
スコアリングでは、数値契約が変わっていない表現を再計算せず、その埋め込み出力を
再証明する。

## 0b. 障害後の運用修正 B

最初の CPU スコアリング試行は schema-4 継続性ゲートで fail-closed により停止し、
安定した結果ディレクトリ、エンドポイント、bootstrap 結果、検証レポート、図、
候補解釈のいずれも作成されなかった。続いて別の読み取り専用診断が、schema-4 の
全 92,844 予測キーを新規の schema-5 推論と比較した。source、cluster、
dependence-block、Train-relationship、eligibility、Test、truth、label、prediction、
reject decision、correctness の各フィールドは同一であり、Test は引き続きゼロ、
凍結済み閾値はすべて厳密にシリアライズされていた。当時、非厳密一致の値は異なる
BLAS バッチ形状に起因するとされた。メンバー確率は 114 行（最大絶対差
`3.353e-7`）、代表確率は 684 行（`2.305e-7`）、メンバー生スコアは 112 行
（最大絶対値 `0.03125`）、代表生スコアは 684 行（最大絶対値 `0.0234375`）
であった。報告された生の相対値 `4.795e-7`/`3.590e-7` は最大*絶対*差の行に
属するものであり、全体の最大相対値ではなかった。以下の修正 C は、この原因帰属と
誤ってラベル付けされた極値の両方に優先する。本段落は、すでに凍結された修正 B の
上限について、当時の根拠としてのみ残す。

したがって修正 B は、正式な schema-5 結果が存在する前に数値互換性ポリシーを
凍結する。全 92,844 行について新規推論を完了し、各行で次を満たさなければならない。

```text
probability:       abs(new-old) <= 5e-7 + 1e-6 * abs(old)
raw decision score: abs(new-old) <= 1e-5 + 1e-6 * abs(old)
threshold:         exact serialized equality
```

モデル固有またはデータ適応的な上限拡大は認めない。全行の値と差分は、チェックサム
で拘束された監査表に保持する。独立バリデーターは不等式を再計算し、それらの値から
二値判定、H3 reject 状態、正誤を導出する。すべてのキー、セマンティックフィールド、
空欄パターン、有限性／範囲チェック、厳密な閾値、導出判定が合格した後に限り、置換を
all-or-none で実行する。すなわち ESM-2 650M と ESM-C 6B の、チェックサムで拘束
された schema-4 シリアライズ済み行そのものを schema 5 の正規予測キャッシュとし、
その正規行から混合ヘッドを合成する。これにより、埋め込み、ヘッド、閾値、
エンドポイント、候補順位、リリース済み V0 成果物のいずれも変更することなく、
プラットフォーム依存の最下位ビットのずれを除去する。

## 0c. 旧来の数値演算子訂正修正 C

修正 B の科学的境界は fail-closed であったが、その数値診断は不完全だった。
Schema-4 ジョブ `4968695` は四つの BLAS スレッドを使用した。このジョブは後続ステップ
で全体終了ステータス 1 となっており、成功したジョブと記述してはならない。ただし、
予測生成と独立予測検証はすでに完了しており、チェックサムで拘束された
`predictions.tsv` のバイト列は引き続き正規の継続性成果物である。最初の schema-5
試行 `4968800` は 12 スレッドを使用し、厳密継続性チェックにおいてメトリクス生成前
に停止した。同じく 12 スレッドを用いた診断 `4968804` は、最大絶対差を持つ行に
相対差を付しており、最大の行単位相対差を計算せず、修正 B の式を全行に適用しても
いなかった。その結果、この集計は全体的な上限と誤解された。HardNeg のフルバッチ
構成は、過去の実行と診断実行の間で変わっていなかった。再現された原因は、バッチ
形状の変更ではなく、四スレッドから十二スレッドへの変更による OpenBLAS の縮約
計画の変化だった。

エラー発見時点で、安定した schema-5 結果、エンドポイント、bootstrap、検証、図、
候補解釈はいずれも存在しなかった。ジョブ `4968816` は修正 B の生スコアゲートで、
再びメトリクス生成前に停止した。訂正済みの全行 12 スレッド診断 `4968818` は、
メンバー生スコア 2 件、代表生スコア 9 件の違反を示した一方、確率と閾値の失敗件数
はゼロだった。独立に使用されたトップレベル最大相対値スカラーは、メンバー確率
`5.836859e-6`、メンバー生スコア `5.253913e-6`、代表確率 `6.363661e-6`、
代表生スコア `1.201539e-6` であり、閾値は厳密一致した。診断の詳細な
`max_relative_delta_record.ratio` ペイロードには表示上の不具合があった
（ヘルパーが `limit=1.0` を使用したため、このフィールドには絶対差が格納された）。
修正 C ではこのレコードフィールドを再利用しない。正式なスコアラーとバリデーターが
行単位の差分と上限をそれぞれ独立に再計算する。これは新たなドリフトではなかった。
そこで、結果生成前のリプレイ仮説を過去の数値演算子で検証した。読み取り専用の cdb
ジョブ `4968820` は終了ステータス 0 で完了し、Python 3.11.7、要求 CPU 数 四、
`OMP_NUM_THREADS=4`、`MKL_NUM_THREADS=4`、`OPENBLAS_NUM_THREADS=4`、
`PYTHONHASHSEED=20260724` の下で全 92,844 キーを比較した。Test 件数はゼロであり、
五つの数値フィールドすべてで `nonexact=0`、修正 B の失敗数は `=0` だった。ジョブ
`4968820` は厳密数値／有限性／Test の診断専用であり、すべてのセマンティック
フィールドの監査や、prediction、reject、correctness 値の独立再導出は行っていない。
したがって、正式な完全監査とは記述しない。

よって修正 C は、許容誤差ではなくランタイム演算子を訂正する。修正 B の確率／
生スコア上限と厳密閾値規則は凍結されたままであり、引き続き再計算する。schema-5
ではさらに、正規の ESM-2-650M/ESM-C-6B 全 92,844 行について、シリアライズされた
数値の厳密リプレイを要求する。スコアラーは推論前に、四スレッドのランタイムと
ロード済み BLAS スレッドプールを証明しなければならない。すべてのプールを観測可能
にするため、まず宣言済みの凍結数値モジュール `scipy.linalg` と
`sklearn.linear_model` のみを import する。この操作は fit、score、prediction の
いずれも実行しない。その後、推論前に二つの BLAS プールと一つの OpenMP プールが
すべて四スレッドであることを証明する。すべての正規値／再計算値、差分、
セマンティックフィールド、空欄パターン、有限性／範囲チェック、Test フラグ、導出
prediction／reject decision、correctness 値は引き続きチェックサムで拘束される。
修正 B の範囲内に収まる場合でも、非厳密一致の数値文字列はすべて失敗となる。完全な
厳密監査に合格した後に限り、正規行を all-or-none で置換し、混合ヘッドの再合成に
使用できる。

正式スコアラーは、エンドポイント、bootstrap、指名表のいずれかを計算する前に、
キー、セマンティクス、空欄、有限性／範囲、導出判定、Test、厳密文字列、保持された
上限について完全なゲート処理を行う。その後、独立バリデーターがチェックサムで拘束
された行単位監査とランタイム証明からこれらのチェックを再構築する。したがって、
数値のみの `4968820` エビデンスは演算子訂正の根拠となるが、それ自体では schema-5
結果を承認できない。

これは運用上のリプレイ訂正にすぎない。埋め込み、fit 済みヘッド、temperature、
閾値、Test ポリシー、bootstrap シード、CV スコア、候補グリッド、ロバストネス
エンドポイント、リリース済み V0 成果物は変更されていない。ジョブ `4968695` 全体
が合格したとは主張しない。使用するのは、すでに検証済みの予測成果物と、現在では
独立にリプレイされた数値演算子のみである。

## 0d. 結果生成後の H3 表示契約修正 D

修正 C の正式生成物は `schema5_v1` に変更なく保持する。その H3 表示をレビューした
ところ、二次的な pooled reject エンドポイント（`8` 件のメンバー関係／`3` 件の
Validation 親）が、凍結済みの二つの生物学的サブグループを個別表示していないことが
判明した。修正 D は報告契約の修復であり、新たなモデル解析ではない。上書き不可の
新規生成物を `schema5_v1_amendment_d` 以下に書き込む。

スコアラーは、すでに計算済みのレコード単位 H3 予測を、推論に使用したものと同じ、
チェックサムで拘束されたファミリーマニフェストに join する。凍結 SHA256 は
`8cd9e9ce45ad965eb745cc4ecdf08d7e3205f57b830bca00bcf0041e5bcdf541`
であり、スコアラーと独立バリデーターは `head3_status` または
`head3_phylum_label` を使用する前に、その identity の厳密一致を要求する。厳密に
次を導出する。

- `Produgelaviricota_reject_recall`：`7` 関係／`2` 親／`2` dependence block。
  block→parent→member を均等加重する。
- `literature_unclassified_reject_recall`：`1` 関係／`1` 親／`1` dependence block。
  点推定のみで、一般化を主張しない記述的結果であることを明示する。
- `rare_or_unclassified_reject_recall`：既存の `8` / `3` pooled 値。二次的な診断
  としてのみ保持する。

各 reject 行では、加重値に加え、生のメンバー `k/n` と生の一意な親 `k/n` を
報告する。独立バリデーターは凍結マニフェスト自体を読み、`7+1` join を再構築し、
support、生カウント、加重エンドポイント、推定可能な区間を再計算し、システムごとに
正確に六行の H3 エンドポイントセットを要求する。継続性のため、
Produgelaviricota は schema-4 シードオフセット `6100`、literature-unclassified
は `6110`、既存の pooled エンドポイントは引き続き `6100` を使用する。
エンドポイント間の共同比較は行わない。

サブグループ推論は実行しない。埋め込み、fit 済みヘッド、確率、予測ラベル、
temperature、閾値、Train-CV fold と値、候補順位、モデルコストエビデンス、
四-source エンドポイント、Test=0、リリース済み V0 成果物は変更されない。これを
機械的に検証可能にするため、修正 D のスコアラーとバリデーターは、単一モデル予測、
合成システム予測、expected-path 予測、システムレジストリ、Train-CV 候補表、
Pareto 表、指名表について、保持された修正 C 生成物とのバイト同一性を要求する。
いずれかの差異は公開前に fail-closed となる。保持された親 identity は、
`results/CHECKSUMS.sha256 = aa9f3cef647487d4eaec7749ceeb49c58085657a38d0d99c7577f3655448e72c`
および
`validation.json = 2b63cecae7788cce3d4c8ef96d48bf1becfbe8d74b9e9c084b2ab69a47542bcb`
として凍結されており、成果物レベルの比較前に両方を検証する。

バイト同一性の記述は、意図的に宣言済みの七成果物のみに限定する。四-source の
サマリー、bootstrap、paired diagnostics、model-cost 行は、既存バリデーターが
独立に再計算するか、同じ凍結済み予測／比較入力に再拘束する。修正 D は、これらの
派生表について別途ファイル全体のバイト同一性を主張しない。

## 1. 問いとエビデンス境界

本解析は、正式な 14 モデルベンチマークのゲートをすでに通過した八表現モデルが、
同一の四つの source-specific Validation-family コホートで一貫した挙動を示すか、
また、事前宣言された二エンコーダーカスケードが後の外部確認に向けた妥当な候補で
あるかを問う。

すべての表現チェックポイント、Train のみで fit したヘッド、temperature、
decision threshold、H3 reject threshold、適法なコホート除外、dependence block
は凍結されたままである。Schema-5 出力を fitting、calibration、threshold tuning、
リリース済み V0 ツール、Test にフィードバックしてはならない。混合カスケードには
`recommended_for_external_confirmation` とのみ記載でき、独立検証済みまたは
本番環境で優れていると記載してはならない。

恒久カウンター：

```text
training_operations=0
calibration_fit_operations=0
threshold_tuning_operations=0
Test vectors selected for inference=0
Test predictions or performance metrics computed=0
released_V0_artifacts_modified=0
```

## 2. なぜこの八モデルなのか

モデルセットは schema-5 推論前に、既存のチェックサムで拘束された 14 モデル
ベンチマークから固定された。

`esm2_650m`、`esm2_3b`、`esmc_300m`、`esmc_600m`、`esmc_6b`、`prott5_xl`、
`prostt5`、`esm3_open_1_4b`。

他の六ベンチマークモデルは 14 モデル開発図に引き続き表示されるが、事前宣言した
primary-candidate 境界を通過しなかったため、この高コストなロバストネス拡張には
含めない。Schema-5 結果に基づいてモデルを遡及的に追加または除外してはならない。

## 3. 八モデルすべてで同一の四-source 入力

各モデルはバイト同一のマニフェストと FASTA 入力を受け取る。

| shard | 生の埋め込みレコード | 適法なスコア対象レコード | 役割 |
| --- | ---: | ---: | --- |
| viral family | 13,074 | H1/H2 13,054; H3 13,052 | マッチしたウイルス感度と経路 |
| graph family: cellular | 391 | 391 | マッチした cellular H1/H2 経路 |
| graph family: background | 3,000 | 3,000 | マッチした H1 specificity |
| matched HardNeg | 3,478 | 3,478 | マッチした H1 specificity |

13,074 件の viral 行は、過去の生の埋め込み入力である。凍結済みの完全性ロジックは、
H1/H2 スコアリングから split をまたぐ完全同一配列の競合 20 件を除外し、H3 からは
継承 phylum の競合をさらに二件除外する。全モデルに同じ除外を適用する。一意配列を
一回だけ埋め込んでも、関連する member-parent 行が独立になるわけではない。推論は
適法な関係に展開して戻し、不確実性は凍結済み dependence block 単位で再標本化する。

入力 identity：

| shard | manifest SHA256 | FASTA SHA256 |
| --- | --- | --- |
| viral family | `d96ab256de26414706c9d4993f1d9e2d64adaea8cece32645bb16a2b18b7e6f3` | `9650b5703ce413ca438c9cb84740aa8bd4e14be6a1f183027419fdc9fefe6b7d` |
| graph family | `25f0ceaed999cc62ee933d6258c88bfcbad4ff4596900099ae0e8a046b10d33b` | `1e7478a7eedaee0d14952018797d18637cf1c316a6d0781dc179a32cfc50bee0` |
| matched HardNeg | `ec55863a86014952d107e870bffe428adcf5ea4f6fb800520fc4e957479b41c4` | `f274b6ac9ea5df52f6dcbe4428e22454649aecd93131f0eee7826087d6eaaf66` |

## 4. 同種候補と混合候補

最初に、source が当該ヘッドをサポートする場合、八モデルそれぞれが H1、H2、H3 を
供給する。これらの同種実行は表現固有の失敗を診断するためのものであり、単一の
四-source スコアに平均しない。

primary mixed-head search は、事前宣言された九カスケードに限定する。

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

H2 はすでに飽和しており、三番目の常時オンのエンコーダーには運用上の合理性がない
ため、H1 と H2 は一つのエンコーダーを共有しなければならない。異なる H3
エンコーダーは、H1→H2 経路が viral VMA-DJR に到達した後に限り呼び出す。残りの
`8^3` 組合せからデータ依存で追加することは primary result では認めない。

## 5. エンドポイント

source ごとに個別に報告する。

- viral：H1 sensitivity、H2 conditional sensitivity、H1→H2 path recall、
  H3 known 二-phylum macro-F1、二つの known-phylum F1 値、Produgelaviricota
  reject recall、literature-unclassified reject recall、および二次的な小標本診断
  としてのみ用いる pooled reject recall。
- cellular：H1 sensitivity、H2 specificity、H1→H2 non-MCP path-correct recall。
- background と matched HardNeg：H1 specificity/FPR のみ。
- 適用可能な各 source：member-level rate および `all legal members correct`
  source-cluster fraction。

H3 `unknown` は reject の挙動であり、普遍的な未知ウイルス検出ではない。正式な
代表レベルベンチマークには rare Validation レコードが五件ある。matched-family
robustness shard には、三件の Validation 親に由来する適法な rare member relation
が八件（Produgelaviricota 7 と literature-unclassified 1）含まれる。二つの
サブグループの分母と、生の member/parent `k/n` は個別に表示しなければならない。
literature-unclassified の一レコードは記述目的のみであり、一般化を支持できない。
`8/3` pooled 値は二次的である。これらの reject エンドポイントはいずれも
known-phylum macro-F1 に含めない。background または HardNeg における H2/H3 は
ゼロではなく `N/A` とする。

## 6. 不確実性と比較

シード `20260728` で、決定論的な nested bootstrap を 10,000 反復実行する。外側
単位は凍結済みの shared-SHA/original-component dependence block とし、メンバーは
source cluster 内にネストされたままとする。モデルおよび混合カスケードの差分には
同じ bootstrap draw を使用する。九十五パーセントのパーセンタイル区間を報告する。自明でない八件
の primary mixed candidate は、凍結済み all-ESM-C-6B cascade と family-wise Holm
補正で比較する。九番目の候補は all-6B 自己参照で、差分はゼロであり仮説検定ではない。
cellular/background/HardNeg の強みに関して、all-ESM-2-650M に対する文脈的な paired
delta も報告するが、候補の再順位付けには使用できない。未調整の探索的主張は禁止する。
凍結済み equal-block→cluster→member 推定と、厳密な all-members-correct cluster
fraction は、異なる問いに答えるため、両方を示さなければならない。

## 7. 候補指名規則

ロバストネスを最適化しない。候補順位はまず、既存の Train-only 五-fold 値から決める。

`S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 known macro-F1`。

混合候補では、H1/H2 fold 値は共有 base model から、H3 は同一の凍結 fold 上の H3
モデルから得る。平均 `S` が最高のものを accuracy-first nominee とする。候補が
その最大値から paired fold standard error 一個以内にある場合は Pareto set を報告し、
次の順で優先する。常時オンの base-encoder GPU seconds per sequence が小さいもの、
worst-case 二-encoder GPU seconds が小さいもの、peak GPU memory が小さいもの、最後に
凍結済み lexical candidate ID。

Schema-5 ロバストネスによって、この Train-CV 指名を並べ替えてはならない。Holm
補正済み paired interval が all-ESM-C-6B に対する劣化を確立した場合、source-specific
warning を付す。この警告は nominee に必ず添え、source-component-disjoint または
prospective external set で確認されるまで、production replacement を阻止する。

コストは、常時オンの H1/H2 エンコーダーと条件付き H3 エンコーダーの二項、および
worst-case sum として報告する。想定した route prevalence を明記せずに、prevalence
依存の単一ランタイムを主張しない。

## 8. 完了条件と fail-closed 規則

完了には、チェックサムが有効な埋め込み bundle 24 件（八モデル×三 shard）、新規
実体化レシート 18 件、および既存 650M/6B bundle に対する schema-5 再利用証明 六件
が必要で、すべて Test 件数ゼロでなければならない。さらに、凍結済み head／
temperature／threshold hash の厳密一致、八件の同種結果表と九件の primary mixed
結果表の完備、独立に再計算されたエンドポイント、`status=PASS` のバリデーター
レポートを要する。18 件の生 workstation レシートは、元の `/lab/...` path と byte
を保持する。別の 24 行の正規化証明レイヤーが、各 source receipt SHA をバイト同一の
gds2 bundle とその `/aptmp/...` registry path に拘束する。生レシートは決して
書き換えない。欠落、不一致、不完全、非有限のエビデンスは失敗した生成物として保持し、
暗黙に置換しない。schema 5 の報告内容にかかわらず、Schema 4 は変更しない。

二つの schema-4 モデルについては、修正 C のランタイム証明と 92,844 行の再計算監査、
五つの数値フィールドすべての厳密なシリアライズ一致、同種表と混合ヘッド表の双方で正規の
schema-4 `predictions.tsv` 行がチェックサム継続性を厳密に保つこと、ならびに厳密
リプレイ、保持された修正 B 上限、all-or-none canonicalization を確認する独立検証
ゲートも完了条件となる。監査行の欠落、または非厳密一致の数値文字列、上限外、
セマンティック、空欄、範囲、閾値、導出判定、ランタイム lineage、Test のいずれかの
不一致は fail-closed となる。

修正 D の完了には、正確に 102 H3 行（17 system label ごとに六 endpoint）が必要で、
うち 34 subgroup 行、厳密な `7/2/2` と `1/1/1` support、生の member と unique-parent
reject `k/n`、point-only の literature-unclassified 行、独立した manifest-join
再構築、宣言された修正 C の prediction/threshold/CV/order 成果物七件すべてとの
バイト同一性も要する。保持された修正 C 生成物を上書きしたり、その場で移行したり
することはない。

cdb launcher は下記の固定順序で実行し、安定した result または validation target の
上書きを拒否する。

```text
6 checksum-only reuse attestations (if absent)
18 raw + 6 reuse -> 24 normalized path attestations (if absent)
schema-5 scorer -> atomic results/
independent recomputation -> atomic validation.json
```

GPU 表現の実体化は workstation 上ですでに完了している。スコアリング／検証段階は
CPU のみを使用し、APG を使用してはならない。
