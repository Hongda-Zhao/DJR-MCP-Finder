<!-- i18n-mirror: non-authoritative translation; source=results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/FIGURE_GUIDE.md -->

> この翻訳は閲覧用です。固定された中国語の原文が正式かつ権威ある版です。

# Figure の読み方

## a：Head ごとに確認する

各点は、一つの model が一つの valid source で示した correct-decision rate です。横線は 95% CI で、右にあるほど良いことを示します。H1 には valid source が四つ、H2 には二つあり、H3 は viral だけです。オレンジ色は Train-CV ですでに選択済みの component を示すだけで、この figure を使って model を再選択することを意味しません。

## b：Tool path 全体を確認する

その source で実行すべきすべての Head が正しく回答した場合に限り、input の expected path が正しいと数えます。各 cell は point estimate と 95% CI を示します。オレンジ線は、「cluster 全体の近縁すべてが正しい」cluster の割合です。

## c：1 → 2 → 3 の順で読む

1. Train だけを使う five-fold CV で 3×3 recipe を比較します。各 cell は S ± fold SE です。
2. 最高値の事前登録済み recipe は、H1/H2 を ESM-2 3B、H3 を ESM-C 6B に割り当てます。
3. 選択後に初めて、四つの source に属する同一 cluster の近縁を確認します。0/4 warning は、all-6B に対する source-specific disadvantage が確立されなかったことだけを示し、equivalence は証明しません。

重要な境界：robustness は candidate ranking に関与していません。Test accessed=0。固定 V0 は変更されておらず、外部／前向きの確認が引き続き必要です。ESM3-open 1.4B は、この H3 family-neighbour expected-label accuracy では point estimate が高いものの、これは Train-CV known macro-F1 ではなく、同じ evidence layer にも属さないため、post-hoc reranking には使用できません。
