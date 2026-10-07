# 系統樹に基づく除外と開発データでの再学習（2026-10-07）

[English](README.md) | [简体中文](README.cn.md) | **日本語**

完了済みの**探索的研究実験**です。モデルのリリースや、汚染除去が確認されたことを意味しません。参照系統樹の再点検、ユーザー指定の広い除外集合、ESM-C 6B と ESM-2 650M の開発データでの再学習を記録します。公開済みのエンコーダー、Head、閾値、ルーティング、バージョンは変更しません。

## 方法とデータ

先に 8 配列を除いた 550 葉の AA / 3Di 樹で、Class と Phylum ごとに非根付き内部辺の両側、単独の異分類葉、支持値、距離同順位を含む近傍を調べました。候補 22 配列は、優先監査 5、支持不足の重点監査 4、特別な解釈が必要な 3、弱い・文脈依存の信号 10 に分かれます。最優先は Imitervirales_C0475、Priklausovirales_C0052、C0082、Asfuvirales_C0011、Gold Chitovirales_C0003 です。

ユーザーの指定に従い、弱い信号や既知の実験構造参照も含め 22 配列すべてを剪定しました。累計 **30 葉を除外し、528 葉を保持**しています。FoldMason / IQ-TREE の再推定ではありません。支持値は元の 558 葉解析に由来し、経路統合で生じた辺では省略します。長枝の除去により midpoint の根位置は変わり得ます。

30 配列すべてを SHA で正式な 11060 行のモデル manifest に対応付けました。3 つの Head の開発データから **Train 16 行、Validation 7 行**を除外し、**Test 7 行は要監査として記録するだけで変更・評価しません**。新 manifest は 11037 行（Train 6618、Validation 2205、Test 2214）。VMA-DJR は 320 / 105 / 112、H3 既知クラスは 305 / 100 / 106 です。

元の正例 560 配列には、558 葉の樹に含まれない literature-only 配列が 2 本あり、保持しています。528 葉をすべて Train に投入するわけではありません。検証済みの固定 embedding の行部分集合を再利用し、6 つの分類 Head を学習し直しました。両モデルで共通の Train-only 成分別 5-fold を新しく固定し、温度と閾値を再校正しました。PLM 自体のファインチューニングではありません。

## 結果と解釈

| モデル | CV H1 AP | CV H2 AP | CV H3 macro-F1 |
| --- | ---: | ---: | ---: |
| ESM-C 6B | 0.997021 | 1.000000 | 0.994888 |
| ESM-2 650M | 0.996198 | 1.000000 | 0.912663 |

Validation の H1 AP は 0.992544 / 0.999746、H3 closed-set macro-F1 は 1.000000 / 0.986094 で、すべての Head で 6B が優れるわけではありません。既知クラス 100 配列のうち各モデルで 4 配列を拒否しました。unknown 診断はわずか 5 配列で、どちらも 4 配列を拒否しましたが、対象は異なります。

これは選択したハイパーパラメーターにおける**Head ごとの条件付き開発指標**であり、カスケード全体や Test の性能ではありません。同じ CV でハイパーパラメーターを選び、Validation で校正します。除外方針は Test 割当参照も含む全参照樹の観察後に決定したため、Test 行を保存しても前向きの未観測評価にはなりません。同一評価集合での元データ対除外データの対照実験はなく、汚染除去による汎化改善や正式モデル置換の根拠にはできません。同じ Class 内の既存 Order 問題は未解決です。

## 証拠と検証

- [22 候補](topology/review_candidates_22.tsv)、[優先 5 配列](topology/priority_audit_5.tsv)、[分類階級別の証拠](topology/candidate_rank_evidence.tsv)、[窓サイズ感度](topology/window_sensitivity.tsv)。
- [累計除外 30 配列](pruning/removed_tip_ids.txt)、[保持 528 配列](pruning/retained_tip_ids.txt)、[剪定 QA](pruning/pruning_QA.tsv)。
- [3Di 樹](pruning/figures/Three_Phylum_3DI_midpoint_rectangular_full_taxonomy_only.pdf)、[AA 樹](pruning/figures/Three_Phylum_AA_midpoint_rectangular_full_taxonomy_only.pdf)、[比較図](pruning/figures/Three_Phylum_AA_3Di_midpoint_comparison_taxonomy_only.pdf)。
- [学習対応表](retraining/exclusion_crosswalk_30.tsv)、[元 manifest の監査](retraining/source_manifest_audit.json)、[比較表](retraining/comparison.tsv)、[結果要約](retraining/RESULTS_SUMMARY.json)、[準備検証](retraining/PREPARED.json)。

リポジトリのルートで実行します。配列や checkpoint は不要です。

```bash
python scripts/validate_topology_exclusion_evidence.py
python -m pytest -q tests/test_topology_exclusion_evidence.py
```

## 完全な再現に必要なもの

`recorded_scripts/` は**実行時の施設固有スクリプトの記録**です。移植可能な既定コマンドや自動 CI ではありません。元の `outputs/` 構成と `/aptmp/hongda/` の履歴アーカイブを参照します。この Git 証拠パッケージだけでは配列、embedding、実行環境を置き換えられません。

樹解析には元の `Three_Phylum_RefOnly_FoldMason_IQTREE_20260924`、8 配列の除外監査、`Three_Phylum_pruned8_20261007` 入力を復元し、元の作業ルートで `topology/recheck.R`、`attachment.R`、`summarize.py` を順に実行します。R の ape、描画にはさらに phangorn、ggplot2、patchwork、注釈、配色、メタデータ、未整列 FAA が必要です。樹のハッシュと QA は manifest にあります。

再学習には**新規出力ディレクトリ**を使い、`ROOT`、`BASE`、`ARCHIVE` と PBS の実行・環境パスを一緒に移設してください。既存の完了ディレクトリに履歴 PBS をそのまま実行しないでください。準備スクリプトは元 manifest のハッシュ、30 配列の対応、元 FAA と両 embedding bundle を検証し、Test を保持して開発データとベクトルを抽出、コードと fold を保存します。各 `calibrate_benchmark_model.py` 実行後、finalizer が 6 モデルのハッシュと指標分母を確認します。バージョンとコードハッシュは `PREPARED.json` と calibration に記録しています。

実行ルート：`/aptmp/hongda/DJR-MCP-Finder/experiments/pruned30_dev_20261007`。PBS 5147398 / 5147399 / 5147400 は Exit 0、33 / 17 / 13 秒でした。rx1000 は利用可能でしたが、移行確認時には CPU ジョブが完了しており再実行していません。

生配列、embedding、checkpoint、環境、個別 Test 予測は**含めません**。モデルパスとコードハッシュはサーバー側成果物の来歴であり、軽量検証器で非同梱モデルのバイト列を再検証することはできません。`CHECKSUMS.sha256` はこの実験だけを対象とし、正式リリースのハッシュは変更しません。新 Head は固有の校正値とエンコーダー仕様を組み合わせて使用します。
