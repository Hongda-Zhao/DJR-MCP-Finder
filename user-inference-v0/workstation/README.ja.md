[English](README.md) | [简体中文](README.cn.md) | **日本語**

# ポータブル Docker deployment

Docker wrapper は script の場所から `user-inference-v0` checkout を特定するため、任意の作業
ディレクトリから呼び出せます。入力 path と出力 path は host 上に保持されます。不変の
ESM-C 6B checkpoint は、設定可能な名前付き Docker volume に cache されます。

CUDA での実行には、NVIDIA Container Toolkit をサポートする Docker と、約 15 GB の空き
memory を持つ GPU が必要です。24 GB 以上を推奨します。CPU inference を明示的に選択する
こともできますが、約 25 GB の float32 weight を読み込み、通常の deployment path としては
検証されていません。

## 設定

wrapper にはポータブルな既定値があり、次の environment override を使用できます。

| 変数 | 既定値 | 用途 |
| --- | --- | --- |
| `DJRMCP_DOCKER` | `docker` | Docker-compatible executable |
| `DJRMCP_BASE_IMAGE` | `ubuntu:24.04` | `build.sh` が使用する base image |
| `DJRMCP_IMAGE` | `djrmcp-user-inference:v0` | ローカルで構築する image tag |
| `DJRMCP_CACHE_VOLUME` | `djrmcp-esmc6b-cache` | 名前付き Hugging Face cache volume |
| `DJRMCP_DEVICE` | `cuda` | 実行 device：`auto`、`cuda`、`cpu` |
| `DJRMCP_GPU` | `0` | container に公開する物理 GPU index |
| `DJRMCP_GPU_CHECK` | `1` | CUDA preflight だけを省略する場合に限り `0` に設定 |
| `DJRMCP_OFFLINE` | `0` | network を無効にした cached inference では `1` に設定 |
| `DJRMCP_UID` / `DJRMCP_GID` | host ID | bind mount した出力に使用する container user/group |

base image または dependency pin を変更すると、過去の validation record とは異なる
deployment になり、改めて検証が必要です。

## Build

`checkout` をダウンロードしたディレクトリに設定します。固定の host path は不要です。

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
bash "${checkout}/workstation/build.sh"
```

build は、検証済みの既定動作として CUDA preflight を維持します。Docker から NVIDIA GPU を
公開できない host で image を build する場合は、この preflight だけを明示的に省略します。

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_GPU_CHECK=0 \
bash "${checkout}/workstation/build.sh"
```

build は、パッケージ化された凍結 model bundle を検証し、設定された cache volume を作成します。
ESM-C checkpoint はダウンロードしません。

## ユーザー FASTA の実行

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_DEVICE=cuda DJRMCP_GPU=0 \
bash "${checkout}/workstation/run_user_fasta.sh" \
  /absolute/path/proteins.faa \
  /absolute/path/run_output/sample
```

省略可能な第三 argument は `DJRMCP_GPU` を上書きします。最初の prediction run は、pin された
`Biohub/ESMC-6B` revision を `DJRMCP_CACHE_VOLUME` にダウンロードし、その後の実行は再利用
します。cache の準備後は、network に依存しない実行を要求できます。

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_OFFLINE=1 DJRMCP_DEVICE=cuda DJRMCP_GPU=0 \
bash "${checkout}/workstation/run_user_fasta.sh" \
  /absolute/path/proteins.faa \
  /absolute/path/run_output/sample_offline
```

host の出力ディレクトリには `predictions.tsv`、`run_metadata.json`、`CHECKSUMS.sha256` が
含まれます。既存の標準出力ファイルは上書きされず、wrapper は成功を返す前に checksum
manifest を検証します。

## 過去の deployment validation

以前の deployment は 2026-07-27 に end-to-end GPU smoke test に合格しました。凍結された
6.352B-parameter checkpoint は peak allocated GPU bytes として 13,047,401,984 を使用し、
`examples/synthetic_example.faa` に対して checksum-valid な出力を生成しました。正確な image、
runtime、input、output の証拠は、履歴 metadata として `VALIDATION.json` に保持されています。
元の host alias と deployment path は provenance のためだけの情報であり、この checkout の
手順や要件ではありません。

ポータビリティ変更後に再構築すると、新しい image identity が生成されます。その image を
独立に検証済みとみなす前に、GPU smoke test を再実行してください。
