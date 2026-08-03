<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/figures/FIGURE_CONTRACT.md -->

この翻訳は閲覧の便宜のみを目的としています。凍結された英語の原文が正式な文書です。

# Figure contract

核心結論：v0.1 encoder の変更は、component-held-out protein および BLAST-defined difficult
protein で推定できます。しかし、現在の厳密な <20% identity cohort は小さすぎるため、
ultra-remote superiority claim を支持できません。

- Figure archetype：paired-delta panel を中心とする quantitative grid。
- Target/output：manuscript/report figure；編集可能な SVG と PDF、600-dpi TIFF、preview PNG。
- Backend：Python（matplotlib のみ）。
- 最終 size：幅 180 mm、高さ約 145 mm。
- Panel a：すべての holdout、20–30% identity twilight layer、low-coverage stress における、
  paired v0.1 minus v0 sensitivity delta と 95% descriptive bootstrap CI。
- Panel b：low-coverage stress stratum における、選択した PLM と classical method の absolute
  sensitivity。calibration-fold-locked threshold を使用します。
- Panel c：すべての component-held-out row における FPR <=0.005 の normalized partial AUROC。
  十分な per-source negative-component resolution がない endpoint は省略します。
- Panel d：independent-component count と、事前に凍結された adequacy threshold の比較。
- Statistics：total n >=30 かつ各 fold n >=5 の場合のみ paired component bootstrap を使用します。
  厳密な <20% stratum には CI または superiority inference を付けません。
- Source data：plot するすべての point が `figures/source_data/` に存在する必要があります。
- Reviewer risk：BLAST-derived stratum は method-conditioned です。実際の evaluation specificity
  は 99.5% target を満たさない可能性があります。H2 には negative component が一つしかない
  evaluation fold があります。現在の benchmark は Train-only development evidence です。空心の
  symbol は、いずれかの system が実際の specificity gate を満たさない paired delta を示します。
  fixed-threshold bootstrap interval は calibration uncertainty を含みません。
