<!-- i18n-mirror: non-authoritative translation; source=user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/MODEL_CARD.md -->

> **翻译说明：** 本译文仅供阅读；如有差异，以源语言原文为准。

# Project V0 ESM-C 6B 推理 bundle

此 bundle 以不使用 pickle 的 NumPy 表示形式，包含三个冻结的 DJR-MCP Finder project-V0 linear heads。
其中不包含 ESM-C 6B checkpoint。

## 预期用途

- H1：DJR 与 non-DJR 的区分。
- H2：viral-morphogenesis association；在实际运行中，仅在通过 H1 后到达。
- H3：Nucleocytoviricota 与 Preplasmiviricota 的区分，并带有冻结的 low-confidence rejection；
  在实际运行中，仅在通过 H1 和 H2 后到达。

## 固定表示

- Model：`Biohub/ESMC-6B`
- Window/stride：1022/511 amino acids
- Pooling：先计算 residue mean，再计算 window mean
- Dimension：2560
- Classifier input：float16 storage round-trip，然后进行 float32 linear inference

## 局限性

- 入选的 ESM-C 6B 尚未在新的 prospective external Test 上评分。
- Calibrated scores 并不是经过 prevalence 调整的 posterior probabilities。
- H3 `unknown/other` 不是通用的 unknown-virus 或 OOD detector。
- Training sources 与 labels 存在部分混杂；仍需独立的 same-source validation。
- 对超出已观察 training alphabet/length domain 的输入应谨慎处理。

确切 identities 与验证信息请参阅 `release.json` 和 `PARITY_REPORT.json`。
