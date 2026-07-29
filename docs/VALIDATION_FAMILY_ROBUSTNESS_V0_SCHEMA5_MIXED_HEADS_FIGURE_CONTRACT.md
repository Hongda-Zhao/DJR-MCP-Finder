# Figure contract — schema-5 eight-model / mixed-head robustness (Amendment D)

## Core conclusion

Across the same four source-specific Validation-family cohorts, the eight
eligible frozen PLMs can be compared fairly, while a predeclared two-encoder
cascade may be nominated from Train-only CV and compute cost without treating
these related Validation members as an independent Test.

## Evidence and interpretation boundary

- Primary nomination evidence: frozen shared five-fold Train-only
  `S = 0.60 H1 AP + 0.30 H2 AP + 0.10 H3 known macro-F1`.
- Auxiliary evidence: equal-block→cluster→member four-source robustness and
  strict all-members-correct cluster fractions.
- No source averaging; viral, cellular, background, and matched HardNeg remain
  separate columns.
- H3 known-class F1 and reject recall are separate.  The H3 boundary has four
  primary display rows: Nucleocytoviricota F1, Preplasmiviricota F1,
  Produgelaviricota reject recall, and literature-unclassified reject recall.
  The two reject groups are never combined into a primary pooled endpoint.
- The Produgelaviricota row prints `7 relations / 2 parents / 2 blocks` and its
  raw member `k/n`; the literature-unclassified row prints `1 / 1 / 1` and its
  raw member `k/n`.  The single-record row is point-only and has no bootstrap
  confidence interval.
- The pre-existing pooled `8 relations / 3 parents / 3 blocks` endpoint and
  the separate frozen representative benchmark (`n=5`) remain in Source Data
  and QA/caption material only.  Neither appears as a fifth primary H3 row or
  as a paired improvement claim on the main canvas.
- `N/A`, `not estimable`, and numeric zero use different marks.
- The chosen route is labelled `recommended for external confirmation`, not
  independently validated or production-superior.

## Figure archetype and backend

- Archetype: quantitative comparison grid with one decision/Pareto panel.
- Backend: Python/matplotlib only.
- Main target: 183 mm wide by 225 mm high; minimum final text
  6.5 pt; editable SVG/PDF plus 300-dpi PNG and 600-dpi LZW TIFF.
- Palette: colorblind-safe dark blue/orange/teal with neutral greys; do not use
  a rainbow heat map.

## Panel map

### a — identical evidence and applicable heads

Compact four-row table: legal cluster/member/block counts and head
applicability.  A single non-overlapping `Test accessed = 0` badge preserves
the leakage boundary without repeating a Test column.  Weighting details stay
in the caption/QA.  Purpose: establish that all eight models receive the same
legal evidence and prevent background/HardNeg H2/H3 misreading.

### b — eight homogeneous models

Eight rows by source-specific expected-path columns.  Cell value is the
frozen equal-block→cluster→member estimate with 95% CI; a small adjacent mark
shows strict all-members-correct cluster fraction.  The panel is descriptive
and has no cross-source average or winner highlight.

### c — nine predeclared mixed candidates

Left: all nine fixed candidate IDs with Train-CV `S ± paired fold SE` and
one-SE membership.  Right: only the already-selected Train-CV nominee's four
source-specific expected-path rates with 95% CIs and its warning count versus
all-6B.  The complete nine-candidate × four-source diagnostics and contextual
deltas remain in `panel_c_mixed_candidates.tsv`, but are intentionally not
drawn as a second ranking grid.  Robustness does not reorder the candidates.

### d — operational trade-off

Accuracy/cost Pareto plot with always-on H1/H2 encoder cost on x and
conditional H3 encoder cost shown separately (plus worst-case sum).  No
prevalence-dependent runtime is shown without the assumed route prevalence.

### e — H3 boundary

An independent panel reports exactly four primary H3 rows: the two
known-phylum F1 values and separate Produgelaviricota and
literature-unclassified reject recalls.  Known-class rows print truth and
evaluation support; reject rows print raw member `k/n`, parent count, and block
count.  Pooled rare recall, the separate `4/5` representative benchmark, and
the long interpretation note stay in caption/QA and Source Data, outside the
main plot.  Reject means avoiding forced assignment to the two known phyla,
not general unknown-virus detection.

## Reviewer-risk map

1. Selection leakage: same Validation families cannot both tune and confirm;
   show Train-CV nomination and external-confirmation label on the figure.
2. Pseudoreplication: show block count and equal block→cluster→member
   bootstrap; never use naive sequence-level CI.
3. Source imbalance: prohibit a four-source mean.
4. H3 overclaim: split Produgelaviricota from literature-unclassified, print
   raw `k/n` and hierarchical support, suppress the single-block CI, keep the
   pooled value outside the main canvas, and keep reject recall apart from
   known macro-F1.
5. Multiple comparisons: only eight nontrivial candidates versus all-6B enter
   the Holm family; all-6B self-delta is zero, not a test.
6. Cost overclaim: separate always-on and conditional encoder costs and state
   that timings are workstation/environment specific.

## Required source-data tables

- `materialization_summary.tsv` plus schema-4 `coverage_summary.tsv` continuity
- `legacy_numerical_operator_runtime.json` plus
  `schema4_recomputation_audit_summary.tsv` (four-thread exact replay gate;
  Amendment-B tolerances are diagnostic upper bounds only)
- `source_path_summary.tsv`
- `strict_cluster_summary.tsv`
- `train_cv_candidate_summary.tsv`
- `pairwise_source_path_delta.tsv`
- `accuracy_cost_pareto.tsv`
- `candidate_nomination.tsv`
- `h3_class_summary.tsv`
- `model_cost_registry.tsv`

Every plotted value must be recoverable from exported panel source-data TSVs;
the plotting script must verify the result `CHECKSUMS.sha256` before reading.
`source_data/panel_d_h3_boundary.tsv` retains its stable artifact name and
contains the four panel-e primary rows plus the two explicitly secondary rows,
with endpoint role, truth/evaluation
support, parent/block support, member and representative raw `k/n`, value, and
confidence-interval fields.
