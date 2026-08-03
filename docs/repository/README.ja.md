[English](../../README.md) | [简体中文](README.cn.md) | **日本語**

[![CI](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Hongda-Zhao/DJR-MCP-Finder?display_name=tag&sort=semver&label=release&color=2ea44f)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

# DJR-MCP Finder

**タンパク質 FASTA から double-jelly-roll major capsid protein（DJR-MCP）候補をスクリーニングし、本プロジェクトが対応するウイルス門に属するかを判定します。**

DJR-MCP は *Varidnaviria* を特徴づけるカプシドタンパク質です。明瞭な配列類似性が弱くなった後も double-jelly-roll 構造のシグナルが残る場合があるため、多様な DNA ウイルスの発見と分類に有用な指標となります。

| 入力 | 出力 | 対象ユーザー |
| --- | --- | --- |
| アミノ酸 FASTA | タンパク質ごとの DJR/MCP スコアと最終ラベル | ウイルスタンパク質、または contig から予測されたタンパク質をスクリーニングするウイルス学・バイオインフォマティクス研究者 |

> **新規スクリーニングには Model V0.1 Candidate を推奨します。Model V0 は公開済み・凍結済みの正式ベースラインとして維持されます。** V0.1 には独立した外部検証がなお必要であり、V0 も本プロジェクトの主要な研究成果です。

## 予測フロー

![DJR-MCP Finder の予測フロー](../assets/readme/readme_workflow.svg)

H2 は H1 を通過した配列に対してのみ実行され、H3 はさらに H2 を通過した配列に対してのみ実行されます。すべてのスコア、gate 状態、最終ラベルは `predictions.tsv` に記録されます。これらのラベルはスクリーニング用であり、構造確認を意味するものではありません。

## クイックスタート

推奨環境は Linux、Docker、NVIDIA Container Toolkit、および CUDA GPU です。24 GB 以上の GPU メモリと BF16 対応を推奨します。

```bash
git clone https://github.com/Hongda-Zhao/DJR-MCP-Finder.git
cd DJR-MCP-Finder/user-inference-v0
bash workstation/build.sh

cd ../user-inference-v0.1
DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh

bash workstation/run_user_fasta.sh \
  /absolute/path/to/proteins.faa \
  run_output/my_sample \
  0
```

V0.1 は V0 の凍結済みイメージをベースとして使用するため、fresh clone では最初に V0 をビルドする必要があります。上記の空値は、ローカルで再構築すると必ず変化する過去の Docker image ID の確認だけを省略します。バージョン、環境、チェックサムの確認は引き続き実行されます。予測処理の本体は Python で実装されており、Docker は H1/H2 と H3 が必要とする二つの固定実行環境を分離するために使用されます。

通常の FASTA 予測に PBS、`qsub`、HPC scheduler は不要です。

初回の予測時には、固定バージョンのモデル checkpoint がダウンロードされます。結果は次の場所に保存されます。

```text
run_output/my_sample/
├── predictions.tsv
├── run_metadata.json
└── CHECKSUMS.sha256
```

最終ラベルは `non_djr`、`djr_non_mcp`、`mcp::Nucleocytoviricota`、`mcp::Preplasmiviricota`、または `mcp::unknown/other` です。`mcp::unknown/other` は、配列が H1/H2 を通過したものの、H3 が対応する二つのウイルス門のいずれにも確実に分類できなかったことだけを示します。これは汎用的な未知ウイルス検出器ではありません。

## 主要な開発性能と Benchmark

開発時のエビデンスを「データ構成 → 評価設計 → V0 モデル選択 → V0/V0.1 比較」の順に示します。

### 開発データ

![開発データの構成と component-safe な固定分割](../assets/readme/readme_development_data.svg)

四つのエビデンスグループには、合計 11,060 件の exact-sequence-unique representatives が含まれます。固定分割は Train 6,634 件、Validation 2,212 件、Test 2,214 件です。Validation/Test は開発データ内の固定パーティションです。以下のモデル選択では Train のみを使用しており、新たな prospective external Test には該当しません。

### 共通の五折設計

![共通の component-safe 5-fold Train CV](../assets/readme/readme_shared_train_cv.svg)

14 種の encoder と、その後の V0.1 混合候補は、すべて同一の component-safe fold mapping を使用しています。各 component は一度だけ評価用に留保され、最終結果は五折平均 ± SE として報告されます。

### V0 の 14-model Benchmark

![候補 encoder 14 種による V0 モデル選択 Benchmark](../assets/readme/readme_v0_model_selection.svg)

全 encoder の比較から ESM-C 6B が Model V0 として選択されました。2 位の ESM-2 3B は、その後 V0.1 の H1/H2 に使用され、H3 には引き続き V0 の ESM-C 6B が使用されます。したがって、V0.1 は混合 encoder candidate であり、この図における 15 番目の単一 encoder モデルではありません。

### V0 と V0.1：何が変わったか

Model V0 は、一度の ESM-C 6B embedding から H1、H2、H3 を実行します。Model V0.1 Candidate は混合 encoder cascade です。ESM-2 3B と、それ専用に凍結された H1/H2 heads、temperatures、thresholds が DJR/MCP スクリーニングを担当します。二段階の gate を通過した配列に対してのみ ESM-C 6B を実行し、V0 と完全に同一の H3 phylum/reject head を使用します。

![Model V0 と Model V0.1 のアーキテクチャおよび凍結 component の比較](../assets/readme/readme_v0_v01_architecture.svg)

| 比較項目 | Model V0 | Model V0.1 Candidate |
| --- | --- | --- |
| プロジェクト上の位置づけ | 公開済み・凍結済みの正式ベースライン | 新規スクリーニングに推奨する開発候補。外部検証がなお必要 |
| H1/H2 | ESM-C 6B representation、heads、calibration | ESM-2 3B representation、および対応する新しい凍結済み heads と calibration |
| H3 | ESM-C 6B phylum/reject head | V0 とバイト単位で同一の H3 artifact と calibration |
| 実行方式 | 単一 encoder。最終ラベルは H1→H2→H3 の順に決定 | H2 は H1-positive の場合のみ実行。H3 は第二の encoder を使って条件付きで実行 |
| 出力の由来情報 | `predictions.tsv` は 20 フィールド | 23 フィールド。三つの head encoder フィールドを追加 |

図中の gate 値は、各バージョンで個別に凍結された calibration threshold であり、性能スコアではありません。threshold の大小だけから、どちらのモデルが強い、または厳格であるかを判断することはできません。両バージョンは同一の三段階の決定規則と五種類の最終ラベルを維持していますが、V0.1 では実行経路と provenance がより明確になっています。

#### 平均性能

![Model V0 と Model V0.1 Candidate の Train-only 開発 Benchmark](../assets/readme/readme_train_cv_performance.svg)

図は五折平均 ± SE を示し、横軸の表示範囲は 0.968–1.000 です。V0.1 で置き換えられたのは H1/H2 stack 全体です。H2 AP は偶然同一であり、H3 は同じ artifact を再利用するため完全に同一です。

| Train-only 五折 CV ↑ | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: |
| H1 AP | `0.9985 ± 0.0003` | **`0.9993 ± 0.0004`** |
| H2 AP | `1.0000 ± 0.0000` | `1.0000 ± 0.0000` |
| H3 known-phylum macro-F1 | `0.9806 ± 0.0095` | `0.9806 ± 0.0095` |
| 総合スコア `S` | `0.9971 ± 0.0009` | **`0.9976 ± 0.0010`** |

`S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 macro-F1` です。V0.1 の H1 AP は平均 `0.000833` 向上しました。H2/H3 は変化しないため、総合スコアの平均差 `+0.000500` は正確に `0.60 × ΔH1` に由来します。太字は candidate nomination を示すものであり、統計的有意性を示すものではありません。

#### 五折それぞれの変化

![Model V0 と Model V0.1 Candidate の H1 AP および総合 S の fold 別ペア比較](../assets/readme/readme_v0_v01_fold_detail.svg)

V0.1 は五折のうち四折で向上し、一折で低下しました。`S` の paired-fold 平均差は `+0.000500`、paired SE は `0.000349` です。この図は、共通の Train-CV における記述的な候補選択エビデンスにすぎません。統計的有意性の検定でも、新たな prospective external Test でもありません。

## 出力例

`predictions.tsv` には、入力タンパク質ごとのスコア、cascade 状態、最終ラベルが記録されます。以下はフィールド形式の例です。

| protein_id | head1_djr_probability | head2_mcp_probability | head3_prediction | final_prediction |
| --- | ---: | ---: | --- | --- |
| candidate_001 | 0.997 | 0.981 | Nucleocytoviricota | `mcp::Nucleocytoviricota` |
| cellular_djr_002 | 0.994 | 0.082 | not_reached | `djr_non_mcp` |
| background_003 | 0.006 | NA | not_reached | `non_djr` |

## 結果の適用範囲

- 出力は後続検証のためのスクリーニング候補であり、構造確認ではありません。
- V0.1 の推奨は Train-only の開発時 CV に基づき、独立した外部テストによる確認はまだ行われていません。
- スコアは自然試料における prevalence-adjusted probability ではありません。大規模スクリーニングには、独立した偽陽性評価と、構造または人手による確認が必要です。

## リポジトリ内ディレクトリの役割

| ディレクトリ | 役割 |
| --- | --- |
| [`.github/`](../../.github/) | 継続的インテグレーション、Release 自動化、Issue/PR テンプレート |
| [`benchmarks/`](../../benchmarks/) | checksum-bound な Benchmark protocol、コンパクトな結果、図 |
| [`configs/`](../../configs/) | データセット、モデル選択、検証の設定 |
| [`data/`](../../data/) | 公開済み manifest、split contract、データ整合性記録 |
| [`docs/`](../) | 科学的エビデンス、再現性、architecture、versioning、多言語文書 |
| [`results/`](../../results/) | コンパクトな公開結果、モデル identity、図の provenance |
| [`scripts/`](../../scripts/) | 可搬な Python 研究 workflow、検証、モデル評価、描画ユーティリティ |
| [`src/`](../../src/) | コア `djrmcp-finder` Python 研究パッケージ |
| [`tests/`](../../tests/) | 自動テストとエンジニアリング契約チェック |
| [`user-inference-v0/`](../../user-inference-v0/) | 公開済み・凍結済み Model V0 正式ベースラインパッケージ |
| [`user-inference-v0.1/`](../../user-inference-v0.1/) | 推奨 Model V0.1 Candidate 推論パッケージ |

詳細な使用方法については、[Model V0.1 Candidate](../../user-inference-v0.1/README.ja.md) および [Model V0](../../user-inference-v0/README.ja.md) のユーザーガイドを参照してください。データ、方法、エビデンスの適用範囲については、[科学的エビデンスの説明](../SCIENTIFIC_EVIDENCE.ja.md)を参照してください。

本プロジェクト独自のコードと文書には [MIT License](../../LICENSE) が適用されます。
