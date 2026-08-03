[English](REFERENCE_ENVIRONMENT.md) | [简体中文](REFERENCE_ENVIRONMENT.cn.md) | **日本語**

# 凍結 embedding の参照環境

選択された ESM-C 6B の開発用 embedding は、次の環境で生成されました。

```text
Python       3.12.3
NumPy        2.5.1
PyTorch      2.13.0+cu130
Transformers 4.57.6 (Biohub fork at ef32577f55da19a4989cd7b22e004dc43a4998cb)
CUDA runtime 13.0
GPU          NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition
Linux        x86_64, glibc 2.39
```

推論パッケージは ESM-C checkpoint と Biohub Transformers の git revision を厳密に検証し、
各実行で実際の PyTorch/CUDA/GPU 環境を記録します。ポータブルな Docker 手順は
[`workstation/README.ja.md`](../workstation/README.ja.md) に記載されています。元の実 GPU
smoke run の証拠は、履歴 metadata として
[`workstation/VALIDATION.json`](../workstation/VALIDATION.json) に保持されています。再構築した
image は新しい identity を持つため、公開リリース前に golden-FASTA の label と score tolerance
を改めて検証してください。
