<!-- i18n-mirror: non-authoritative translation; source=results/figures/project_v0/README.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

[English](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/results/figures/project_v0/README.md) | [简体中文](https://github.com/Hongda-Zhao/DJR-MCP-Finder/blob/main/results/figures/project_v0/README.cn.md) | **日本語**

# Project V0 の現行 figure release

有効な release には、一つの main figure と一つの supplementary figure が含まれます。Figure 1 は primary model を選択し、説明します。Supplementary Fig. S1 は、freeze 後の schema 5 family-neighbour evaluation であり、Figure 1 に feedback することはできません。

| Figure | Directory | Conclusion | Interpretation boundary |
| --- | --- | --- | --- |
| 1. 14-model development benchmark | `model_benchmark_metric_revision_1/` | raw-score ranking に基づき ESM-C 6B を選択、`S=0.997145`。旧 650M H1 CV AP の `0.857` は sigmoid-tie artifact であり、`0.997917` に修正 | Train/Validation development selection。ESM-C 6B Test=`not_evaluated` |
| Supplementary Fig. S1. Schema 5 head-focused robustness | `validation_family_robustness_v0_schema5_head_focus/` | 八つの homogeneous system と九つの事前登録済み mixed recipe。Train-CV nominee は H1/H2 ESM-2 3B + H3 ESM-C 6B で、四つの source に対する warning は `0/4` | auxiliary のみ。Robustness は ranking に影響せず、equivalence test、release gate、independent Test、unseen-family benchmark のいずれでもない |

Supplementary Fig. S1 は三つの layer、すなわち per-head performance、expected-path performance、3×3 mixed recipe に対する Train-CV → nomination → four-source checking の sequence を示します。H3 の rare category と unclassified category は分離したまま維持し、一般的な unknown-virus detector として統合してはいけません。解釈の完全な guide は、その directory の `FIGURE_GUIDE.md` を参照してください。

完成した各ディレクトリには、編集可能な SVG/PDF、PNG、パネルの元データ、品質確認・出典記録、および個別のチェックサムマニフェストが含まれます。利用可能な TIFF も現在のコンパクトな公開セットに含まれます。主ワークフローのマニフェストは Figure 1 に、head-focus 図のマニフェストは Supplementary Fig. S1 に結び付けられるため、マニフェストを束ねる追加の索引は保持しません。

過去の Test data が開かれたのは ESM-2 650M だけです。現在有効な figure には ESM-C 6B Test panel が含まれていないため、旧 model の evidence が新 model に誤って帰属されることを防ぎます。
