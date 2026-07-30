[English](README.md) | **简体中文**

# DJR-MCP Finder — User Inference V0

这个独立目录把冻结的 DJR-MCP Finder project V0 封装成面向用户蛋白 FASTA 的推理工具。
它不会训练模型、修改 temperature/threshold、读取历史 Test，或改变主工程 release identity。

```text
protein FASTA
  -> pinned ESM-C 6B embedding
  -> frozen H1/H2/H3 linear heads
  -> frozen H1 -> H2 -> H3 gate
  -> predictions.tsv + run_metadata.json + CHECKSUMS.sha256
```

## 输出语义

最终输出只有五种：

```text
non_djr
djr_non_vma
vma::Nucleocytoviricota
vma::Preplasmiviricota
vma::unknown/other
```

`vma::unknown/other` 仅表示样本通过 H1/H2 后，不能可靠归入 H3 的两个已知 phylum；
它不是任意未知病毒或全局 OOD 检测器。

## 安装

基础检查和单元测试不下载 ESM-C：

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
```

真实推理需要固定的 Biohub Transformers revision 与 PyTorch：

```bash
python -m pip install -e '.[inference]'
```

推荐使用至少 24 GB 显存的 CUDA GPU。冻结 benchmark 中 ESM-C 6B 的实测峰值约为
15.0 GB；CPU 模式会以 float32 加载约 25 GB 权重，速度未作为常规路径验证。

## 使用

先在 CPU 上完成输入与模型包检查：

```bash
djrmcp-predict validate-fasta proteins.faa
djrmcp-predict model-info
```

然后运行推理：

```bash
djrmcp-predict predict proteins.faa \
  --outdir run_output/my_sample \
  --device cuda
```

也可以使用完整包装脚本（依次执行 FASTA、模型、推理和结果 checksum 检查）：

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
bash "${checkout}/scripts/run_user_fasta.sh" proteins.faa run_output/my_sample cuda
```

包装脚本根据自身位置定位 checkout，不要求从仓库根目录启动。默认优先使用 checkout 内的
`.venv/bin/python`，否则使用 `python3`；运行环境与路径均可显式覆盖：

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_PYTHON=/path/to/venv/bin/python \
DJRMCP_CACHE_DIR=/path/to/huggingface-cache \
DJRMCP_DEVICE=cuda \
bash "${checkout}/scripts/run_user_fasta.sh" proteins.faa run_output/my_sample
```

`DJRMCP_DEVICE` 默认是 `cuda`，也可显式设为 `auto` 或 `cpu`；第三个位置参数优先级更高。
`DJRMCP_OFFLINE=1` 会把包装脚本切换为离线模式。Docker/NVIDIA 部署及可配置的 image、
cache volume、GPU、UID/GID 见 [`workstation/README.cn.md`](workstation/README.cn.md)。

首次运行会从 Hugging Face 下载固定 revision 的 `Biohub/ESMC-6B`。已有缓存时可禁止联网：

```bash
djrmcp-predict predict proteins.faa \
  --outdir run_output/my_sample \
  --device cuda \
  --offline
```

输出目录包含：

```text
predictions.tsv    每条输入蛋白的 H1/H2/H3 分数、门控状态与最终标签
run_metadata.json  输入/模型 SHA256、环境、硬件、阈值、运行时间与解释边界
CHECKSUMS.sha256   两个结果文件的完整性校验
```

默认拒绝覆盖已有结果。若明确需要替换标准输出文件，可使用 `--overwrite`；写入仍采用临时文件
加 atomic rename。

## 输入合同

- FASTA ID 必须非空且唯一；保留完整 header。
- 序列统一转大写，允许训练中出现的 20 种标准氨基酸和 `X`。
- 空序列、gap、终止符、其他模糊残基和疑似纯核酸 FASTA 均 fail closed。
- 相同序列、不同 ID 只计算一次 embedding，再恢复原始顺序。
- 长度不在训练范围 130–2906 aa 时仍可计算，但写入域外 warning。
- 长序列始终使用冻结的 1022-aa window / 511-aa stride；不静默截断。

## 冻结合同

- ESM-C 6B：`Biohub/ESMC-6B@45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a`
- Transformers：`Biohub/transformers@ef32577f55da19a4989cd7b22e004dc43a4998cb`
- embedding：residue mean，再对重叠 window mean，2560 维
- classifier input：与训练一致的 float16 存储精度 round-trip
- H1/H2 gate：概率 `>=` 冻结 threshold
- H3 reject：最大概率 `<` 冻结 threshold 时输出 `unknown/other`

三个 sklearn joblib 已导出为 checksum-verified NumPy 权重；公共推理不反序列化 pickle。
`PARITY_REPORT.json` 记录全部 11,060 条冻结 ESM-C embedding 上与原 joblib 的一致性验证。
原始 embedding 的参考软件/硬件环境见 `environment/REFERENCE_ENVIRONMENT.md`。

## 科学边界

当前 ESM-C 6B 没有新的 prospective external Test。输出概率是开发数据分布下的冻结 calibrated
model score，不是自然蛋白组中经过 prevalence 调整的后验概率。用于大规模发现时，应进行独立的
false-positive、同来源挑战集和结构/人工验证。

该目录目前不包含项目级 `LICENSE`，因此不授予复制、修改或再分发权。任何正式公开发布前仍需
确定代码和数据/分类头许可，并补充引用信息。
