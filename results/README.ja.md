[English](README.md) | [简体中文](README.cn.md) | **日本語**

# Git に含まれる結果

このリポジトリでは、公開済み V0 解析を読み取り、監査するために必要な、コンパクトで
checksum-bound な証拠のみを追跡します。

- `figures/project_v0/`
- `validation_family_robustness_v0_schema5_mixed_heads/`
- public-checkout validator と `PROJECT_V0_RELEASE_CHECKSUMS.sha256` が必要とする小規模な
  checksum、fold、comparison ファイル

大規模な生成出力、embedding、生の intermediate ファイル、model cache は、引き続きルートの
`.gitignore` により除外されます。該当する場合、それらの identity は release checksum と
provenance record に保持されています。

特に、`data/processed/v0/CHECKSUMS.sha256` と
`postsplit_integrity_v0/CHECKSUMS.sha256` は archive identity inventory です。クリーンな Git
checkout には、前者の 38 個の dataset target と後者の 15 個の integrity-audit target は意図的に
含まれていません。これら二つの manifest に対して `sha256sum -c` を実行する前に、
checksum-bound archive を復元してください。
