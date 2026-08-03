**English** | [简体中文](REFERENCE_ENVIRONMENT.cn.md) | [日本語](REFERENCE_ENVIRONMENT.ja.md)

# Frozen embedding reference environment

The selected ESM-C 6B development embedding was generated with:

```text
Python       3.12.3
NumPy        2.5.1
PyTorch      2.13.0+cu130
Transformers 4.57.6 (Biohub fork at ef32577f55da19a4989cd7b22e004dc43a4998cb)
CUDA runtime 13.0
GPU          NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition
Linux        x86_64, glibc 2.39
```

The inference package strictly verifies the ESM-C checkpoint and Biohub Transformers
git revisions. It records the actual PyTorch/CUDA/GPU environment in every run.
The portable Docker recipe is documented in
[`workstation/README.md`](../workstation/README.md); evidence from the original
real-GPU smoke run is retained in
[`workstation/VALIDATION.json`](../workstation/VALIDATION.json) as historical metadata.
Any rebuilt image has a new identity and should receive a fresh golden-FASTA label
and score-tolerance validation before public release.
