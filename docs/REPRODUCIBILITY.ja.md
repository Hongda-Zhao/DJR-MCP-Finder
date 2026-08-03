# 再現性のレベルとアーカイブ境界

[English](REPRODUCIBILITY.md) | [简体中文](REPRODUCIBILITY.cn.md) | **日本語**

[ドキュメント一覧](README.ja.md) | [リポジトリ README](repository/README.ja.md) |
[科学的根拠](SCIENTIFIC_EVIDENCE.ja.md)

このプロジェクトで「再現可能」は三つの異なる意味を持ちます。公開 checkout の検証、公開モデル checkpoint を使ったユーザー予測の反復、または固定アーカイブと可搬な Python entrypoint を使った研究 workflow の再実行です。要件は意図的に分けて記載します。元の PBS launcher は歴史的 replay evidence であり、公開された既定 entrypoint ではありません。

## 対象範囲の概要

| レベル | 公開 checkout だけで可能か | 再現する内容 | 追加要件 |
| --- | --- | --- | --- |
| A — Checkout 検証 | はい | メタデータ、ドキュメント、テスト、FASTA 検証、bundle 識別子、パッケージビルド | Python 3.12+ と宣言済み依存関係 |
| B — 公開ユーザー推論 | いいえ | ユーザー FASTA からの実際の V0 または V0.1 予測 | 固定された公開 checkpoint。検証済みかつ推奨されるワークステーション経路：Linux、Docker、CUDA GPU |
| C — アーカイブに基づく科学的再実行 | いいえ | データセット構築、embedding、モデル選択、内部 Benchmark workflow | 固定された非公開アーカイブ／データベース、checksum、Python、MMseqs2 などのバージョン管理されたツール。HPC は歴史的 launcher を任意で再実行する場合のみ必要 |
| 保護された Test 評価 | いいえ | 管理者が承認した事前登録済み Test 実行 | 保護された ledger と個別の承認。アーカイブと HPC だけでは不十分 |

このコンパクトな GitHub リポジトリでは、元のデータベース、モデル checkpoint、大規模 embedding、ログ、TIFF ファイル、過去の実行出力のすべてを再配布していません。

## Level A — 公開 checkout を検証する

次の手順では、大規模 encoder のダウンロードや GPU を必要とせず、コードと固定パッケージの規約を検証できます。

```bash
cd /path/to/DJR-MCP-Finder
python3.12 -m venv .venv
source .venv/bin/activate

make setup
make metadata docs-check lint test smoke
```

`make smoke` は FASTA 検証と `model-info` を実行しますが、予測は行いません。wheel/sdist の構築とローカル CI 相当の全ゲートも含めるには、次を実行します。

```bash
make check
```

標準 target の定義はリポジトリの [`Makefile`](../Makefile) にあります。Level A 検証の合格は、checkout とコンパクト bundle の内部整合性を示しますが、生物学的精度や外部一般化性能を示すものではありません。

## Level B — 公開ユーザー予測を反復する

ユーザー推論に非公開の研究アーカイブは不要です。

PBS、`qsub`、HPC scheduler も不要です。PBS は、どちらの公開予測 interface にも含まれません。

検証済みかつ推奨されるワークステーション経路は、Linux + Docker + CUDA GPU です。両パッケージとも自動／CPU デバイスモードを明示的に提供しますが、大容量メモリを要する CPU fallback は正式なワークステーション検証の対象外であり、基準となる再現経路として扱うべきではありません。

- **優先する実験的候補：** [Model V0.1 Candidate ユーザーガイド](../user-inference-v0.1/README.md)と[初回クローン後のワークステーション設定](../user-inference-v0.1/workstation/README.md#fresh-clone-setup)に従ってください。最初の予測で ESM-2 がダウンロードされ、少なくとも一つの配列が H3 に到達した時点で ESM-C がダウンロードされます。
- **リリース済みベースライン：** [Model V0 ユーザーガイド](../user-inference-v0/README.md)と [V0 ワークステーション設定](../user-inference-v0/workstation/README.md)に従ってください。最初の予測で固定された ESM-C checkpoint がダウンロードされます。

どちらの経路も `predictions.tsv`、`run_metadata.json`、`CHECKSUMS.sha256` を生成します。その入力経路で必要なすべての checkpoint がキャッシュされた後に限り、ネットワークを無効にした実行が可能です。ユーザー推論の反復は、固定モデル／ランタイム経路を検証しますが、学習データ、モデル選択、Benchmark は再実行しません。

## Level C — アーカイブに基づく研究 workflow を再実行する

完全な再実行には、公開 checkout に含まれない次のリソースが必要です。

- checksum が一致するソースデータベースと、コンパクト／完全 artifact アーカイブ。
- 固定設定で参照されるモデル embedding と生の Benchmark ledger、および存在する場合は `FULL_ARTIFACT_POINTER.json` ファイルで参照されるデータ。
- 記録済みの Python、CUDA、MMseqs2、その他のバージョン管理されたソフトウェア環境。
- 選択した段階に十分な local または HPC compute。PBS/HPC が必要なのは、元の checksum-bound Benchmark launcher を意図的に再実行する場合だけです。

### 過去のパスをローカル環境に割り当てる

固定設定内の過去の絶対パスは来歴情報として維持されます。固定入力を編集せず、サイトローカルなコピーを生成してください。

```bash
cd /path/to/DJR-MCP-Finder

export DJRMCP_PROJECT_ROOT="$(pwd -P)"
export DJRMCP_ARCHIVE_ROOT=/absolute/path/to/checksum-bound-archives
export DJRMCP_DATABASE_ROOT=/absolute/path/to/frozen-input-databases
export DJRMCP_SOFTWARE_ROOT=/absolute/path/to/versioned-HPC-software
export DJRMCP_VENV_ROOT=/absolute/path/to/project-python-environment

python3 scripts/render_portable_config.py \
  configs/v0_dataset.json \
  build/local-configs/v0_dataset.json
```

これらの変数はローカルリソースの場所を示すもので、ダウンロード URL や認証情報ではありません。renderer は宣言済みのパス接頭辞を書き換えますが、ファイルをダウンロードせず、割り当て先のリソースが存在することも証明しません。割り当てた入力はあらかじめ存在し、固定 checksum と一致していなければなりません。

### 可搬な Python 研究 entrypoint を実行する

dataset 構築には Python と MMseqs2 が必要ですが、PBS と Environment Modules は不要です。runner は既存の出力ディレクトリを上書きしないため、まだ存在しない明示的なパスを使用してください。

```bash
python3 scripts/run_v0_dataset.py \
  --config build/local-configs/v0_dataset.json \
  --work-dir build/replay/v0-interim \
  --output-dir build/replay/v0-processed

python3 scripts/run_postsplit_integrity_audit.py --help
```

二つ目のコマンドは、可搬な post-split audit に必要な manifest、FASTA input、output directory を表示します。どちらの runner も `--python` と `--mmseqs` override を受け付け、それ以外は local executable を使用します。Benchmark replay には、固定設定から参照される archived embedding、ledger、存在する場合は `FULL_ARTIFACT_POINTER.json` が引き続き必要です。checksum-bound の `benchmarks/*/pbs/` launcher は、任意の歴史的 HPC replay evidence であり、通常の entrypoint ではありません。凍結 evidence bundle の identity を保つため、そのまま維持します。

## 固定された来歴と完全性

- `/aptmp/hongda/DJRMCP_Develope/` 以下の過去のパスと記録済みホストは、来歴情報またはアーカイブの場所であり、通常のユーザー推論に必要な実行時要件ではありません。
- 固定モデル bundle は、分類器 head を読み込む前に `CHECKSUMS.sha256` を検証します。
- ユーザー予測には、出力と実行メタデータに対する `CHECKSUMS.sha256` が含まれます。
- コンパクトな Benchmark とリリースエビデンスには、それらを所有する checksum manifest が保持されます。
- モデル checkpoint は固定された上流識別子からダウンロードされ、ここでは再配布されません。
- Checksum が保証するのはコンテンツの同一性であり、著者や安全な転送ではありません。

固定設定、検証記録、レポート、artifact pointer に含まれる過去のパスを一括置換しないでください。特に `legacy_schema4_numerical_operator.venv_root` は Amendment-D の厳密な数値再実行規約に属します。固定 bundle 内の notice またはモデルカードを変更する場合は、その bundle の checksum manifest を更新して `model-info` を再実行する必要があります。重み、閾値、ルーティング、encoder を変更する場合は、[`VERSIONING.md`](VERSIONING.md) に従って新しい科学モデル識別子を作成する必要があります。

## 保護された Test の境界

リポジトリには選択済みモデルだけを対象とする Test runner が含まれますが、公開 checkout やパスの上書きによってアクセス権を得ることはできません。本番 ledger は外部管理者 registry に固定され、上書きを拒否します。実行には registry の権限に加えて、固定入力と workflow に対する承認が必要です。アーカイブ、ソフトウェアスタック、HPC へのアクセスだけでは、Test の実行は承認されません。

## 再現性の入口

- [完全な科学 workflow](research/WORKFLOW_V0.md)
- [科学的根拠と主張の境界](SCIENTIFIC_EVIDENCE.md)
- [正式 V0 リファレンス環境](../user-inference-v0/environment/REFERENCE_ENVIRONMENT.md)
- [Candidate リファレンス環境](../user-inference-v0.1/environment/REFERENCE_ENVIRONMENT.md)
- [正式 V0 ワークステーション検証](../user-inference-v0/workstation/VALIDATION.json)
- [Candidate ワークステーション検証](../user-inference-v0.1/workstation/VALIDATION.json)
- [リポジトリリリースマニフェスト](../release-manifest.json)
