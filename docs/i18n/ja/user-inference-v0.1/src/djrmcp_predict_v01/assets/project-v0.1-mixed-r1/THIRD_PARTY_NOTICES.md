<!-- i18n-mirror: non-authoritative translation; source=user-inference-v0.1/src/djrmcp_predict_v01/assets/project-v0.1-mixed-r1/THIRD_PARTY_NOTICES.md -->

> **翻訳について：** この翻訳は閲覧用です。相違がある場合は、原文の言語版を正式版とします。

# 第三者に関する通知

V0.1 development candidate は、次の external checkpoints をダウンロードしますが、再配布はしません。

- `facebook/esm2_t36_3B_UR50D`。MIT の下で公開されています。
- `Biohub/ESMC-6B`。MIT の下で公開され、
  [Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/) が付属します。

固定済みの [Biohub Transformers fork](https://github.com/Biohub/transformers) は Apache-2.0 の下で
公開されています。その他の runtime dependencies には、それぞれの upstream licenses と notices が
引き続き適用されます。

DJR-MCP Finder package code とオリジナルの同梱 linear classifier heads は、package-level MIT
`LICENSE` の対象です。このライセンスによって、external checkpoints、upstream runtime software、
source datasets が再ライセンスされることはありません。
