<!-- i18n-mirror: non-authoritative translation; source=user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/MODEL_CARD.md -->

> **翻訳について：** この翻訳は閲覧用です。相違がある場合は、原文の言語版を正式版とします。

# Project V0 ESM-C 6B 推論 bundle

この bundle には、凍結済みの三つの DJR-MCP Finder project-V0 linear heads が、pickle を使用しない
NumPy 表現で含まれています。ESM-C 6B checkpoint は含まれていません。

## 想定用途

- H1：DJR と non-DJR の識別。
- H2：viral-morphogenesis association。運用上は H1 を通過した後にのみ到達します。
- H3：Nucleocytoviricota と Preplasmiviricota の識別、および凍結済み low-confidence rejection。
  運用上は H1 と H2 を通過した後にのみ到達します。

## 固定表現

- Model：`Biohub/ESMC-6B`
- Window/stride：1022/511 amino acids
- Pooling：residue mean の後に window mean
- Dimension：2560
- Classifier input：float16 storage round-trip の後に float32 linear inference

## 制限事項

- 選択された ESM-C 6B は、新しい prospective external Test ではまだ評価されていません。
- Calibrated scores は prevalence-adjusted posterior probabilities ではありません。
- H3 `unknown/other` は、汎用的な unknown-virus または OOD detector ではありません。
- Training sources と labels は部分的に交絡しており、独立した same-source validation が引き続き
  必要です。
- 観測済み training alphabet/length domain の範囲外にある入力は、慎重に扱う必要があります。

正確な identities と検証情報については、`release.json` と `PARITY_REPORT.json` を参照してください。
