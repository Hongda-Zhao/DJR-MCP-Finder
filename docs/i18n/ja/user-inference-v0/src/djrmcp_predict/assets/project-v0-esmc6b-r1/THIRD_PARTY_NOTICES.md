<!-- i18n-mirror: non-authoritative translation; source=user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md -->

> **翻訳について：** この翻訳は閲覧用です。相違がある場合は、原文の言語版を正式版とします。

# 第三者に関する通知

Embedding model は、次の場所から別途取得します。

- `Biohub/ESMC-6B`
- https://huggingface.co/Biohub/ESMC-6B

凍結済み adapter は Biohub Transformers fork を使用します。

- https://github.com/Biohub/transformers
- revision `ef32577f55da19a4989cd7b22e004dc43a4998cb`

Biohub ESM code と ESM-C model weights は MIT の下で公開されています。再配布またはデプロイの前に、
上流の model card、third-party notices、[Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/)
を確認してください。固定済みの [Biohub Transformers fork](https://github.com/Biohub/transformers) は
Apache-2.0 の下で公開されています。この inference bundle は 6B checkpoint を再配布しません。

DJR-MCP Finder package code とオリジナルの同梱 linear classifier heads は、package-level MIT
`LICENSE` の対象です。このライセンスによって、external checkpoint、upstream runtime software、
source datasets が再ライセンスされることはありません。
