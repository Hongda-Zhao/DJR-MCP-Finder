[English](REFERENCE_ENVIRONMENT.md) | [简体中文](REFERENCE_ENVIRONMENT.cn.md) | **日本語**

# 凍結 mixed-encoder の参照環境

これは検証に使用した履歴環境であり、必須のホストや checkout の場所ではありません。
ポータブル wrapper は、各推論実行で実際に観測された環境を記録します。

```text
Common       Python 3.12.3; NumPy 2.5.1; PyTorch 2.13.0+cu130
ESM-2 3B    Transformers 5.14.1; CUDA FP16; window batch 2
ESM-C 6B    Biohub Transformers 4.57.6 @ ef32577f55da19a4989cd7b22e004dc43a4998cb;
             CUDA BF16; window batch 1
GPU          NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition
OS           Linux x86_64; glibc 2.39; CUDA runtime 13.0
```

両 encoder は、residue mean に続いて overlapping-window mean（1022 residues、stride 511）
を行い、2560 次元ベクトルを生成します。その後、classifier が使用する凍結 float16 storage
round-trip を適用します。公開 runtime は両 checkpoint の revision と encoder ごとの
Transformers 環境を検証し、実際の model、package、GPU、parameter count、peak-memory の
provenance を記録します。

科学的ステータス：Train のみを用いた共有 five-fold CV nomination、prospective external Test
record はゼロ、外部確認が必要、リリース済み V0 は変更なし。
