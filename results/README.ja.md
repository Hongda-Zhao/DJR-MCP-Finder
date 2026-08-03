[English](README.md) | [简体中文](README.cn.md) | **日本語**

# Git に含まれる結果

このリポジトリでは、公開済み V0 解析を読み取り、監査するために必要な、コンパクトで
checksum-bound な証拠のみを追跡します。

- `figures/project_v0/`
- `validation_family_robustness_v0_schema5_mixed_heads/`
- 公開リポジトリの検証プログラムが必要とする小規模なチェックサム、fold、比較ファイル

大規模な生成出力、埋め込み、生の中間ファイル、モデルキャッシュは、引き続きルートの
`.gitignore` により除外されます。該当する場合、それらの識別情報は専用のデータセット、
モデル、ベンチマーク、または結果マニフェストに保持されています。

特に、`data/processed/v0/CHECKSUMS.sha256` と
`postsplit_integrity_v0/CHECKSUMS.sha256` は archive identity inventory です。クリーンな Git
checkout には、前者の 38 個の dataset target と後者の 15 個の integrity-audit target は意図的に
含まれていません。これら二つの manifest に対して `sha256sum -c` を実行する前に、
checksum-bound archive を復元してください。
