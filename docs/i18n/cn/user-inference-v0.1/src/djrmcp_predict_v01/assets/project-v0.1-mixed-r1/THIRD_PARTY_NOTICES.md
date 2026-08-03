<!-- i18n-mirror: non-authoritative translation; source=user-inference-v0.1/src/djrmcp_predict_v01/assets/project-v0.1-mixed-r1/THIRD_PARTY_NOTICES.md -->

> **翻译说明：** 本译文仅供阅读；如有差异，以源语言原文为准。

# 第三方声明

V0.1 development candidate 会下载但不会重新分发以下 external checkpoints：

- `facebook/esm2_t36_3B_UR50D`，以 MIT 发布。
- `Biohub/ESMC-6B`，以 MIT 发布，并附有
  [Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/)。

固定的 [Biohub Transformers fork](https://github.com/Biohub/transformers) 以 Apache-2.0 发布。其他
runtime dependencies 保留各自的 upstream licenses 和 notices。

DJR-MCP Finder package code 和原创的捆绑 linear classifier heads 由 package-level MIT `LICENSE`
覆盖。该许可证不会为 external checkpoints、upstream runtime software 或 source datasets 重新授予许可。
