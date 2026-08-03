<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/figures/QA_REPORT.md -->

この翻訳は閲覧の便宜のみを目的としています。凍結された英語の原文が正式な文書です。

# Figure QA report

- 核心結論と panel hierarchy は `FIGURE_CONTRACT.md` に一致します。
- Backend：Python/matplotlib のみ。正確な version は `visualization_manifest.json` に記録されます。
- Static source preflight：14 PASS、0 WARN、0 FAIL。
- Visual inspection：二回の layout revision 後に final-size PNG を検査しました。title、legend、
  axis-label、panel-label、footer の重なりはなく、crop された mark もありません。
- 最終 width：180.1 mm。宣言された最小 text size：5.1 pt。
- Compact export：editable-text SVG、TrueType-text PDF、300-dpi PNG preview。600-dpi TIFF は
  完全 archive 内で引き続き checksum-bound です。
- Data integrity：observation の sampling や削除はありません。panel b/c の method subset は
  legibility のため事前に宣言されています。完全な method table は `results/` にあります。
- Statistics：paired interval は独立 evaluation component を resample し、threshold は
  calibration から固定します。calibration uncertainty を除外し、そのことを明記しています。
- Specificity：いずれかの system が少なくとも一つの fold で実際の 99.5% specificity を満たさない
  pair は、空心 marker によって明示的に downgrade します。
- Low-FPR resolution：source ごとの independent-negative resolution が FPR 0.005 で不十分なため、
  H2 と end-to-end pAUROC は interpolate せず suppress します。
- Sample-size gate：strict qcov >=80%、identity <20% は n=1 component のみであり、証拠不足と
  表示します。CI または superiority annotation はありません。
- Source data とすべての export は、`visualization_manifest.json` と benchmark-level
  `CHECKSUMS.sha256` で SHA-256 bound です。
