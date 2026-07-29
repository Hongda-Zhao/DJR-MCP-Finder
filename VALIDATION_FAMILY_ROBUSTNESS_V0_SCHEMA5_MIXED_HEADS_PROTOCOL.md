# Project V0 eight-model / mixed-head Validation-family robustness protocol

Status: schema 5, frozen analysis plan, auxiliary development evidence.  It
does not replace schema 4, alter the released V0 model, or constitute an
independent Test evaluation.

Analysis ID: `project_v0_validation_family_robustness_schema5_mixed_heads`.

## 0. Pre-scoring amendment A

An independent contract audit was completed after label-free embedding
materialization had started but before any schema-5 prediction, endpoint,
bootstrap result, or model comparison existed.  Amendment A corrects the
matched-family rare-H3 denominator (8 member relations / 3 parents, distinct
from the 5 representative-level benchmark records), requires six explicit
reuse attestations, strengthens resume-receipt validation, and checksum-binds
the schema-4 continuity validator/result manifest.  The eight models, nine
mixed candidates, input bytes, frozen heads/thresholds, CV nomination rule,
bootstrap seed, and Test=0 boundary are unchanged.  The original
materialization protocol/config snapshots (SHA256 `81aedf...881b6f` and
`441990...adb94`) remain archived; amended scoring re-attests their embedding
outputs rather than recomputing representations whose numerical contract did
not change.

## 0b. Post-failure operational amendment B

The first CPU scoring attempt stopped fail-closed at the schema-4 continuity
gate, before a stable result directory, endpoint, bootstrap result, validation
report, figure, or candidate interpretation was created.  A separate read-only
diagnostic then compared all 92,844 schema-4 prediction keys with fresh
schema-5 inference.  Source, cluster, dependence-block, Train-relationship,
eligibility, Test, truth, label, prediction, reject decision, and correctness
fields were identical; Test remained zero and every frozen threshold was
serialized exactly.  At that time the nonexact values were attributed to a
different BLAS batch shape: member probabilities 114 rows (maximum absolute
difference `3.353e-7`), representative probabilities 684 (`2.305e-7`), member
raw scores 112 (maximum absolute `0.03125`), and representative raw scores 684
(maximum absolute `0.0234375`).  The reported raw relative values
`4.795e-7`/`3.590e-7` belonged to the maximum-*absolute*-difference rows; they
were not global maximum-relative values.  Amendment C below supersedes both
that causal attribution and those mislabeled extrema.  This paragraph is
retained only as the contemporaneous rationale for the already frozen
Amendment-B upper bounds.

Amendment B therefore freezes a numerical compatibility policy before any
formal schema-5 result exists.  Fresh inference must still be completed for
all 92,844 rows and must pass, row by row,

```text
probability:       abs(new-old) <= 5e-7 + 1e-6 * abs(old)
raw decision score: abs(new-old) <= 1e-5 + 1e-6 * abs(old)
threshold:         exact serialized equality
```

No model-specific or data-adaptive enlargement is permitted.  Both values and
deltas for every row are retained in a checksum-bound audit table.  The
independent validator recomputes the inequalities and derives binary calls,
H3 reject status, and correctness from those values.  Only after all keys,
semantic fields, blank patterns, finite/range checks, exact thresholds, and
derived decisions pass is the substitution performed all-or-none: the exact
checksum-bound schema-4 serialized rows for ESM-2 650M and ESM-C 6B become the
canonical prediction cache in schema 5, and mixed heads are composed from
those canonical rows.  This removes platform-dependent last-bit drift without
changing embeddings, heads, thresholds, endpoints, candidate ordering, or any
released-V0 artifact.

## 0c. Legacy numerical-operator correction amendment C

Amendment B's scientific boundary was fail-closed, but its numerical diagnosis
was incomplete.  Schema-4 job `4968695` used four BLAS threads.  That job had
overall exit status 1 in a later step; it must not be described as a successful
job.  Its prediction generation and independent prediction validation had
already completed, however, and those checksum-bound `predictions.tsv` bytes
remain the canonical continuity artifact.  The first schema-5 attempt
`4968800` used 12 threads and stopped before metrics at exact continuity.
Diagnostic `4968804`, also with 12 threads, attached a relative difference to
the row with the largest absolute difference; it did not compute the maximum
row-wise relative difference or apply the Amendment-B formula to every row.
Consequently its aggregate was misinterpreted as a global bound.  The HardNeg
full-batch composition was unchanged between the historical and diagnostic
runs.  The reproduced cause was the four-to-twelve-thread change in the
OpenBLAS reduction plan, not a change in batch shape.

No stable schema-5 result, endpoint, bootstrap, validation, figure, or
candidate interpretation existed when the error was found.  Job `4968816`
again stopped before metrics under the Amendment-B raw-score gate.  Corrected
all-row 12-thread diagnostic `4968818` showed 2 member-raw and 9
representative-raw violations while probability and threshold failure counts
were zero.  Its independently used top-level maximum-relative scalars were
member probability `5.836859e-6`, member raw `5.253913e-6`, representative
probability `6.363661e-6`, and representative raw `1.201539e-6`; thresholds
were exact.  The diagnostic's detailed `max_relative_delta_record.ratio`
payload had a display defect (the helper used `limit=1.0`, so that field held
absolute delta).  Amendment C does not reuse that record field: the formal
scorer and validator independently recompute every row-level delta and bound.
This was not new drift.  A pre-result replay hypothesis was then tested using
the historical numerical operator.  Read-only cdb job `4968820` finished with
exit status 0 and compared all 92,844 keys under Python 3.11.7, four requested
CPUs, `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4`,
`OPENBLAS_NUM_THREADS=4`, and `PYTHONHASHSEED=20260724`.  Test count was zero;
all five numeric fields had `nonexact=0` and Amendment-B failures `=0`.
Job `4968820` was an exact-numeric/finite/Test diagnostic only: it did not
audit every semantic field or independently rederive prediction, reject, and
correctness values, and is not described as the formal full audit.

Amendment C therefore corrects the runtime operator rather than changing a
tolerance.  The Amendment-B probability/raw upper bounds and exact-threshold
rule remain frozen and are still recomputed.  Schema-5 additionally requires
exact serialized numeric replay for every one of the 92,844 canonical
ESM-2-650M/ESM-C-6B rows.  The scorer must attest the four-thread runtime and
loaded BLAS thread pools before inference.  To make all pools observable, it
first imports only the declared frozen numerical modules `scipy.linalg` and
`sklearn.linear_model`; this performs no fit, score, or prediction.  It then
attests two BLAS pools plus one OpenMP pool, all at four threads, before any
inference.  Every canonical/recomputed value,
delta, semantic field, blank pattern, finite/range check, Test flag, derived
prediction/reject decision, and correctness value remains checksum-bound.
Any nonexact numeric string fails even when it would fit Amendment B.  Only
after the complete exact audit passes may canonical rows be substituted
all-or-none and used for mixed-head recomposition.

The formal scorer performs the complete key, semantic, blank, finite/range,
derived-decision, Test, exact-string, and retained-upper-bound gate before it
computes any endpoint, bootstrap, or nomination table.  The independent
validator then reconstructs those checks from the checksum-bound row audit and
runtime attestation.  Thus the numeric-only `4968820` evidence motivates the
operator correction but cannot by itself authorize a schema-5 result.

This is an operational replay correction only.  Embeddings, fitted heads,
temperatures, thresholds, Test policy, bootstrap seed, CV score, candidate
grid, robustness endpoints, and released V0 artifacts are unchanged.  No
claim is made that job `4968695` as a whole passed; only its already validated
prediction artifact and its now independently replayed numerical operator are
used.

## 0d. Post-result H3 display-contract amendment D

The Amendment-C formal generation is retained unchanged at `schema5_v1`.
Review of its H3 presentation found that the secondary pooled reject endpoint
(`8` member relations / `3` Validation parents) did not show its two frozen
biological subgroups separately.  Amendment D is a reporting-contract repair,
not a new model analysis.  A new no-overwrite generation is written under
`schema5_v1_amendment_d`.

The scorer joins the already computed per-record H3 predictions to the same
checksum-bound family manifest used by inference.  Its frozen SHA256 is
`8cd9e9ce45ad965eb745cc4ecdf08d7e3205f57b830bca00bcf0041e5bcdf541`;
the scorer and independent validator both require that exact identity before
using `head3_status` or `head3_phylum_label`.  It derives exactly:

- `Produgelaviricota_reject_recall`: `7` relations / `2` parents / `2`
  dependence blocks, equal block→parent→member weighted;
- `literature_unclassified_reject_recall`: `1` relation / `1` parent / `1`
  dependence block, point estimate only, explicitly descriptive with no
  generalization claim; and
- `rare_or_unclassified_reject_recall`: the existing `8` / `3` pooled value,
  retained only as a secondary diagnostic.

Every reject row reports raw member `k/n` and raw unique-parent `k/n` in
addition to the weighted value.  The independent validator reads the frozen
manifest itself, reconstructs the `7+1` join, recomputes support, raw counts,
weighted endpoints and estimable intervals, and requires the exact six-row
H3 endpoint set per system.  For continuity, Produgelaviricota uses the
schema-4 seed offset `6100`, literature-unclassified uses `6110`, and the
existing pooled endpoint retains `6100`; endpoints are not jointly compared.

No subgroup inference is run.  Embeddings, fitted heads, probabilities,
predicted labels, temperatures, thresholds, Train-CV folds and values,
candidate ordering, model-cost evidence, four-source endpoints, Test=0, and
released V0 artifacts remain unchanged.  To make this mechanically
verifiable, the Amendment-D scorer and validator require byte identity to the
retained Amendment-C generation for the single-model predictions, composed
system predictions, expected-path predictions, system registry, Train-CV
candidate table, Pareto table, and nomination table.  Any difference fails
closed before publication.  The retained parent identities are frozen as
`results/CHECKSUMS.sha256 = aa9f3cef647487d4eaec7749ceeb49c58085657a38d0d99c7577f3655448e72c`
and
`validation.json = 2b63cecae7788cce3d4c8ef96d48bf1becfbe8d74b9e9c084b2ab69a47542bcb`;
both are verified before artifact-level comparison.

The byte-equivalence statement is deliberately limited to those seven
declared artifacts.  Four-source summaries, bootstraps, paired diagnostics,
and model-cost rows are instead independently recomputed or rebound to the
same frozen prediction/comparison inputs by the existing validator; Amendment
D makes no separate whole-file byte-identity claim for those derived tables.

## 1. Question and evidence boundary

This analysis asks whether the eight representation models that already
passed the formal 14-model benchmark gates behave consistently on the same
four source-specific Validation-family cohorts, and whether a predeclared
two-encoder cascade is a reasonable candidate for later external
confirmation.

All representation checkpoints, Train-only fitted heads, temperatures,
decision thresholds, H3 reject thresholds, legal cohort exclusions, and
dependence blocks remain frozen.  Schema-5 outputs cannot feed back into
fitting, calibration, threshold tuning, the released V0 tool, or Test.  A
mixed cascade may only be called `recommended_for_external_confirmation`,
never independently validated or production-superior.

Permanent counters:

```text
training_operations=0
calibration_fit_operations=0
threshold_tuning_operations=0
Test vectors selected for inference=0
Test predictions or performance metrics computed=0
released_V0_artifacts_modified=0
```

## 2. Why exactly these eight models

The model set was fixed from the existing, checksum-bound 14-model benchmark
before schema-5 inference:

`esm2_650m`, `esm2_3b`, `esmc_300m`, `esmc_600m`, `esmc_6b`, `prott5_xl`,
`prostt5`, and `esm3_open_1_4b`.

The other six benchmark models remain visible in the 14-model development
figure but do not enter this expensive robustness extension because they did
not pass the predeclared primary-candidate boundary.  Schema-5 results may not
add or remove models retrospectively.

## 3. Identical four-source inputs for all eight models

Every model receives byte-identical manifests and FASTA inputs:

| shard | raw embedded records | legal scored records | role |
| --- | ---: | ---: | --- |
| viral family | 13,074 | H1/H2 13,054; H3 13,052 | matched viral sensitivity and path |
| graph family: cellular | 391 | 391 | matched cellular H1/H2 path |
| graph family: background | 3,000 | 3,000 | matched H1 specificity |
| matched HardNeg | 3,478 | 3,478 | matched H1 specificity |

The 13,074 viral rows are the historic raw embedding input.  The already
frozen integrity logic excludes 20 cross-split exact-sequence conflicts from
H1/H2 scoring and two additional inherited-phylum conflicts from H3.  The
same exclusions are applied to all models.  Embedding one unique sequence
once does not make related member-parent rows independent; inference is
expanded back to the legal relations and uncertainty is resampled by the
frozen dependence blocks.

Input identities:

| shard | manifest SHA256 | FASTA SHA256 |
| --- | --- | --- |
| viral family | `d96ab256de26414706c9d4993f1d9e2d64adaea8cece32645bb16a2b18b7e6f3` | `9650b5703ce413ca438c9cb84740aa8bd4e14be6a1f183027419fdc9fefe6b7d` |
| graph family | `25f0ceaed999cc62ee933d6258c88bfcbad4ff4596900099ae0e8a046b10d33b` | `1e7478a7eedaee0d14952018797d18637cf1c316a6d0781dc179a32cfc50bee0` |
| matched HardNeg | `ec55863a86014952d107e870bffe428adcf5ea4f6fb800520fc4e957479b41c4` | `f274b6ac9ea5df52f6dcbe4428e22454649aecd93131f0eee7826087d6eaaf66` |

## 4. Homogeneous and mixed candidates

First, each of the eight models supplies H1, H2 and H3 wherever the source
supports that head.  These homogeneous runs diagnose representation-specific
failure and are not averaged into one four-source score.

Primary mixed-head search is restricted to nine predeclared cascades:

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

H1 and H2 must share one encoder because H2 is already saturated and a third
always-on encoder is operationally unjustified.  A different H3 encoder is
invoked only after the H1→H2 route reaches viral VMA-DJR.  No data-dependent
addition from the remaining `8^3` combinations is permitted in the primary
result.

## 5. Endpoints

Sources are reported separately:

- viral: H1 sensitivity, H2 conditional sensitivity, H1→H2 path recall,
  H3 known two-phylum macro-F1, the two known-phylum F1 values,
  Produgelaviricota reject recall, literature-unclassified reject recall, and
  the pooled reject recall only as a secondary small-sample diagnostic;
- cellular: H1 sensitivity, H2 specificity, and H1→H2 non-MCP path-correct
  recall;
- background and matched HardNeg: H1 specificity/FPR only;
- every applicable source: member-level rate and `all legal members correct`
  source-cluster fraction.

H3 `unknown` is reject behavior, not universal unknown-virus detection.  The
formal representative-level benchmark has five rare Validation records.  The
matched-family robustness shard contains eight legal rare member relations
from three Validation parents (Produgelaviricota 7 plus
literature-unclassified 1).  The two subgroup denominators and their raw
member/parent `k/n` must be shown separately.  The one literature-unclassified
record is descriptive only and cannot support generalization.  The `8/3`
pooled value is secondary; none of these reject endpoints enters the
known-phylum macro-F1.  H2/H3 on background or HardNeg are `N/A`, not zero.

## 6. Uncertainty and comparisons

Use 10,000 deterministic nested bootstrap replicates with seed `20260728`.
The outer unit is the frozen shared-SHA/original-component dependence block;
members remain nested within their source cluster.  Model and mixed-cascade
deltas use the same bootstrap draws.  Ninety-five-percent percentile
intervals are reported.  The eight nontrivial primary mixed candidates are
compared with the frozen all-ESM-C-6B cascade using family-wise Holm
correction; the ninth candidate is the all-6B self-reference and has delta
zero, not a hypothesis test.  Contextual paired deltas versus all-ESM-2-650M
are also reported for the cellular/background/HardNeg strengths but cannot
rerank candidates.  Unadjusted exploratory claims are forbidden.  The frozen
equal-block→cluster→member estimate and the strict all-members-correct cluster
fraction must both be shown because they answer different questions.

## 7. Candidate nomination rule

Robustness is not optimized.  The candidate order is determined first from
the existing Train-only five-fold values

`S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 known macro-F1`.

For a mixed candidate, H1/H2 fold values come from its shared base model and
H3 from its H3 model on the identical frozen folds.  Highest mean `S` is the
accuracy-first nominee.  If candidates are within one paired fold standard
error of that maximum, report the Pareto set and prefer, in order, lower
always-on base-encoder GPU seconds per sequence, lower worst-case two-encoder
GPU seconds, lower peak GPU memory, then the frozen lexical candidate ID.

Schema-5 robustness cannot reorder this Train-CV nomination.  It supplies a
source-specific warning when the Holm-adjusted paired interval establishes a
degradation versus all-ESM-C-6B; such a warning must accompany the nominee
and blocks any production replacement until a source-component-disjoint or
prospective external set confirms it.

Cost is reported as two terms—always-on H1/H2 encoder plus conditional H3
encoder—and as worst-case sum.  A single prevalence-dependent runtime is not
claimed without stating the assumed route prevalence.

## 8. Completion and fail-closed rules

Completion requires 24 checksum-valid embedding bundles (eight models by
three shards), 18 new-materialization receipts plus six schema-5 reuse
attestations for the existing 650M/6B bundles, all with Test count zero, exact
frozen head/temperature/threshold hashes, the complete eight homogeneous and
nine primary mixed result tables, independently recomputed endpoints, and a
validator report with `status=PASS`.  The 18 raw workstation receipts retain
their original `/lab/...` paths and bytes.  A separate 24-row normalized
attestation layer binds each source receipt SHA to the byte-identical gds2
bundle and its `/aptmp/...` registry path; raw receipts are never rewritten.
Missing, mismatched, partial, or non-finite evidence is retained as a failed
generation and is never silently substituted.  Schema 4 remains unchanged
whatever schema 5 reports.

For the two schema-4 models, completion additionally requires the Amendment-C
runtime attestation and 92,844-row recomputation audit, exact serialized
equality for all five numeric fields, exact checksum continuity of the
canonical schema-4 `predictions.tsv` rows in both homogeneous and mixed-head
tables, and an independent validation gate confirming exact replay, retained
Amendment-B upper bounds, and all-or-none canonicalization.  A missing audit
row or any nonexact numeric string, out-of-bound, semantic, blank, range,
threshold, derived-decision, runtime-lineage, or Test mismatch fails closed.

Amendment-D completion additionally requires exactly 102 H3 rows (six
endpoints for each of 17 system labels), including 34 subgroup rows, the exact
`7/2/2` and `1/1/1` supports, raw member and unique-parent reject `k/n`, a
point-only literature-unclassified row, independent manifest-join
reconstruction, and byte identity of all seven declared Amendment-C
prediction/threshold/CV/order artifacts.  The retained Amendment-C generation
is never overwritten or migrated in place.

The cdb launcher executes the fixed order below and refuses to overwrite any
stable result or validation target:

```text
6 checksum-only reuse attestations (if absent)
18 raw + 6 reuse -> 24 normalized path attestations (if absent)
schema-5 scorer -> atomic results/
independent recomputation -> atomic validation.json
```

GPU representation materialization is already complete on the workstation;
the scoring/validation stage is CPU-only and must not use APG.
