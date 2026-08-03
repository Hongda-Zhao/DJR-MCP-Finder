[English](README.md) | **简体中文** | [日本語](README.ja.md)

# 可移植 Docker 部署

Docker wrapper 从脚本位置定位 `user-inference-v0` checkout，因此可从任意工作目录调用。输入与
输出路径保留在宿主机上。不可变的 ESM-C 6B checkpoint 缓存在可配置的 Docker named volume 中。

CUDA 运行需要 Docker、NVIDIA Container Toolkit 支持，以及约 15 GB 可用显存；建议 24 GB 或
更多。可以显式选择 CPU inference，但它会加载约 25 GB 的 float32 权重，并不是经过验证的常规
部署路径。

## 配置

Wrapper 提供可移植默认值，并接受以下环境变量覆盖：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DJRMCP_DOCKER` | `docker` | Docker-compatible executable |
| `DJRMCP_BASE_IMAGE` | `ubuntu:24.04` | `build.sh` 使用的 base image |
| `DJRMCP_IMAGE` | `djrmcp-user-inference:v0` | 本地构建的 image tag |
| `DJRMCP_CACHE_VOLUME` | `djrmcp-esmc6b-cache` | Hugging Face cache named volume |
| `DJRMCP_DEVICE` | `cuda` | 运行设备：`auto`、`cuda` 或 `cpu` |
| `DJRMCP_GPU` | `0` | 暴露给 container 的物理 GPU index |
| `DJRMCP_GPU_CHECK` | `1` | 仅在需要跳过 CUDA preflight 时设为 `0` |
| `DJRMCP_OFFLINE` | `0` | 设为 `1` 以进行断网的 cached inference |
| `DJRMCP_UID` / `DJRMCP_GID` | 宿主机 ID | bind-mounted 输出所使用的 container user/group |

改变 base image 或 dependency pin 会产生不同于历史验证记录的部署，需要重新验证。

## 构建

将 `checkout` 设为下载后的目录；不要求固定宿主机路径：

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
bash "${checkout}/workstation/build.sh"
```

构建默认保留经过验证的 CUDA preflight。在 Docker 无法暴露 NVIDIA GPU 的宿主机上构建 image 时，
只显式跳过该 preflight：

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_GPU_CHECK=0 \
bash "${checkout}/workstation/build.sh"
```

构建会验证打包后的冻结 model bundle，并创建配置的 cache volume；不会下载 ESM-C checkpoint。

## 运行用户 FASTA

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_DEVICE=cuda DJRMCP_GPU=0 \
bash "${checkout}/workstation/run_user_fasta.sh" \
  /absolute/path/proteins.faa \
  /absolute/path/run_output/sample
```

可选的第三个参数覆盖 `DJRMCP_GPU`。第一次 prediction 会把固定 revision 的 `Biohub/ESMC-6B`
下载到 `DJRMCP_CACHE_VOLUME`；后续运行复用该缓存。若缓存已经填充，可要求完全不依赖网络：

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_OFFLINE=1 DJRMCP_DEVICE=cuda DJRMCP_GPU=0 \
bash "${checkout}/workstation/run_user_fasta.sh" \
  /absolute/path/proteins.faa \
  /absolute/path/run_output/sample_offline
```

宿主机输出目录包含 `predictions.tsv`、`run_metadata.json` 和 `CHECKSUMS.sha256`。已有标准输出
文件不会被覆盖，wrapper 返回成功前会验证 checksum manifest。

## 历史部署验证

较早的部署已于 2026-07-27 通过端到端 GPU smoke test。冻结的 6.352B-parameter checkpoint 使用
了 13,047,401,984 peak allocated GPU bytes，并为 `examples/synthetic_example.faa` 生成了
checksum-valid 输出。精确 image、runtime、输入和输出证据作为历史 metadata 保存在
`VALIDATION.json`。其中原始宿主机 alias 和部署路径只用于 provenance，不是当前 checkout 的指令或
要求。

可移植性修改后重新构建会产生新的 image identity；把新 image 视为独立验证之前，应重新运行 GPU
smoke test。
