[English](README.md) | [简体中文](README.cn.md) | **日本語**

# DJR-MCP Finder — Model V0 ユーザー推論

この独立ディレクトリは、凍結された DJR-MCP Finder project V0 を、ユーザーが用意した protein
FASTA ファイル向けの推論ツールとしてパッケージ化します。model の学習、temperature や
threshold の変更、過去の Test split の読み取り、メイン project の release identity の変更は
行いません。

| レイヤー | 識別子 |
| --- | --- |
| 科学モデル | `model-v0`（リリース済み） |
| 凍結 bundle revision | `model-v0-esmc6b-r1` |
| Python distribution | `djrmcp-user-inference==0.1.0` |
| CLI | `djrmcp-predict` |

これらの識別子は、リポジトリの [versioning contract](../docs/VERSIONING.md) に従います。
Python package version は engineering version であり、科学モデルの名称を変更するものでは
ありません。

```text
protein FASTA
  -> pinned ESM-C 6B embedding
  -> frozen H1/H2/H3 linear heads
  -> frozen H1 -> H2 -> H3 gate
  -> predictions.tsv + run_metadata.json + CHECKSUMS.sha256
```

## 出力の意味

最終出力 label は、次の五種類だけです。

```text
non_djr
djr_non_mcp
mcp::Nucleocytoviricota
mcp::Preplasmiviricota
mcp::unknown/other
```

`mcp::unknown/other` は、sample が H1/H2 を通過したものの、既知の二つの H3 phyla のいずれにも
確実に割り当てられなかったことだけを意味します。任意の未知ウイルスや、一般的な
out-of-distribution data の detector ではありません。

Head-2 の score column は `head2_mcp_probability` です。新しい run metadata は output schema
version 2 を使用します。

## インストール

基本チェックと unit test では ESM-C をダウンロードしません。

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

実際の推論には、pin された Biohub Transformers revision と PyTorch が必要です。

```bash
python -m pip install -e '.[inference]'
```

24 GB 以上のメモリを持つ CUDA GPU を推奨します。凍結 benchmark では、ESM-C 6B の実測
peak memory は約 15.0 GB でした。CPU mode は約 25 GB の float32 weight を読み込みますが、
通常利用する経路としては検証されていません。

## 使用方法

まず CPU 上で入力と model package を検証します。

```bash
djrmcp-predict validate-fasta proteins.faa
djrmcp-predict model-info
```

続いて推論を実行します。

```bash
djrmcp-predict predict proteins.faa \
  --outdir run_output/my_sample \
  --device cuda
```

FASTA と model の確認、推論、結果 checksum の検証を順番に行う完全な wrapper も利用できます。

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
bash "${checkout}/scripts/run_user_fasta.sh" proteins.faa run_output/my_sample cuda
```

wrapper は自身の path から checkout を特定するため、リポジトリ root から起動する必要は
ありません。checkout 内の `.venv/bin/python` を優先し、存在しない場合は `python3` を使用
します。runtime と path は明示的に上書きできます。

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_PYTHON=/path/to/venv/bin/python \
DJRMCP_CACHE_DIR=/path/to/huggingface-cache \
DJRMCP_DEVICE=cuda \
bash "${checkout}/scripts/run_user_fasta.sh" proteins.faa run_output/my_sample
```

`DJRMCP_DEVICE` の既定値は `cuda` で、`auto` または `cpu` を明示的に設定できます。第三
position argument が優先されます。`DJRMCP_OFFLINE=1` は wrapper を offline mode に切り替えます。
Docker/NVIDIA deployment と、設定可能な image、cache volume、GPU、UID/GID については
[`workstation/README.ja.md`](workstation/README.ja.md) を参照してください。

初回実行時には、pin された `Biohub/ESMC-6B` revision が Hugging Face からダウンロードされます。
cache の準備後は、network access を無効化できます。

```bash
djrmcp-predict predict proteins.faa \
  --outdir run_output/my_sample \
  --device cuda \
  --offline
```

出力ディレクトリには次のファイルが含まれます。

```text
predictions.tsv    各入力 protein の H1/H2/H3 score、gate state、最終 label
run_metadata.json  入力/model SHA256、environment、hardware、threshold、runtime、解釈境界
CHECKSUMS.sha256   二つの結果ファイルの integrity check
```

既存の結果は既定では上書きされません。標準出力ファイルを明示的に置き換える場合のみ
`--overwrite` を使用してください。この場合も、一時ファイルへの書き込み後に atomic rename
が行われます。

## 入力 contract

- FASTA ID は空でなく、一意である必要があります。完全な header が保持されます。
- sequence は大文字に変換されます。学習時に使用した 20 種類の標準 amino acid と `X` を
  受け付けます。
- 空 sequence、gap、stop symbol、その他の ambiguous residue、明らかに nucleotide のみの
  FASTA は fail closed になります。
- 同一 sequence で ID だけが異なる場合、embedding は一度だけ計算され、元の順序に戻されます。
- 130–2906 aa の training range 外の sequence も評価されますが、out-of-domain warning が
  付与されます。
- 長い sequence は常に、凍結された 1022-aa window / 511-aa stride を使用し、暗黙に
  truncate されることはありません。

## 凍結 contract

- ESM-C 6B：`Biohub/ESMC-6B@45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a`
- Transformers：`Biohub/transformers@ef32577f55da19a4989cd7b22e004dc43a4998cb`
- embedding：residue mean の後に overlapping-window mean、2560 dimensions
- classifier input：training と一致する float16 storage-precision round trip
- H1/H2 gate：probability `>=` frozen threshold
- H3 reject：最大 probability が frozen threshold より `<` の場合は `unknown/other` を出力

三つの sklearn joblib file は、checksum で検証された NumPy weight として export されています。
公開推論では pickle を deserialize しません。`PARITY_REPORT.json` には、11,060 個すべての
凍結 ESM-C embedding について、元の joblib file との parity が記録されています。元の
embedding に使用した software と hardware の参照環境は
`environment/REFERENCE_ENVIRONMENT.ja.md` を参照してください。

## 科学的境界

現在の ESM-C 6B model には、新しい prospective external Test がありません。出力 probability は、
development-data distribution 下での凍結済み calibrated model score であり、自然 proteome
における prevalence-adjusted posterior probability ではありません。大規模な探索には、独立した
false-positive assessment、same-source challenge set、構造および手動での検証が必要です。

## ライセンス

この独立 package と、同梱された独自の linear classifier head は
[MIT License](LICENSE) で公開されています。ESM-C checkpoint は別途ダウンロードされ、この
package からは再配布されません。checkpoint と pin された runtime dependency には、各 upstream
の条件が適用されます。[release-specific third-party notice](src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md)
およびリポジトリレベルの [`THIRD_PARTY_NOTICES.md`](../docs/repository/THIRD_PARTY_NOTICES.md) を参照してください。
