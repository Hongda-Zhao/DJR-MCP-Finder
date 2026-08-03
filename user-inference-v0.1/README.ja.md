[English](README.md) | [简体中文](README.cn.md) | **日本語**

# DJR-MCP Finder — Model V0.1 Candidate ユーザー推論

このディレクトリは、ユーザーが用意した protein FASTA ファイルを受け取り、凍結された
V0.1 mixed-encoder candidate の予測を返します。

```text
FASTA -> ESM-2 3B -> H1 -> H2 -> [passing sequences only] ESM-C 6B -> H3
```

これは探索的スクリーニングで現在優先する実験的候補パッケージです。独立した外部検証は
まだ行われておらず、リリース済み V0 を置き換えたり非推奨にしたりするものではありません。

workstation package は、2026-07-29 に 12 個の protein を使った online run と、network を完全に
無効化した rerun を完了しました。両方の実行は、label mismatch ゼロ、probability delta ゼロで
凍結 golden standard と一致しました。元の host、image、GPU の詳細は、履歴 validation evidence
として `workstation/VALIDATION.json` に保持されており、runtime requirement ではありません。
V0.1 は scientific candidate version であり、Python wheel version `0.2.1` は engineering package
revision を識別します。

| レイヤー | 識別子 |
| --- | --- |
| 科学モデル | `model-v0.1-candidate`（正式モデルとしては未リリース） |
| 凍結 bundle revision | `model-v0.1-mixed-r1` |
| Python distribution | `djrmcp-user-inference-v01==0.2.1` |
| CLI | `djrmcp-predict-v01` |

完全な `candidate` qualifier が必要です。科学モデルと package version が異なる理由は、
リポジトリの [versioning contract](../docs/VERSIONING.md) を参照してください。

## Workstation での使用

Docker を推奨します。image は互換性のない二つの Transformers 環境を分離し、それらの間で
GPU memory を解放します。

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0.1
bash workstation/build.sh

bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample \
  0
```

既定では独立した resource を使用します。

```text
base image       djrmcp-user-inference:v0
candidate image  djrmcp-user-inference:v0.1
cache            djrmcp-v01-hf-cache
GPU              device=0
```

script は自身の場所から checkout を解決するため、任意の作業ディレクトリから呼び出せます。
入力 path と出力 path には相対 path と絶対 path のどちらも使用できます。一般的な Docker 設定は、
environment variable で上書きできます。

```bash
export DJRMCP_BASE_IMAGE=local/djrmcp-user-inference:v0
export DJRMCP_IMAGE=local/djrmcp-user-inference:v0.1
export DJRMCP_CACHE_SOURCE=/absolute/path/to/huggingface-cache
export DJRMCP_DOCKER_GPUS=all
export DJRMCP_DOCKER=docker
```

`DJRMCP_CACHE_SOURCE` には、Docker volume または絶対 host directory を指定できます。既定値は
引き続き独立した named volume です。既定では、build 時に過去に検証された V0 base image ID
を検証します。同じ互換性のある凍結環境から V0 をローカルで再構築し、そのため image ID が
異なる場合は、provenance を確認した後に
`DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh` を明示的に使用できます。
version、CUDA、Transformers、candidate-bundle の検査は引き続き実行されます。その他の option は
[`workstation/README.ja.md`](workstation/README.ja.md) を参照してください。

24 GB 以上で native BF16 をサポートする CUDA GPU を推奨します。過去の peak は ESM-2 3B が
約 5.95 GB、ESM-C 6B が約 15.0 GB でした。二つの model が同時に memory 上に置かれることは
ありません。H1/H2 を通過する sequence がなければ、H3 worker は起動しません。

## CLI

入力と bundle の検査には GPU は必要ありません。

```bash
djrmcp-predict-v01 validate-fasta proteins.faa
djrmcp-predict-v01 model-info
```

凍結された両方の Python 環境がすでに設定されている場合：

```bash
export DJRMCP_ESM2_PYTHON=/path/to/esm2-venv/bin/python
export DJRMCP_ESMC_PYTHON=/path/to/esmc-venv/bin/python

djrmcp-predict-v01 predict proteins.faa \
  --outdir run_output/sample \
  --device cuda
```

checkout 内の wrapper を直接使用することもできます。wrapper は `DJRMCP_PYTHON`、checkout
内の `.venv/bin/python`、`python3` の順に優先し、検証済みの CUDA 既定値を維持します。device
の自動選択または CPU を指定するには、`auto`/`cpu` を明示的に渡すか、`DJRMCP_DEVICE` を
設定します。

```bash
DJRMCP_PYTHON=/path/to/controller-python \
DJRMCP_ESM2_PYTHON=/path/to/esm2-venv/bin/python \
DJRMCP_ESMC_PYTHON=/path/to/esmc-venv/bin/python \
DJRMCP_CACHE_DIR=/path/to/huggingface-cache \
bash scripts/run_user_fasta.sh proteins.faa run_output/sample auto
```

cache の準備後は、CLI option `--offline` を追加するか、wrapper に `DJRMCP_OFFLINE=1` を設定
してください。出力ディレクトリには次のファイルが含まれます。

```text
predictions.tsv
run_metadata.json
CHECKSUMS.sha256
```

最終 label は `non_djr`、`djr_non_mcp`、`mcp::Nucleocytoviricota`、
`mcp::Preplasmiviricota`、`mcp::unknown/other` のいずれかです。最後の category は、sequence が
H1/H2 を通過したものの、既知の二つの H3 phyla のいずれにも確実に割り当てられなかったこと
だけを意味します。一般的な unknown-virus や out-of-distribution detector ではありません。

Head-2 の score column は `head2_mcp_probability` です。新しい run metadata は output schema
version 3 を使用します。

## 入力および凍結 contract

- FASTA ID は空でなく、一意である必要があります。20 種類の標準 amino acid と `X` を
  受け付けます。
- 同一 sequence は一度だけ embedding されます。出力では元の ID と順序が復元されます。
- 130–2906 aa の範囲外も評価できますが、out-of-training-domain warning が付与されます。
- 長い sequence は 1022-aa window / 511-aa stride で完全にカバーされ、truncate されません。
- H1/H2 は FP16 の `facebook/esm2_t36_3B_UR50D@476b639...` を使用します。
- H3 は BF16 の `Biohub/ESMC-6B@45b0fa5...` を使用し、gate-through sequence に対してのみ
  実行されます。
- classifier head は checksum で検証された pickle-free NPZ file です。wheel に sklearn
  joblib は含まれません。
- raw score、probability、threshold decision は、両方の 11,060 個の凍結 embedding set で
  完全に一致します。

各実行では、input、model、classifier head、routed subset、runtime environment、output の
SHA256 hash が記録されます。probability は development-data distribution 下での calibrated
model score であり、自然 sample における prevalence-adjusted posterior ではありません。

## 開発チェック

V0.1 Python package は NumPy 2.5.1 を pin しているため、Python 3.12 以降が必要です。CPU のみの
contract test では大規模 model をダウンロードしません。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

凍結環境と release boundary は `environment/REFERENCE_ENVIRONMENT.ja.md` を参照してください。

## ライセンス

この実験的候補パッケージと、同梱された独自の線形分類ヘッドは
[MIT License](LICENSE) で公開されています。ESM-2 と ESM-C checkpoint は別途ダウンロードされ、
各上流配布元の条件が適用されます。
[release-specific third-party notice](src/djrmcp_predict_v01/assets/project-v0.1-mixed-r1/THIRD_PARTY_NOTICES.md)
およびリポジトリレベルの [`THIRD_PARTY_NOTICES.md`](../docs/repository/THIRD_PARTY_NOTICES.md) を参照してください。
独立した外部検証は未実施です。
