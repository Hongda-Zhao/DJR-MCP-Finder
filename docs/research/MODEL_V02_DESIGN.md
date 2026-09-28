# Model V0.2 design proposal based on V0.1 Candidate

**English** | [简体中文](MODEL_V02_DESIGN.cn.md) | [日本語](MODEL_V02_DESIGN.ja.md)

Status: **length-policy preview implemented, 2026-09-28**. V0.2 model training is deferred. No new scientific weights, calibration, release or measured accuracy improvement exist.

## Implemented V0.2 policy preview: length guard

The current deliverable adds a conservative **abstention policy** to frozen V0.1.
It is not a trained scientific Model V0.2 or evidence of improved accuracy.

| Normalized input length | Action | `final_prediction` |
|---|---|---|
| <250 aa | Skip all encoders and classification heads | `mcp_unreliable_short_sequence` |
| ≥250 aa, including exactly 250 | Use unchanged V0.1 inference | Existing five model labels |

The short-input display label is **MCP unreliable: sequence shorter than 250 aa**.
It means insufficient evidence to evaluate MCP status, neither MCP-positive nor
non-MCP. Status is `not_evaluated_short_sequence`, scores are `NA`, heads are
`not_reached`, `head3_reached=0`, and warnings include `length_below_250_aa`.
FASTA whitespace is removed and lowercase converted to uppercase; X counts as
one residue. The entire FASTA is validated first; invalid short sequences still
raise an error. Mixed inputs retain every record, original header and input order.

The 250 aa boundary is a **user-selected deployment policy**, not an established
biological minimum or a guarantee of accuracy above it. Metadata-only inspection
found 560 curated MCP positives (336 Train, 112 Validation, 112 Test), none below
250 aa. Train has 13 positives at 250–299 aa; all 560 have 22 in that bin. This
supports identifying an evidence gap, not calling every short sequence false.

Use the new entry point after installing this checkout, or invoke the module:

```bash
PYTHONPATH=user-inference-v0.1/src python -m djrmcp_predict_v01.v02_preview predict \
  proteins.faa --outdir results/v02-preview --device cpu
# Installed equivalent: djrmcp-predict-v02-preview predict proteins.faa --outdir results/v02-preview
```

All-short inputs require no PLM checkpoint, model worker or GPU. Eligible inputs
use the existing V0.1 encoder environments and cache options. Existing Docker
wrappers still select V0.1; invoke the preview explicitly in a rebuilt environment.
The output remains `predictions.tsv`, `run_metadata.json`, and `CHECKSUMS.sha256`.
The TSV keeps its columns but adds an abstention value; downstream label readers
must accept it. Metadata uses `schema_name=djrmcp_v02_policy_preview` and records
the policy, coverage, abstention count and nested eligible-subset baseline run.
The V0.1 command and frozen weights are unchanged. No release is published.

For evaluation, preserve the existing unfiltered V0/V0.1 diagnostic benchmark.
A policy evaluation must separately report scoring coverage and abstentions per
length bin (<250, 250–299, 300–349, 350–399, 400–449, 450–499, ≥500 aa). Below
250, conditional recall/FPR are **not estimable** because no prediction is made;
abstentions are never true negatives. For end-to-end detection recall, all true
positives remain in the denominator and positive abstentions count as undetected.
Report metrics on scored inputs with their denominators and full-cohort detection
recall separately. The current figures describe V0.1 cross-fit diagnostics, not
V0.2 policy performance.

The following training proposal is future research only. Its <250 aa improvement
criteria evaluate a future model without this guard, to determine whether a
separately validated policy could eventually relax it. They are not claims or
acceptance conditions for the current abstaining pipeline.

## Objective and baseline

Improve detection of short MCP-derived protein fragments while controlling
false positives and preserving full-length performance. The scientific baseline
is **Model V0.1 Candidate**, not Model V0. The V0 arm in the
[short-sequence benchmark](../../benchmarks/short_sequence_v1/README.md) is a
historical reference. First measure V0.1; the results may show that no model
change is needed in some length ranges.

| Component | V0.1 Candidate | First proposed V0.2 candidate |
|---|---|---|
| H1/H2 encoder | Pinned ESM-2 3B | Keep checkpoint, pooling, precision and long-sequence window policy |
| H1 DJR classifier | Full-protein training | Evaluate parent-balanced full + fragment training |
| H2 MCP classifier | Full DJR-protein training | Evaluate matched positive/negative fragment training |
| H3 phylum encoder/head | ESM-C 6B, reused from V0 | Keep initially, to isolate H1/H2 changes |
| Thresholds | Frozen V0.1 calibration | New candidate-specific calibration, frozen before evaluation |
| Output | Existing five labels and scores | Policy preview adds short-input abstention; scored inputs retain existing labels |

## Proposed training experiment — not implemented or run

1. Keep the frozen outer component folds. Generate augmentation **only inside
   fit components**. A parent, its homologous component, and all fragments stay
   together. Calibration and evaluation proteins never enter classifier fitting.
2. Retain full inputs. Initially evaluate 130, 150, 200, 250 and 300 aa training
   fragments, with terminal and internal views. Keep 50/100 aa as stress-test
   conditions until evidence supports training on them. Do not invent a complete
   fold/function label for a fragment; labels denote the parent protein's origin.
3. Give every parent equal total weight. The initial candidate allocates half of
   its weight to the full protein and half to its available fragment lengths,
   then divides fragment weight equally by length and available position. If a
   parent has no eligible fragment, its full sequence receives all weight.
   Preserve H1 class/source balancing and H2 class balancing **after** parent
   weighting; duplicating negatives or long proteins must not change these priors.
4. Keep the existing classifier families and hyperparameters in the first
   ablation. Fit scaling statistics only inside the fit partition. Encoder
   fine-tuning, a separate short-protein encoder, and length-specific classifiers
   are outside the first experiment.
5. Compare a full-only control against full + fragment training. Initially retain
   full-protein-only threshold calibration, as in the benchmark, to isolate the
   effect of training. A second, separately registered experiment may add
   parent-weighted calibration fragments. Do not silently change both training
   and thresholds in one unlabeled comparison.
6. Keep H3 fixed in deployment-oriented experiments. In cross-fit experiments,
   fit H3 once on the allowed full-protein fit components and share that exact
   fold head between the V0.1 control and V0.2 candidate. Monitor H3 end-to-end
   recall because improved H1/H2 recall can expose H3 to harder fragments.

## Development and confirmation

The current benchmark implements V0/V0.1 refits only. It does **not** implement a
V0.2 training adapter. Extending it must add explicit method identities, fit
manifests, per-parent weights and augmentation checksums before any V0.2 run.

Use nested component splits within the outer fit portion if selecting
augmentation weights, hyperparameters or length policies. Calibration controls
thresholds; the outer evaluation fold never chooses a setting. The existing
development data and baseline results have already been inspected, so even a
careful cross-fit comparison remains an internal development result.

A release-level improvement requires a new, method-independent external
lockbox: trusted MCPs, cellular DJR, difficult non-DJR and background proteins,
including independently labeled real short proteins. Freeze parent-level
overlap screening, sequence/label hashes, source mixture, evaluation endpoints
and the one-time comparison before scoring. Synthetic truncations and real
short-protein results must remain separate. Do not automatically reopen the
project's protected historical Test partition.

## Proposed acceptance criteria

These are **design targets to preregister before V0.2 results**, not passed
criteria. Use paired component-bootstrap uncertainty and disclose support.

- Primary benefit: positive lower 95% CI for the equal-weight mean MCP recall
  difference (V0.2 minus V0.1) across 130, 150 and 200 aa. All three lengths must
  have adequate independent support; do not replace the endpoint with the
  best-performing length after scoring.
- Short-fragment specificity: at each primary length, the upper 95% CI of the
  pooled MCP FPR is <=1%, and the upper CI of the paired FPR increase is <=0.5
  percentage points. Also report each negative source separately; pooled
  success cannot hide an unreviewed source-specific failure.
- Full-length guardrail: the lower CI of the MCP recall difference is >=-1
  percentage point; the upper CI of the FPR increase is <=0.5 percentage points.
- Phylum guardrail: report both known phyla and upstream gate losses separately.
  The lower CI of the full-length H3 end-to-end recall difference should be
  >=-1 percentage point for each phylum.
- Missing or insufficient support, unstable estimates, and degenerate zero-error
  bootstrap intervals cannot establish a gate. Add independent samples or use a
  preregistered boundary-valid interval; do not label the current bootstrap's
  zero-width interval as proof that the population FPR is zero.

The current benchmark reports per-length rates and paired differences. The
three-length composite, candidate training and formal acceptance decision are
future work. Failing a gate leaves V0.1 as the baseline; no version promotion
occurs automatically.

## Software and delivery plan

After scientific confirmation, export a separate checksum-bound candidate
bundle with its training-data identity, augmentation policy, encoder revisions,
head weights, temperatures, thresholds and tested length range. Preserve V0.1
as a selectable baseline and add parity tests between offline evaluation and
packaged inference, including short inputs and gate failures.

The implemented policy is specified above. Preserve model-score semantics and do
not infer biological completeness from length alone. Future research may support
a separately versioned relaxation of the deployment guard.

Only then assign a scientific candidate identity and update the model card,
bundle and [version mapping](../VERSIONING.md). The existing inference package
version `0.2.1` is an engineering version, not scientific Model V0.2. This design
does not change `release-manifest.json` or existing package versions.

The observed-length benchmark is now complete using historical embeddings on CPU.
It contains no MCP positives below 250 aa; the 250–299 aa group has only 13.
This evidence gap strengthens the need for the paired truncation benchmark and
independent short-positive confirmation before claiming a validated usable length range. The 250 aa guard is an operational choice.
New-fragment GPU encoding and V0.2 model training remain separate steps; V0.2
training has not been performed.
