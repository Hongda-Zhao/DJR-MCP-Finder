<!-- i18n-mirror: non-authoritative translation; source=results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/FIGURE_GUIDE.md -->

> This translation is provided for reading only; the frozen Chinese source document is the authoritative version.

# How to read the figure

## a: Inspect each Head separately

Each point is the correct-decision rate for one model on one valid source, and the horizontal line is the 95% CI; farther to the right is better. H1 has four valid sources, H2 has two, and H3 has only viral. Orange only marks the component already selected by Train-CV; it does not indicate that this figure is used to select the model again.

## b: Inspect the complete tool path

An input is counted as having a correct expected path only when every Head that should run for that source answers correctly. Each cell contains the point estimate and 95% CI; the orange line is the cluster proportion for which “all relatives in the entire cluster are correct.”

## c: Read in the order 1 → 2 → 3

1. Compare the 3×3 recipes using five-fold CV on Train only; each cell is S ± fold SE.
2. The highest-scoring preregistered recipe assigns H1/H2 to ESM-2 3B and H3 to ESM-C 6B.
3. Only after selection are same-cluster relatives from four sources checked; a 0/4 warning means only that no source-specific disadvantage relative to all-6B was established, and does not demonstrate equivalence.

Important boundary: robustness did not participate in candidate ranking; Test accessed=0; frozen V0 did not change and still requires external/prospective confirmation. ESM3-open 1.4B has a higher point estimate for H3 family-neighbour expected-label accuracy in this analysis, but this is not Train-CV known macro-F1 and does not belong to the same evidence layer, so it cannot be used for post-hoc reranking.
