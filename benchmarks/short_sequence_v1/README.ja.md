# 短配列 benchmark v1

[English](README.md) | [简体中文](README.cn.md) | **日本語**

状態（2026-09-28）：保存済み embedding を再利用した入力長別の CPU 評価は完了しました。
対応のある切断実験は未完了です。ラベル付きタンパク質を使い、
DJR-MCP-Finder 自体の短断片への能力を測ります。応用先の予測候補を正解にしません。
V0.2 設計の基準は V0.1 Candidate、V0 は過去の対照です。

## 入力長別の結果（2026-09-28）

両 encoder で Train 6,634 配列すべてに一致し、計 13,268 ベクトルを再利用しました。
GPU encoding は実行していません。[指標表](results/observed_length_20260928/metrics.tsv)と
[図](results/observed_length_20260928/observed_length.pdf)を収録しています。

| 入力長 (aa) | MCP 数 | V0.1 方式 MCP 再現率 | 非 MCP 数 | V0.1 方式の偽陽性数 |
|---|---:|---:|---:|---:|
| <130 | 0 | NA | 0 | NA |
| 130–149 | 0 | NA | 1 | 0 |
| 150–199 | 0 | NA | 278 | 0 |
| 200–249 | 0 | NA | 280 | 0 |
| 250–299 | 13 | 13/13 (100%) | 482 | 0 |
| >=300 | 323 | 318/323 (98.45%) | 5,257 | 0 |

**250 aa 未満に MCP 陽性例がない**ため、その範囲の MCP 再現率や最短の利用可能長は
推定できません。13/13 の根拠は少数例であり、観測偽陽性ゼロも母集団の誤りゼロを
意味しません。V0 の集約 MCP 再現率は同じで、200–249 aa に偽陽性 1 件、>=300 aa に
2 件があります。内部 component cross-fit であり、配布分類頭の独立外部テストでは
ありません。補完する切断実験では新しい断片のみ GPU encoding を行います。


## 保存済み embedding の再利用：CPU による入力長別評価

`prepare --mode observed` は元の Train 配列だけを使用し、断片を生成しません。
空の長さ区間も NA として残し、再現率ゼロとは扱いません。区間ごとにタンパク質と
由来の構成が異なるため、同一タンパク質の切断効果を直接示す評価ではありません。

```bash
python3 benchmarks/short_sequence_v1/benchmark.py prepare --mode observed --out run/observed
python3 benchmarks/short_sequence_v1/benchmark.py reuse --run run/observed --encoder esm2_3b --source /path/to/v0_benchmark_esm2_3b --require-complete
python3 benchmarks/short_sequence_v1/benchmark.py reuse --run run/observed --encoder esmc_6b --source /path/to/v0_benchmark_esmc_6b --require-complete
python3 benchmarks/short_sequence_v1/benchmark.py score --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py summarize --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py validate --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py plot --run run/observed
```

NumPy、scikit-learn、PyYAML、Matplotlib を使い、Torch、モデル読み込み、GPU は
不要です。ファイル checksum、固定モデル revision、精度、pooling、window、token
処理、adapter 設定を検証し、配列 SHA-256 と長さで **Train 行だけ**を照合します。
元の ID が異なっていても再利用できます。履歴 bundle に他 split が含まれていても、
そのベクトルとラベルは学習・校正・評価に使用しません。元 cache は変更せず、既存の
出力 bundle も上書きしません。

既定の `--mode truncation` では、`--require-complete` を外して先に `reuse` を
実行し、その後 `embed` で不足配列だけを計算します。`reuse/*.json` と対応表に
source checksum と行の由来を保存します。スクリプト変更時は新しい run を準備します。
`plot` は `observed_length.png/.pdf/.svg`、切断評価ではさらに `length_curves` を出力します。


## 方法

固定した 6,634 Train レコードと既存の component 五分割を使い、manifest、FASTA、
fold map、encoder registry の SHA-256 を検証します。Validation/Test レコードは導入・評価しません。
混合 split の履歴 cache は整合性を検証して Train 行だけを選択します。各サイクルは全長の三 fold で学習、一 fold で校正、一 fold の全長
と断片で評価します。親と全断片は同じ component/fold に残します。

V0 の H1/H2 は ESM-C 6B、V0.1 Candidate は ESM-2 3B を使います。H3 は各 fold の
許可された既知二門の全長データで一度だけ学習し、両方式で共有します。これは
**fold ごとの再学習**であり、配布済み分類頭を自身の学習断片で試す方式ではありません。
結果は内部開発評価で、独立外部性能や配布モデルの更新を意味しません。

H1 は校正 MCC、H2 は真の DJR 校正データ上の macro-F1 を最大化する raw-score
閾値を選びます。同点は高い閾値を採用し、全件拒否も候補に含めます。長さごとの
再校正はしません。H3 は校正データの絶対二値 logit の下側 5% 分位点を使い、
既知クラスの少なくとも 95% 受容を目指します。絶対 logit と正の温度での信頼度は
順位が同じです。スコアを校正済み事後確率とは表示しません。

## 断片と指標

主要解析では >=300 aa の同一親集合から 50、100、130、150、200、250、300 aa の
断片と全長対照を作ります。陽性と陰性に同じ生成規則を適用します。各長さで N 末端、
C 末端、厳密に内部の位置を一つ一様抽出します。親・長さ別のハッシュ seed で
順序に依存しない再現性を保ちます。座標は 0 始まり、右端を含みません。
内部開始位置がなければ生成せず、300 aa の親から作る 300 aa 末端断片は全長と
同じです。評価ビューを残したまま、同一配列の embedding 計算を共通化します。

短い親は全長入力の記述的解析に残し、主要な対応あり比較から除外します。生成した
断片または全長入力が別 fold のクエリと完全一致した場合、影響する親を**全ての
対応あり条件**から除外し、理由を記録します。これは完全一致の検査であり、全ての
遠縁相同性の除去を保証しません。

断片ラベルは MCP 由来であることを示し、完全な DJR 構造や機能を保証しません。
50/100 aa は記録された学習長の範囲外です。全長入力は <100、100–129、130–149、
150–199、200–249、250–299、>=300 aa に別集計します。この短入力群も、実験的に
完全性が確認された天然短タンパク質とは限りません。

主要指標は H1 AND H2 の MCP 再現率と偽陽性率です。`mcp::unknown/other` も
MCP 検出に数えます。cellular DJR、難しい non-DJR、背景 non-DJR の偽陽性率も
分けて報告します。pooled FPR はこの由来構成での値で、応用時の偽発見率ではありません。

H1/H2 の診断と、H3 の門別エンドツーエンド再現率、ゲート通過後の正答・誤分類・
拒否率を別途示します。H2 診断は真の DJR 全件、条件付き H3 はゲートを通過した
MCP が分母です。エンドツーエンド指標では上流失敗を分母に残します。unknown 拒否は
少数例の診断であり、一般的 OOD 検出の証拠ではありません。

親内で断片の結果を平均し、次に親間で平均します。component 全体を再抽出する
2,000 回の bootstrap で 95% CI を計算し、断片・親・独立 component 数も表示します。
一 component の場合は CI を出さず、ゼロ誤りの退化した区間を母集団誤りゼロの証明に
しません。区間はモデル再学習や事前学習の不確実性を含みません。長さ−全長と
V0.1−V0 の対応差は共通の適格親集合で計算します。H3 条件付き分母はゲートに依存
するため、全体性能にはエンドツーエンド指標を優先します。

## 実行

GitHub は Train FASTA を配布していません。凍結データがある checkout で準備します。
gds2 の入力ハッシュは 2026-09-28 に一致を確認しました。Python 3.10+ が必要です。

```bash
cd /path/to/DJR-MCP-Finder
python3 benchmarks/short_sequence_v1/benchmark.py prepare \
  --project-root /path/to/DJR-MCP-Finder \
  --out benchmarks/short_sequence_v1/run/production_v1
```

空でない出力先は拒否します。プロトコルやコードの変更には新しい run を使います。
割り当て済み GPU 上で、ESM-C と ESM-2 の既存の互換 Python 環境を使います。
ESM-C は固定した専用 Transformers 実装が必要です。ログインノードでは実行しません。

```bash
"${ESMC_PYTHON:?Set ESM-C Python}" benchmarks/short_sequence_v1/benchmark.py embed \
  --run benchmarks/short_sequence_v1/run/production_v1 --encoder esmc_6b --device cuda
"${ESM2_PYTHON:?Set ESM-2 Python}" benchmarks/short_sequence_v1/benchmark.py embed \
  --run benchmarks/short_sequence_v1/run/production_v1 --encoder esm2_3b --device cuda
```

必要なら `--limit 2` で GPU smoke test を行い、その後制限なしで再開します。
未完了・破損・revision 不一致の embedding は評価できません。断片は再符号化し、
親の平均ベクトルを切り取って代用しません。

両 encoder が終わったら、既存 CPU 分類環境で実行します。

```bash
python benchmarks/short_sequence_v1/benchmark.py score --run benchmarks/short_sequence_v1/run/production_v1
python benchmarks/short_sequence_v1/benchmark.py summarize --run benchmarks/short_sequence_v1/run/production_v1
python benchmarks/short_sequence_v1/benchmark.py validate --run benchmarks/short_sequence_v1/run/production_v1
```

gds2 では `qsub benchmarks/short_sequence_v1/pbs/score_gds2.pbs` で CPU ジョブを
明示的に投入できます。`.[figure]` を入れた環境では `plot --run ...` が PNG/PDF を
作ります。自動描画はしません。入力と除外理由は `inputs/`、予測と閾値は `scores/`、
指標・対応差・報告は `results/` に保存します。run は Git 対象外です。
予測行の欠落はエラーにし、成功例だけを集計しません。

CPU テストは `python -m pytest -q tests/test_short_sequence_benchmark.py` です。
人工特徴のテストは GPU 実装や実タンパク質の精度を証明しません。
次の設計は [V0.2 提案](../../docs/research/MODEL_V02_DESIGN.ja.md) を参照してください。

## MCP 陽性配列の長さ統計

整理済み全データには MCP 陽性 560 配列（Train 336、Validation 112、Test 112）が
あります。[全 split の統計](results/mcp_positive_lengths_all_20260928/summary.tsv)と
[分布図](results/mcp_positive_lengths_all_20260928/mcp_positive_lengths.pdf)はメタデータの
記述のみで、保留集合のモデル評価ではありません。全陽性の範囲は 254–2,906 aa、
中央値は 473 aa です。250–299 aa は 22 配列、250 aa 未満はゼロです。Train のみの
benchmark の件数とは区別してください。

再現：`python3 benchmarks/short_sequence_v1/length_statistics.py --parents data/processed/v0/master_manifest.tsv --scope all --out benchmarks/short_sequence_v1/run/lengths_all`。

## 250–500+ aa を 50 aa ごとに再集計した benchmark

[再集計表](results/length_bins_250_500_20260928/confusion_by_length.tsv)と
[図](results/length_bins_250_500_20260928/visualization_en_v2/overview.en.pdf)は既存の Train
cross-fit 予測を再利用し、モデル・閾値・分割は変更しません。区間は左閉右開の
250–299、300–349、350–399、400–449、450–499、>=500 aa です。<250 aa も補助診断
として残します。V0.1 の検出数は順に 13/13、14/15、38/38、75/77、71/71、120/122。
非 MCP 6,298 件に観測偽陽性はありませんが、母集団の誤りゼロを意味しません。
最短の二群は陽性 13、15 例のみで、長さとファミリー構成が交絡するため、単調な
長さ効果や最適な閾値は確立できません。

<250 aa の MCP 予測はこの整理済みデータの陽性長範囲外です。その範囲の正確性と
スコア校正は未検証ですが、参考陽性がないことは全予測が偽である証明ではありません。
短い陰性 559 例で偽陽性ゼロでも、短い陽性の感度や実運用の適合率は推定できません。
推論の強制的な長さ除外は追加していません。

```bash
python3 benchmarks/short_sequence_v1/length_bins_report.py --run benchmarks/short_sequence_v1/run/observed_production_20260928 --out benchmarks/short_sequence_v1/run/length_bins_250_500_new
```

初回分析後の依頼に基づく記述的な再集計です。全体の長さ統計は陽性 560 例ですが、
ここでの性能評価は引き続き Train 陽性 336 例です。

### 英語図の更新

主図は再現率バーと検出数/陽性数、見逃し数、偽陽性数を行ごとに対応させています。
[V0 比較と信頼区間](results/length_bins_250_500_20260928/visualization_en_v2/comparison.en.pdf)と
[門分類の詳細](results/length_bins_250_500_20260928/visualization_en_v2/phylum_detail.en.pdf)は補足図です。
図中の文字はすべて英語で、元の指標表と予測は変更していません。
