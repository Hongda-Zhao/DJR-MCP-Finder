[English](README.md) | **简体中文** | [日本語](README.ja.md)

# 可移植 V0.1 开发候选版部署

本目录部署 mixed-encoder V0.1 candidate，不改变正式 V0 目录、image 或 cache。V0.1 仍是由
Train-CV nomination 得到、需要 prospective external confirmation 的开发候选版。

## 隔离合同

```text
checkout         <repository>/user-inference-v0.1
base image       djrmcp-user-inference:v0
candidate image  djrmcp-user-inference:v0.1
cache            djrmcp-v01-hf-cache
entrypoint       djrmcp-predict-v01
```

该 image 派生自 checksum-verified 的正式 V0 image。它复用已经验证的 V0 CUDA/PyTorch/NumPy
与 ESM-C 环境，只增加小型 ESM-2 Transformers overlay 和 Triton 第一次 GPU forward pass 所需的
compiler 支持。两个 Transformers distribution 保持隔离：

```text
/opt/djrmcp-esm2  H1/H2: facebook/esm2_t36_3B_UR50D@476b6399..., float16
/opt/djrmcp-venv  H3:    Biohub/ESMC-6B@45b0fa5d..., bfloat16
```

ESM-2 环境使用 Transformers 5.14.1 及固定版本的 overlay dependency；ESM-C 环境使用 Biohub
fork `ef32577f55da19a4989cd7b22e004dc43a4998cb`。两个环境共享不可变的 V0 NumPy 2.5.1 和
PyTorch 2.13.0 安装。Controller 先用 ESM-2 3B 对所有 exact-unique 输入序列做 embedding，释放
该 worker 后，只对同时通过 H1 与 H2 的序列启动 ESM-C 6B。因此单 GPU 运行不会让两个 checkpoint
同时驻留。

冻结 benchmark 的峰值约为 ESM-2 3B 5.95 GB、ESM-C 6B 15.0 GB。建议至少 24 GB 且原生支持
BF16 的 CUDA GPU。CPU inference 不是经过验证的 workstation 路径。

## Fresh-clone 配置

V0.1 image 基于 V0 workstation image，因此 fresh clone 必须先构建 V0。本地重建的 V0 image
会具有不同于历史验证 image 的 Docker ID。确认它来自预期 checkout 和固定 V0 环境后，在构建
V0.1 时只显式关闭历史 image-ID gate：

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0
bash workstation/build.sh

cd ../user-inference-v0.1
DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh
```

如果本地已经存在历史验证的精确 `djrmcp-user-inference:v0` image，应保留默认 identity gate，
直接运行 `bash workstation/build.sh`，不要设置上述环境变量。该 override 不会关闭固定 package、
CUDA、model-bundle 或 release checksum 检查。

## 构建

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0.1
bash workstation/build.sh
```

构建首先验证 `djrmcp-user-inference:v0` 是否仍具有经过验证的精确 image identity；它从不 retag
或修改该 image。随后验证两个 Python 环境和带 checksum 的 candidate bundle。它会创建独立的
`djrmcp-v01-hf-cache` volume，但不下载任何 checkpoint，也不构成端到端 inference validation。

脚本从自身位置解析 build context，因此也可从其他工作目录通过绝对路径调用。可移植设置均为环境变量：

```text
DJRMCP_DOCKER                      Docker executable（默认：docker）
DJRMCP_BASE_IMAGE                 V0 base image tag
DJRMCP_EXPECTED_BASE_IMAGE_ID     required base ID；仅在有意使用 compatible local rebuild 时设为空字符串
DJRMCP_IMAGE                      candidate output image tag
DJRMCP_CACHE_SOURCE               named volume 或绝对宿主机 cache 目录
DJRMCP_DOCKER_GPUS                完整 Docker --gpus 值（例如 all、device=0 或 device=GPU-...）
```

未设置 `DJRMCP_DOCKER` 时，`DJRMCP_DOCKER_BIN` 可作为向后兼容 alias。

`DJRMCP_GPU` 仍是默认 `DJRMCP_DOCKER_GPUS=device=$DJRMCP_GPU` 所选择设备的简写。精确的
validated V0 image ID 仍是默认 gate。只关闭该 identity gate 不会关闭固定 package、CUDA、
model-bundle 或 release checksum 检查。

## 运行用户 FASTA

使用物理 GPU 0：

```bash
bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample \
  0
```

使用第二张 GPU 时，把最后一个参数改为 `1`。第一次 inference 会下载不可变的 ESM-2 checkpoint；
只有至少一个序列到达 H3 时才下载 ESM-C。随后两者都从 `djrmcp-v01-hf-cache` 复用。输入和输出保留
在调用方指定的路径。默认的大型 cache 是 Docker named volume；若希望明确指定 cache 位置，可将
`DJRMCP_CACHE_SOURCE` 设为绝对宿主机目录。

两个 checkpoint 都已缓存后，要求完全不依赖网络地复跑：

```bash
DJRMCP_OFFLINE=1 bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample_offline \
  0
```

这会禁用 container network，设置 Hugging Face/Transformers offline 环境，并向两个隔离 worker
传递 CLI `--offline` 选项。

输出目录包含：

```text
predictions.tsv
run_metadata.json
CHECKSUMS.sha256
```

已有标准结果文件不会被覆盖。Wrapper 返回成功前会验证输出 checksum manifest。

## 部署验证

最终 image 已于 2026-07-29 通过 checksum-bound、包含 12 条蛋白且源自 Train 的 fixture；其中四条
record 到达 H3。在线运行和 `--network none` 断网运行都与冻结 golden prediction 完全一致，label、
routing 和 probability difference 均为零。精确的原始宿主机、image、输入、输出、revision、GPU
memory 和 checksum 证据作为历史 metadata 保存在 `VALIDATION.json`；该宿主机不是部署要求。

这建立的是工程复现，而不是 prospective scientific external confirmation。不要把该 image retag
为 `v0`，也不要挂载 `djrmcp-esmc6b-cache`；两个 wrapper 都会明确拒绝这些正式 V0 名称。
