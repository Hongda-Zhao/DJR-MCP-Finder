<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/figures/FIGURE_LEGEND.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# 図の legend

## Fig. 1 | Protein-language-model と従来型 remote-homology retrieval の比較

**a, b** 三つの Benchmark task と九つの method に対する fold-macro component-balanced average precision（a）および sensitivity（b）。Sensitivity は evaluation fold で測定し、独立した calibration fold 上で 99.5% source-balanced specificity を目標に選択した threshold を使用します。色付きの row bar は、controlled、resource-augmented、metadata-augmented、operational の各 track を区別します。Daggers は resource-augmented PSI-BLAST、double daggers は metadata-grouped HMMER、section symbol は operational supervised ESM-C system を示します。これらの track を controlled anchor の代わりには使用しません。**c, d** ESM-C 6B cosine retrieval と、各 controlled classical anchor の average precision（c）および calibration-targeted sensitivity（d）について、事前登録された difference。点は観察された five-fold macro difference、横線は 10,000 回の paired global-component bootstrap replicate による percentile 95% interval です。ゼロ未満の値は classical anchor に有利です。白抜きの点は、観察された singleton negative component を条件とする H2/end-to-end interval を示します。**e** Controlled method の fold-macro evaluation specificity。破線は 99.5% calibration target であり、仮定された evaluation 値ではありません。内部 Benchmark は、循環 3/1/1 component cross-fitting の下で 6,634 Train record、5,566 global component を含みます。Validation と Test prediction はゼロです。H2/end-to-end endpoint には、62 件の cellular-DJR record が一つの component に属する fold/source が含まれ、分解能が制限されます。Source data は付属する TSV file で提供します。

## Supplementary Fig. 1 | 記述的 remote-homology coverage diagnostic

**a** Best local BLASTP match が query の 80% 未満を cover する subset での component-balanced sensitivity。点は三つの task の記述的 estimate を示します。この stratum は、H1 では positive component を 264 個、各 VMA task では 100 個含みます。**b** Controlled method と task ごとに no-hit として encode された evaluation record の割合。これらの panel は main Benchmark と同じ calibration-targeted threshold を使用します。異なる method を同一の realized evaluation specificity に合わせず、BLAST local query coverage を global evolutionary-distance estimate としても扱いません。Source data は付属する TSV file で提供します。

## 日本語での解釈

Main figure の c と d が結論 panel です。H1 では ESM-C の confidence interval 全体がゼロの左側にあります。H2 と end-to-end VMA の interval は、いずれもゼロをまたぎます。Panel e は実際の evaluation specificity を使い、「calibration target 99.5%」を、すべての evaluation fold が 99.5% を達成したと誤解しないようにします。Supplementary figure は distant/low-coverage signal の探索専用で、優越性の推論には使用しません。
