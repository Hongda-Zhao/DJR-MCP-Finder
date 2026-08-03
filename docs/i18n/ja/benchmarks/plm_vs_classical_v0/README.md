<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/README.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

[English](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/benchmarks/plm_vs_classical_v0/README.md) | [简体中文](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/benchmarks/plm_vs_classical_v0/README.cn.md) | **日本語**

# PLM と従来型リモートホモロジー手法の Benchmark

> **内部の cross-fitted 開発 Benchmark — 外部 Test ではありません**

この有効なディレクトリは、公開・checksum 検証用のコンパクトなコアです。固定プロトコル、設定、コード、コンパクトな結果表、検証記録、図のソースデータ、PNG/PDF/SVG 出力を保持します。入力、生の receipt、検索データベース、ログ、行単位の ledger、TIFF export は、`FULL_ARTIFACT_POINTER.json` が示す完全アーカイブ内で checksum に結び付けられたままです。データは削除されていません。

このディレクトリでは、固定された DJR-MCP-Finder Train split 上で、プロジェクトの protein-language-model（PLM）system と、配列・profile 検索 baseline を比較します。保護された Test split を評価することはありません。既存の五つの `global_component_id` fold を、循環 3/1/1 design で再利用します。各 cycle では、三つの fold で database/model を構築し、独立した一つの fold で動作 threshold を calibration し、もう一つの独立した fold を評価します。Calibration と評価は、fitting には含めず、まったく同じ database/model を共有します。

Benchmark には、意図的に分離された二つの track があります。

1. **Controlled retrieval：** ESM-C/ESM-2 の最大 cosine similarity、BLASTP、DIAMOND、MMseqs2、HMMER、PSI-BLAST は、fold ごとに同一の positive reference ID を使用します。
2. **Operational supervised system：** ESM-C 6B embedding を、プロジェクトで固定された H1/H2 classifier 設定で fitting します。この track は labelled negative からも学習するため、改善を PLM representation だけに帰属させる目的では使用しません。

三つの endpoint は、DJR detection（H1）、VMA 対 cellular DJR（H2）、end-to-end VMA detection です。Fold-macro component-balanced AP と、99.5% source-balanced specificity で calibration された sensitivity を primary とします。99.9% endpoint は、resolution-limited secondary evidence としてのみ報告します。

Aggregation 前の audit では、fold 3 の cellular-DJR negative 62 件が一つの component であることも判明しました。影響を受ける H2/end-to-end の low-FPR sensitivity interval は保持しますが、conditional かつ resolution-limited と明記します。`PROTOCOL.md` を参照してください。Score に依存しない count と leakage check は `DATA_AUDIT.md` に記録しています。

## コンパクトコアの検証

```bash
cd /path/to/DJR-MCP-Finder/benchmarks/plm_vs_classical_v0
sha256sum -c CHECKSUMS.sha256
```

`results/validation.json` は、成功した full-validator の固定記録です。コンパクト版だけでは full validator や検索 pipeline を意図的に再実行できません。これらの生入力と receipt は archive のみに存在するためです。GitHub の `pbs/` launcher は portable replay template ですが、単独で動作する runner ではありません。厳密な end-to-end replay では、submit 前に `FULL_ARTIFACT_POINTER.json` に従って、その `full_v1` tree を復元してください。このコンパクトな source checksum を、full-pipeline や科学的結果の checksum と解釈してはいけません。

固定された科学的 contract は `PROTOCOL.md`、マシン可読な path、checksum、parameter、tool version は `config/benchmark.json` を参照してください。

復元済み full archive を別の system で使う場合は、checkout 済み config を provenance として維持し、repository root から runtime copy を生成します。

```bash
python scripts/render_portable_config.py \
  benchmarks/plm_vs_classical_v0/config/benchmark.json \
  build/local-configs/plm_vs_classical_v0.json
```

最初に `DJRMCP_PROJECT_ROOT`、`DJRMCP_ARCHIVE_ROOT`、`DJRMCP_SOFTWARE_ROOT`、`DJRMCP_VENV_ROOT` を設定し、生成された path を `DJRMCP_PLM_CONFIG` として渡してください。PBS launcher は、過去の gds2 project path を必須とせず、これらの variable（または自身の location/`PBS_O_WORKDIR`）から checkout を解決します。

Headline の controlled track では、supervised classifier と retrieval tool を混在させません。Supervised ESM-C、metadata-grouped HMM、iterative PSI-BLAST は、明記された別個の supplementary track で報告します。
