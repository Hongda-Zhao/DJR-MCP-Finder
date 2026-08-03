<!-- i18n-mirror: non-authoritative translation; source=docs/VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_HEAD_FOCUS_FIGURE_CONTRACT.md -->

> **Translation note:** This translation is for reading only; the frozen Chinese source is authoritative.

# Schema-5 Head-focus figure contract

Status: figure contract; does not change models, thresholds, candidate order, or robustness values.
Backend: Python/matplotlib only.
Target size: 183 mm double-column width; SVG/PDF editable text, PNG 300 dpi, TIFF 600 dpi.

## Core conclusion

Differences among the eight homogeneous models are concentrated mainly in H1 for cellular DJR and
H3 for viral data. The mixed system `H1/H2=ESM-2 3B + H3=ESM-C 6B` is first selected by shared
Train-only five-fold CV and then undergoes an auxiliary post-selection check using same-cluster
near relatives from four sources; robustness does not participate in reranking.

## Archetype and evidence hierarchy

- archetype: quantitative grid + explanatory decision strip;
- hero evidence: the 56 valid model/source endpoints for individual Heads;
- validation evidence: 8×4 whole-cascade expected-path accuracy;
- decision explanation: 3×3 Train-CV recipe table → fixed Head assignments → nominee four-source check;
- boundary: Validation-family diagnostic, Test accessed=0, V0 unchanged, external confirmation required.

## Panel map

### a — Head-by-head robustness

- 8 homogeneous models in the same fixed row order;
- H1: viral/cellular positive sensitivity and background/HardNeg negative specificity;
- H2: viral positive sensitivity and cellular negative specificity;
- H3: viral expected-label accuracy;
- points are equal block→cluster→member member estimates; lines are 95% dependence-block bootstrap CIs;
- 8×(4+2+1)=56 rows in total, without adding duplicated component results from the 9 mixed systems;
- orange indicates only the components selected by Train-CV: ESM-2 3B for H1/H2 and ESM-C 6B for H3; it does not indicate a robustness winner.

### b — Whole-cascade robustness

- expected-path accuracy for 8 models × 4 sources;
- an input is scored 1 only when every applicable Head for that source is correct;
- each cell shows the point estimate and 95% CI; the orange line shows the all-members-correct cluster proportion;
- the four sources are not merged into a total score.

### c — Choose, assign, then check

1. Train-CV `S ± fold SE` recipe table for `3 H1/H2 encoders × 3 H3 encoders`;
2. show the frozen assignment: ESM-2 3B handles H1/H2 and ESM-C 6B handles H3;
3. show the nominee's four-source expected-path CIs and warning count relative to all-6B.

The formula is fixed as:

```text
S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 known macro-F1
```

Panel c must state directly: Train-CV is the selection evidence; four-source robustness is a
post-selection check and does not rerank candidates.

## Data and statistics contract

- result input: schema-5 Amendment D compact result, with all directory `CHECKSUMS.sha256` checks passing;
- benchmark input: metric-revision-1 comparison, with the comparison manifest verified;
- CI: 10,000 fixed-seed dependence-block bootstrap replicates;
- weighting: equal dependence block → source cluster → member;
- no exclusions: all 56 head rows, 32 path rows, 9 candidate rows, and 4 nominee diagnostic rows enter Source Data;
- H1/H2 robustness sensitivity/specificity must not be described as AP;
- H3 robustness expected-label accuracy must not be described as Train-CV macro-F1;
- N/A Heads do not generate a row and are not represented by 0;
- do not generate averages across sources or Heads.

## Reviewer risks and safeguards

1. The family-neighbour H3 expected-label point estimate for ESM3-open 1.4B can be higher than that
   for ESM-C 6B. The figure must note that this is a post-selection diagnostic on a different
   cohort/endpoint and cannot overturn the Train-CV ranking.
2. The H2 cellular value of 1.000 is the ceiling of the current cohort and must not be described as
   universally perfect.
3. The 13,054 member relations and similar quantities are not independent replicates; the CI's
   inferential unit is the dependence block, with nested weighting by cluster/member.
4. H3 expected-label accuracy is not general unknown detection; the rare reject cases with n=7 and
   n=1 remain governed by the original H3 boundary panel.
5. `0/4 warnings` means that source-specific inferiority was not established after Holm correction;
   it does not mean statistical equivalence.
