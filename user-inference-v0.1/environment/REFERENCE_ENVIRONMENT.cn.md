[English](REFERENCE_ENVIRONMENT.md) | **简体中文** | [日本語](REFERENCE_ENVIRONMENT.ja.md)

# 冻结 mixed-encoder 参考环境

这是用于验证的历史环境，并非必需的主机或 checkout 路径。可移植 wrapper 会记录每次推理
实际观察到的环境。

```text
Common       Python 3.12.3; NumPy 2.5.1; PyTorch 2.13.0+cu130
ESM-2 3B    Transformers 5.14.1; CUDA FP16; window batch 2
ESM-C 6B    Biohub Transformers 4.57.6 @ ef32577f55da19a4989cd7b22e004dc43a4998cb;
             CUDA BF16; window batch 1
GPU          NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition
OS           Linux x86_64; glibc 2.39; CUDA runtime 13.0
```

两个 encoder 都先进行 residue mean，再进行 overlapping-window mean（1022 residues，stride
511），生成 2560 维向量，随后执行供 classifier 使用的冻结 float16 storage round-trip。
公共 runtime 会验证两个 checkpoint revision 和各 encoder 对应的 Transformers 安装，并记录
实际的 model、package、GPU、parameter count 和 peak-memory provenance。

科学状态：仅使用 Train 的共享五折 CV nomination；prospective external Test 记录为零；需要
外部确认；已发布 V0 保持不变。
