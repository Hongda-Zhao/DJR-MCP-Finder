[English](README.md) | [简体中文](README.cn.md) | **日本語**

# ポータブル V0.1 development-candidate deployment

このディレクトリは、正式な V0 のディレクトリ、イメージ、キャッシュを変更せずに、混合
エンコーダー V0.1 候補モデルを展開します。V0.1 は Train-CV で選定された、独立した外部検証
が未実施の実験的候補です。

## 分離 contract

```text
checkout         <repository>/user-inference-v0.1
base image       djrmcp-user-inference:v0
candidate image  djrmcp-user-inference:v0.1
cache            djrmcp-v01-hf-cache
entrypoint       djrmcp-predict-v01
```

この image は、checksum で検証された正式 V0 image から派生しています。検証済みの V0
CUDA/PyTorch/NumPy と ESM-C 環境を再利用し、小規模な ESM-2 Transformers overlay と、Triton の
最初の GPU forward pass に必要な compiler support だけを追加します。二つの Transformers
distribution は分離されたままです。

```text
/opt/djrmcp-esm2  H1/H2: facebook/esm2_t36_3B_UR50D@476b6399..., float16
/opt/djrmcp-venv  H3:    Biohub/ESMC-6B@45b0fa5d..., bfloat16
```

ESM-2 環境は Transformers 5.14.1 と pin された overlay dependency を使用し、ESM-C 環境は
Biohub fork `ef32577f55da19a4989cd7b22e004dc43a4998cb` を使用します。両環境は、不変の V0
NumPy 2.5.1 と PyTorch 2.13.0 installation を共有します。controller はまず、exact-unique な
入力 sequence をすべて ESM-2 3B で embedding します。この worker を解放してから、H1 と H2
の両方を通過した sequence に対してのみ ESM-C 6B を起動します。そのため single-GPU run で
両 checkpoint が同時に常駐することはありません。

凍結 benchmark の peak は、ESM-2 3B が約 5.95 GB、ESM-C 6B が約 15.0 GB でした。24 GB
以上で native BF16 をサポートする CUDA GPU を推奨します。CPU inference は検証済みの
workstation path ではありません。

## Fresh clone のセットアップ

V0.1 image は V0 workstation image を拡張するため、fresh clone では先に V0 を build する
必要があります。ローカルで再構築した V0 image は、過去に検証した image とは異なる Docker
image ID を持ちます。意図した checkout と pin された V0 環境から build されたことを確認した
うえで、V0.1 を build するときに履歴 image-ID gate だけを明示的に無効化してください。

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0
bash workstation/build.sh

cd ../user-inference-v0.1
DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh
```

過去に検証された正確な `djrmcp-user-inference:v0` image がすでに利用可能な場合は、既定の
identity gate を維持し、environment-variable override を付けずに
`bash workstation/build.sh` を実行してください。上記の override は、pin された package、
CUDA、model-bundle、release checksum の検査を無効化しません。

## Build

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0.1
bash workstation/build.sh
```

build は最初に、`djrmcp-user-inference:v0` が検証済みの正確な image identity を維持している
ことを確認します。この image を retag または変更することはありません。続いて、両方の
Python 環境と checksum-bearing candidate bundle を検証します。独立した
`djrmcp-v01-hf-cache` volume を作成しますが、いずれの checkpoint もダウンロードせず、
end-to-end inference validation にはなりません。

script は自身の場所から build context を解決するため、別の作業ディレクトリから絶対 path で
呼び出すこともできます。ポータブルな設定は environment variable です。

```text
DJRMCP_DOCKER                      Docker executable (default: docker)
DJRMCP_BASE_IMAGE                 V0 base image tag
DJRMCP_EXPECTED_BASE_IMAGE_ID     required base ID; set to an empty string only
                                  for an intentionally compatible local rebuild
DJRMCP_IMAGE                      candidate output image tag
DJRMCP_CACHE_SOURCE               named volume or absolute host cache directory
DJRMCP_DOCKER_GPUS                complete Docker --gpus value (for example all,
                                  device=0, or device=GPU-...)
```

`DJRMCP_DOCKER` が未設定の場合、`DJRMCP_DOCKER_BIN` は backward-compatible alias として
受け付けられます。

`DJRMCP_GPU` は、既定の `DJRMCP_DOCKER_GPUS=device=$DJRMCP_GPU` で選択される device の
shorthand として引き続き使用できます。正確な検証済み V0 image ID が既定の gate です。
その identity gate だけを無効化しても、pin された package、CUDA、model-bundle、release
checksum の検査は無効になりません。

## ユーザー FASTA の実行

物理 GPU 0 を使用する場合：

```bash
bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample \
  0
```

二番目の GPU を使用する場合は、最後の argument に `1` を指定します。最初の inference で
不変の ESM-2 checkpoint がダウンロードされます。ESM-C は、少なくとも一つの sequence が H3
に到達した場合にのみダウンロードされます。その後は両方とも `djrmcp-v01-hf-cache` から再利用
されます。入力と出力は caller が指定した path に保持されます。既定の大規模 cache は Docker
named volume です。明示的な cache location を使用する場合は、`DJRMCP_CACHE_SOURCE` に絶対
host directory を設定してください。

両 checkpoint の cache が準備できた後は、network に依存しない rerun を要求できます。

```bash
DJRMCP_OFFLINE=1 bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample_offline \
  0
```

これは container network を無効化し、Hugging Face/Transformers の offline environment を設定し、
分離された両 worker に CLI `--offline` flag を渡します。

出力ディレクトリには次のファイルが含まれます。

```text
predictions.tsv
run_metadata.json
CHECKSUMS.sha256
```

既存の標準 result file は上書きされません。wrapper は成功を返す前に output checksum manifest
を検証します。

## Deployment validation

最終 image は 2026-07-29 に、checksum-bound で Train 由来の 12-protein fixture に合格しました。
四つの record が H3 に到達しました。online run と `--network none` offline run は、label、routing、
probability の差がすべてゼロで、凍結 golden prediction と一致しました。元の host、image、input、
output、revision、GPU-memory、checksum の正確な証拠は、履歴 metadata として
`VALIDATION.json` に保持されています。その host は、この deployment に必要ありません。

これは engineering reproduction を確立するものであり、prospective scientific external
confirmation ではありません。この image を `v0` に retag したり、`djrmcp-esmc6b-cache` を
mount したりしないでください。両 wrapper は、これらの正式 V0 名を明示的に拒否します。
