[English](README.md) | **简体中文** | [日本語](README.ja.md)

# DJR-MCP Finder — Model V0.1 Candidate 用户推理

该目录接受用户自己的蛋白 FASTA，并输出冻结 V0.1 mixed-encoder 候选模型的预测：

```text
FASTA -> ESM-2 3B -> H1 -> H2 -> [仅通过者] ESM-C 6B -> H3
```

这是当前优先用于探索性筛查的实验候选包。它尚未经过独立外部验证，也不取代或弃用
已发布的 V0。

工作站封装已于 2026-07-29 完成 12 条蛋白的在线与完全断网复跑；两次预测与冻结金标准
均为 0 mismatch / 0 probability delta。原始主机、镜像和 GPU 信息作为历史验证证据保存在
`workstation/VALIDATION.json`，不是运行时要求。这里的 V0.1 是科学候选版本，Python wheel
的 `0.2.1` 是其工程封装修订号。

| 层次 | 标识 |
| --- | --- |
| 科学模型 | `model-v0.1-candidate`（尚未作为正式模型发布） |
| 冻结 bundle revision | `model-v0.1-mixed-r1` |
| Python distribution | `djrmcp-user-inference-v01==0.2.1` |
| CLI | `djrmcp-predict-v01` |

必须保留完整的 `candidate` 限定词。科学模型版本与包版本的区别见仓库
[版本命名合同](../docs/VERSIONING.md)。

## 工作站使用

推荐使用 Docker；镜像内将两个不兼容的 Transformers 环境隔离，并顺序释放显存：

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0.1
bash workstation/build.sh

bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample \
  0
```

默认使用独立资源：

```text
base image       djrmcp-user-inference:v0
candidate image  djrmcp-user-inference:v0.1
cache            djrmcp-v01-hf-cache
GPU              device=0
```

脚本从自身位置解析检出目录；可从任意当前目录调用，输入和输出既可使用相对路径也可使用
绝对路径。常用 Docker 参数均可通过环境变量覆盖：

```bash
export DJRMCP_BASE_IMAGE=local/djrmcp-user-inference:v0
export DJRMCP_IMAGE=local/djrmcp-user-inference:v0.1
export DJRMCP_CACHE_SOURCE=/absolute/path/to/huggingface-cache
export DJRMCP_DOCKER_GPUS=all
export DJRMCP_DOCKER=docker
```

`DJRMCP_CACHE_SOURCE` 可以是 Docker volume 名称或绝对宿主机目录；默认仍使用独立的 named
volume。默认构建会验证历史确认过的 V0 base image ID。若 V0 是在本机由相同冻结环境兼容
重建、因此 image ID 不同，可在核对来源后显式使用
`DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh`；版本、CUDA、Transformers 与
候选 bundle 校验仍会执行。其他选项见 [`workstation/README.cn.md`](workstation/README.cn.md)。

建议至少 24 GB CUDA 显存且原生支持 BF16。历史峰值约为 ESM-2 3B 5.95 GB、ESM-C 6B 15.0 GB；
两者不会同时驻留。若没有序列通过 H1/H2，H3 worker 不会启动。

## CLI

只检查输入或 bundle 不需要 GPU：

```bash
djrmcp-predict-v01 validate-fasta proteins.faa
djrmcp-predict-v01 model-info
```

在已经配置两套 frozen Python 环境时：

```bash
export DJRMCP_ESM2_PYTHON=/path/to/esm2-venv/bin/python
export DJRMCP_ESMC_PYTHON=/path/to/esmc-venv/bin/python

djrmcp-predict-v01 predict proteins.faa \
  --outdir run_output/sample \
  --device cuda
```

也可直接使用检出目录中的封装脚本；它优先使用 `DJRMCP_PYTHON`，其次使用检出目录的
`.venv/bin/python`，最后回退到 `python3`，并保持验证过的 CUDA 默认值。需要自动选择或
CPU 时，显式传入 `auto`/`cpu` 或设置 `DJRMCP_DEVICE`：

```bash
DJRMCP_PYTHON=/path/to/controller-python \
DJRMCP_ESM2_PYTHON=/path/to/esm2-venv/bin/python \
DJRMCP_ESMC_PYTHON=/path/to/esmc-venv/bin/python \
DJRMCP_CACHE_DIR=/path/to/huggingface-cache \
bash scripts/run_user_fasta.sh proteins.faa run_output/sample auto
```

缓存完成后可加 CLI `--offline`，或给封装脚本设置 `DJRMCP_OFFLINE=1`。输出目录包含：

```text
predictions.tsv
run_metadata.json
CHECKSUMS.sha256
```

最终标签为 `non_djr`、`djr_non_mcp`、`mcp::Nucleocytoviricota`、
`mcp::Preplasmiviricota` 或 `mcp::unknown/other`。最后一类仅表示通过 H1/H2 后，
未可靠归入两个已知 H3 phylum；它不是通用未知病毒或 OOD 检测器。

Head-2 分数字段为 `head2_mcp_probability`；新生成的运行元数据使用输出 schema version 3。

## 输入与冻结合同

- FASTA ID 必须非空且唯一；接受 20 种标准氨基酸和 `X`。
- 相同序列只计算一次 embedding，输出仍恢复原始 ID 与顺序。
- 130–2906 aa 之外仍可运行，但结果带训练域外 warning。
- 长序列按 1022 aa window / 511 aa stride 完整覆盖，不截断。
- H1/H2 使用 `facebook/esm2_t36_3B_UR50D@476b639...`、FP16。
- H3 使用 `Biohub/ESMC-6B@45b0fa5...`、BF16，且仅对 gate-through 序列运行。
- 分类头是 checksum-verified、pickle-free NPZ；wheel 不包含 sklearn joblib。
- 两套 11,060 条冻结 embedding 的 raw score、概率和阈值判定 parity 均为精确相等。

每次运行记录输入、模型、分类头、路由子集、运行环境和输出的 SHA256。概率是开发数据
分布下的 calibrated model score，不是自然样本中的 prevalence-adjusted posterior。

## 开发检查

V0.1 Python package 需要 Python 3.12 或更高版本，因为它固定使用 NumPy 2.5.1。纯 CPU 合同测试
不会下载大模型：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

冻结环境与发布边界见 `environment/REFERENCE_ENVIRONMENT.md`。

## 许可证

该实验候选包及其中的原创线性分类头采用 [MIT License](LICENSE)。ESM-2 与 ESM-C
模型权重均另行下载，并保留其上游条款；详见
[release-specific 第三方声明](src/djrmcp_predict_v01/assets/project-v0.1-mixed-r1/THIRD_PARTY_NOTICES.md)
和仓库级 [`THIRD_PARTY_NOTICES.md`](../docs/repository/THIRD_PARTY_NOTICES.md)。独立外部验证仍未完成。
