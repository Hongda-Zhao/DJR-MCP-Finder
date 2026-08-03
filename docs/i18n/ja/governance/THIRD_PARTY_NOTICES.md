<!-- i18n-mirror: non-authoritative translation; source=docs/repository/THIRD_PARTY_NOTICES.md -->

> **翻訳について：** この翻訳は閲覧用です。相違がある場合は、原文の言語版を正式版とします。

# 第三者に関する通知とライセンスの範囲

ファイルに別段の記載がない限り、ルートの
[`LICENSE`](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/LICENSE) は、プロジェクトが作成した
ソースコード、ドキュメント、設定、図、およびオリジナルの同梱線形分類器 head artifacts に適用されます。

このライセンスによって、外部の model checkpoints、software、datasets、protein sequences、structures、
database content、trademarks が再ライセンスされることはありません。これらの資料には、それぞれの
条件が引き続き適用されます。本リポジトリ内の references、accessions、checksums、および派生した
科学的結果は、基となる第三者の原資料が MIT の下で再配布されることを意味しません。

## モデルとランタイムソフトウェア

| コンポーネント | 上流の条件 | 本リポジトリでの配布 |
| --- | --- | --- |
| [`Biohub/ESMC-6B`](https://huggingface.co/Biohub/ESMC-6B) | MIT；上流の model card と [Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/) を確認してください | Checkpoint は別途ダウンロードし、ここでは再配布しません。 |
| [`Biohub/transformers`](https://github.com/Biohub/transformers) | Apache-2.0 | 固定した上流 Git revision からインストールし、vendored source は含みません。 |
| [`facebook/esm2_t36_3B_UR50D`](https://huggingface.co/facebook/esm2_t36_3B_UR50D) | MIT | 未リリースの V0.1 candidate だけが使用し、checkpoint は別途ダウンロードします。 |
| `pyproject.toml` ファイルで宣言された Python dependencies | 各 dependency は上流の license と notices を維持します。 | Python package tooling からインストールし、vendored source は含みません。 |

正式な V0 bundle には、リリース固有の通知も
[`user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md`](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md)
に含まれています。

## データとデータベースの参照

研究 workflow は、NCBI、UniProt、AlphaFold DB、ICTV materials、MGnify、サイトローカル archives などの
外部リソースについて provenance を記録します。ユーザーは、それぞれの正式な提供元からリソースを
入手し、提供元の現在の licenses、attribution requirements、access policies、terms of use に従う必要が
あります。コンパクトな GitHub release は、これらの外部リソースに対する追加の権利を付与しません。
