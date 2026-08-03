[English](REFERENCE_ENVIRONMENT.md) | **简体中文** | [日本語](REFERENCE_ENVIRONMENT.ja.md)

# 冻结 embedding 参考环境

所选 ESM-C 6B 开发 embedding 使用以下环境生成：

```text
Python       3.12.3
NumPy        2.5.1
PyTorch      2.13.0+cu130
Transformers 4.57.6 (Biohub fork at ef32577f55da19a4989cd7b22e004dc43a4998cb)
CUDA runtime 13.0
GPU          NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition
Linux        x86_64, glibc 2.39
```

推理包会严格验证 ESM-C checkpoint 和 Biohub Transformers 的 git revision，并在每次运行中
记录实际的 PyTorch/CUDA/GPU 环境。可移植 Docker 配方见
[`workstation/README.cn.md`](../workstation/README.cn.md)；原始真实 GPU smoke run 的证据作为
历史 metadata 保存在 [`workstation/VALIDATION.json`](../workstation/VALIDATION.json)。任何重新
构建的 image 都具有新的 identity，在公开发布前应重新接受 golden-FASTA label 和 score-tolerance
验证。
