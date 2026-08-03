<!-- i18n-mirror: non-authoritative translation; source=benchmarks/plm_vs_classical_v0/figures/QA_REPORT.md -->

> この翻訳は閲覧用です。固定された英語の原文が正式かつ権威ある版です。

# Figure QA report

状態：**PASS**。

## 科学的・データ完全性

- Visualization は、状態が `PASS` の検証済み `summary.json` および `validation.json` artifact に結び付けられています。
- 27 個すべての method–task primary-metric row と、12 個すべての事前登録済み paired comparison が、正確に一度ずつ含まれます。
- Paired panel は、報告された point estimate と、10,000 回の paired global-component bootstrap replicate による percentile 95% interval を使用します。P value または Holm field は plot しません。
- Low-coverage panel は、`best_local_qcov_lt80` stratum の controlled method–task row 18 個をすべて含みます。
- Plot の都合で record、method、task、fold、interval を sampling または除外していません。
- Secondary/resource-augmented、metadata-augmented、operational の各 track は、controlled comparison と視覚的・文章上で分離したままです。

## Source preflight

厳密な static preflight は、14 件の PASS、0 件の WARN、0 件の FAIL を報告します。有効な Python syntax、Python-only backend、編集可能な SVG/PDF text setting、sans-serif font、検出された最小 text size 5.2 pt、安全でない rainbow map の不使用、SVG/PDF/TIFF export、600 dpi raster output、183 mm の figure width、sampling または simulated data が検出されないこと、guard されていない logarithmic transform がないことを確認しています。

## Export と目視検査

- Main figure：183 × 215 mm。PNG/TIFF は 600 dpi で 4320 × 5070 pixel。SVG/PDF は編集可能な text を維持します。
- Supplementary figure：183 × 86 mm。PNG/TIFF は 600 dpi で 4320 × 2040 pixel。SVG/PDF は編集可能な text を維持します。
- PDF page size は、それぞれ 518.4 × 608.4 pt と 518.4 × 244.8 pt です。
- Export 後、main と supplementary の PNG を元の解像度で検査しました。Panel label、task label、method label、confidence interval、legend、color bar、footnote は、重なりや clipping なく確認できます。
- Main SVG は 151 個の `<text>` node、supplementary SVG は 44 個を含みます。PDF inspection では、Arial TrueType/CIDFontType2 font の埋め込みを確認しています。
- 白い背景、抑制された非 rainbow palette、marker shape により、色だけに依存せず解釈できます。

## Figure に反映された統計上・reviewer 向けの caveat

- 99.5% は calibration-fold target であり、仮定された evaluation specificity ではありません。実際の evaluation specificity を明示します。
- H2/end-to-end interval は、白抜き marker で表示し、conditional/resolution-limited と表示します。一つの negative source/fold に独立 component が一つしかないためです。
- Low-query-coverage panel は記述的であり、global evolutionary-distance analysis や matched-specificity superiority test ではありません。
- Benchmark は引き続き内部かつ Train-only です。Validation/Test prediction count はゼロです。

## Image-integrity statement

Microscopy、photograph、gel、その他の raster observation は使用しません。Raster file は vector/data graphic を 600 dpi で直接 render したものです。局所的な contrast adjustment、selective masking、compositing、image reuse は行っていません。
