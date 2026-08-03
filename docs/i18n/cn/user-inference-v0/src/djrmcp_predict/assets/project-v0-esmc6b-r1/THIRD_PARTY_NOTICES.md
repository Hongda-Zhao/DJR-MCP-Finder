<!-- i18n-mirror: non-authoritative translation; source=user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md -->

> **翻译说明：** 本译文仅供阅读；如有差异，以源语言原文为准。

# 第三方声明

Embedding model 需从以下来源另行获取：

- `Biohub/ESMC-6B`
- https://huggingface.co/Biohub/ESMC-6B

冻结的 adapter 使用 Biohub Transformers fork：

- https://github.com/Biohub/transformers
- revision `ef32577f55da19a4989cd7b22e004dc43a4998cb`

Biohub ESM code 和 ESM-C model weights 以 MIT 发布。在重新分发或部署之前，请查阅上游 model card、
third-party notices 和 [Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/)。固定的
[Biohub Transformers fork](https://github.com/Biohub/transformers) 以 Apache-2.0 发布。此 inference
bundle 不会重新分发 6B checkpoint。

DJR-MCP Finder package code 和原创的捆绑 linear classifier heads 由 package-level MIT `LICENSE`
覆盖。该许可证不会为 external checkpoint、upstream runtime software 或 source datasets 重新授予许可。
