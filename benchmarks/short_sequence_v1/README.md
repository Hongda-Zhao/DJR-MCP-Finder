# Short-sequence benchmark v1

**English** | [简体中文](README.cn.md) | [日本語](README.ja.md)

This benchmark measures how DJR-MCP detection changes when a labeled protein is
replaced by a contiguous short fragment. It compares the V0 and V0.1 Candidate
encoder/classifier recipes under **Train-only component-disjoint cross-fitting**.
It does not use application candidates as ground truth.

V0.1 Candidate is the primary baseline for the
[V0.2 design proposal](../../docs/research/MODEL_V02_DESIGN.md); V0 is retained as
a historical comparator. V0.2 training is outside this implementation.

**Status (2026-09-28): the observed-length benchmark is complete using historical
embeddings, entirely on CPU. The paired truncation benchmark remains pending.**

## Observed-length results (2026-09-28)

Both frozen encoders reused all 6,634 Train vectors (13,268 vectors in total),
with no GPU encoding. [Metrics](results/observed_length_20260928/metrics.tsv)
and [figure](results/observed_length_20260928/observed_length.pdf) are included.

| Input length (aa) | MCP proteins | V0.1 recipe MCP recall | Non-MCP proteins | V0.1 recipe false positives |
|---|---:|---:|---:|---:|
| <130 | 0 | NA | 0 | NA |
| 130–149 | 0 | NA | 1 | 0 |
| 150–199 | 0 | NA | 278 | 0 |
| 200–249 | 0 | NA | 280 | 0 |
| 250–299 | 13 | 13/13 (100%) | 482 | 0 |
| >=300 | 323 | 318/323 (98.45%) | 5,257 | 0 |

There are **no MCP positives below 250 aa**. These data cannot estimate MCP
recall in that range or establish a minimum usable length. The 13/13 estimate
has limited support, and zero observed false positives is not proof of zero
population error. V0 has the same aggregate MCP recall, with one false positive
at 200–249 aa and two at >=300 aa. This remains internal component cross-fit,
not an external test of the shipped heads. Only new fragment sequences require
GPU encoding in the complementary truncation experiment.


## Reuse historical embeddings: CPU-first observed-length benchmark

Run `prepare --mode observed` to evaluate only the original Train sequences,
without generating fragments. The seven observed-length bins are retained even
when empty (`NA`, never zero recall). This compares different proteins across
bins; it does not isolate the causal effect of truncating the same protein.

```bash
python3 benchmarks/short_sequence_v1/benchmark.py prepare --mode observed --out run/observed
python3 benchmarks/short_sequence_v1/benchmark.py reuse --run run/observed --encoder esm2_3b --source /path/to/v0_benchmark_esm2_3b --require-complete
python3 benchmarks/short_sequence_v1/benchmark.py reuse --run run/observed --encoder esmc_6b --source /path/to/v0_benchmark_esmc_6b --require-complete
python3 benchmarks/short_sequence_v1/benchmark.py score --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py summarize --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py validate --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py plot --run run/observed
```

These stages need NumPy, scikit-learn, PyYAML and Matplotlib, but no Torch, model
loading, or GPU. `reuse` verifies source checksums, pinned encoder revision,
precision, pooling, windowing, token handling and adapter options. It matches
exact sequence SHA-256 and length, selecting **Train rows only**, regardless of
old protein IDs. Existing destination bundles are never overwritten. Historical
bundles may contain other splits; those vectors and labels are not imported or
used for fitting, calibration or evaluation. Original cache files stay unchanged.

For `--mode truncation` (the default), run the same `reuse` commands first, without
`--require-complete`. Matched rows are marked complete in the resumable bundle;
`embed` then computes only missing sequences. `reuse/*.json` and mapping tables
record the source checksums and row provenance separately from encoder metadata.
Use a new run directory whenever the benchmark script changes. `plot` exports
`observed_length.png/.pdf/.svg`; truncation runs also export `length_curves`.


## Scientific contract

- Use the existing 6,634 Train proteins and the frozen five-fold component map.
  SHA-256 pins bind the Train manifest, FASTA, fold map, and encoder registry.
  Validation and Test records are not imported, embedded, calibrated, or scored;
  mixed-split historical cache containers are checked for integrity before selecting Train rows.
- In cycle `f`, evaluate fold `f`, calibrate fold `(f % 5) + 1`, and fit the other
  three folds. Fit and calibration use full input proteins only. Every parent
  and all of its fragments remain in its original component/fold.
- Compare `v0` (ESM-C 6B H1/H2) with `v01_candidate` (ESM-2 3B H1/H2). Use the
  pinned encoders, pooling/window rules, classifier families and fixed
  hyperparameters from this project. H3 is an ESM-C 6B logistic head fitted once
  per cycle and shared by both methods.
- These are **fold-specific refits**, not the shipped NPZ heads. They estimate
  internal generalization of the model recipes, not independent external
  accuracy of the released artifacts. No new model selection or release changes
  follow from this benchmark.
- H1 chooses a raw-score threshold maximizing calibration MCC; H2 maximizes
  macro-F1 on true-DJR calibration proteins. Ties choose the highest threshold;
  predict-none is an explicit candidate. Raw scores avoid sigmoid saturation.
  Each threshold is fixed across all lengths and positions in that cycle.
- H3 fits only the two known phyla. Its rejection threshold is the lower 5th
  percentile of absolute binary logits on full known-class calibration
  proteins. This targets at least 95% known acceptance. No unknown examples or
  test fragments select the threshold. For a binary head, absolute logit has the
  same ordering as confidence under any positive temperature; scores are not
  presented as calibrated probabilities.

## Fragment design

The primary panel contains a fixed cohort of parents with length >=300 aa.
Generate **50, 100, 130, 150, 200, 250, 300 aa** fragments plus a full-sequence
control from each parent, identically for positive and negative sources.

At every length take one N-terminal, one C-terminal, and one uniformly sampled
strictly internal fragment. The internal start excludes the two terminal start
positions. A SHA-derived per-parent/per-length seed makes results independent
of input ordering. Coordinates are zero-based, end-exclusive. If no internal
start exists, none is invented; e.g. for a 300-aa parent, both 300-aa terminal
views are identical to the full control. The manifest records all views while
embedding computation is deduplicated by exact sequence hash.

Record original and retained lengths, retained fraction, parent ID, sequence
hash, source class, component and fold. Short parents remain in the full-input
descriptive panel, but are excluded from every primary paired length.

New exact fragment collisions across folds are audited against all generated
queries, including full inputs. The entire affected parent is excluded from
**all** paired lengths, including its full control. It remains in the recorded
query universe and in the observed full-length panel. Exclusions are decided
before scoring and written to `paired_exclusions.tsv`. This detects exact
collisions, not every possible remote homology relationship.

Each fragment inherits its parent's origin label. A positive label means
**MCP-derived fragment**, not demonstrated preservation of a complete DJR fold,
capsid assembly, or biological function. Some fragments may contain little
diagnostic sequence; that information loss is part of the stress test.

## Endpoints and uncertainty

Primary endpoints:

1. End-to-end MCP recall: H1 AND H2 positive among MCP-derived fragments.
2. End-to-end MCP false-positive rate: H1 AND H2 positive among non-MCP
   fragments, both pooled and separately for cellular DJR, hard non-DJR, and
   background non-DJR. The pooled estimate reflects this benchmark's source
   mixture, not the false discovery rate in an application dataset.

`mcp::unknown/other` counts as a detected MCP. It is not an MCP false negative.
Secondary endpoints locate H1/H2 failures and measure H3 end-to-end known-phylum
recall (also by phylum), conditional accuracy, wrong-phylum rate, and rejection.
H2 diagnostics use all true-DJR queries, even those failing H1. H3 raw diagnostic
scores are computed for all queries, but conditional H3 metrics use only
H1/H2-positive MCPs. End-to-end H3 recall retains upstream failures in its
denominator. Unknown rejection is a small diagnostic, not proof of general OOD
detection.

Average eligible fragment outcomes within each parent first; then average
parents. This prevents extra windows from increasing a parent's weight. Report
eligible fragment, parent, and independent component counts. Confidence
intervals use 2,000 bootstrap replicates resampling whole components, retaining
all parents in each sampled component. A single component has no CI. A zero-
error bootstrap interval is flagged as a boundary result, not a population error
bound. These intervals do not include classifier-refitting or pretraining
uncertainty.

Paired differences report length minus full and V0.1 minus V0 on the intersection
of eligible parents. For conditional H3 endpoints this intersection can change
because upstream gates change; prefer end-to-end H3 recall for overall claims.
The endpoints are descriptive, with no multiplicity-adjusted superiority claim.

The separate `observed_length` panel scores full input records in bins <100,
100–129, 130–149, 150–199, 200–249, 250–299 and >=300 aa. These are not necessarily
experimentally verified complete natural short proteins. The <130-aa fragment
conditions are outside the documented training length range. No minimum usable
length is selected automatically; such a recommendation requires a prespecified
recall/FPR tolerance and independent confirmation.

## Run

From a checkout containing the private frozen Train data (the GitHub repository
does not distribute those FASTAs), prepare with Python 3.10+; this stage has no
third-party dependencies:

```bash
cd /path/to/DJR-MCP-Finder
python3 benchmarks/short_sequence_v1/benchmark.py prepare \
  --project-root /path/to/DJR-MCP-Finder \
  --out benchmarks/short_sequence_v1/run/production_v1
```

The four pinned input hashes were checked against gds2 on 2026-09-28. Preparation
refuses a nonempty output directory. A changed protocol or script requires a
new run directory; original inputs and releases are never overwritten.

Generate the two embedding bundles in their respective **existing compatible
environments**, on allocated GPU resources. Do not run these on a login node.
`ESMC_PYTHON` and `ESM2_PYTHON` below are paths to those environment interpreters;
they are not provided by this benchmark. ESM-C needs the project's custom pinned
Transformers implementation, whereas ESM-2 uses its own compatible environment.

```bash
"${ESMC_PYTHON:?Set the ESM-C environment interpreter}" \
  benchmarks/short_sequence_v1/benchmark.py embed \
  --run benchmarks/short_sequence_v1/run/production_v1 --encoder esmc_6b --device cuda

"${ESM2_PYTHON:?Set the ESM-2 environment interpreter}" \
  benchmarks/short_sequence_v1/benchmark.py embed \
  --run benchmarks/short_sequence_v1/run/production_v1 --encoder esm2_3b --device cuda
```

The existing project embedder resumes completed rows and verifies checkpoint
revisions. Run `--limit 2` first for an optional GPU smoke test, then repeat
without `--limit`. Partial, corrupt, wrong-revision, or mismatched bundles cannot
be scored. Features must be recomputed from fragment sequences: slicing or
reusing a parent's pooled embedding does not represent a short protein.

After both bundles finish, use the existing CPU classifier environment (NumPy,
scikit-learn, PyYAML, pandas, joblib, Biopython; no Torch needed for these stages):

```bash
python benchmarks/short_sequence_v1/benchmark.py score \
  --run benchmarks/short_sequence_v1/run/production_v1
python benchmarks/short_sequence_v1/benchmark.py summarize \
  --run benchmarks/short_sequence_v1/run/production_v1
python benchmarks/short_sequence_v1/benchmark.py validate \
  --run benchmarks/short_sequence_v1/run/production_v1
```

Use the existing frozen CPU environment on gds2 for comparable numerical fits;
its path is recorded in `pbs/score_gds2.pbs`. This job is submitted explicitly:

```bash
qsub benchmarks/short_sequence_v1/pbs/score_gds2.pbs
```

Plotting is separate and can run locally with `pip install '.[figure]'`:

```bash
python benchmarks/short_sequence_v1/benchmark.py plot \
  --run benchmarks/short_sequence_v1/run/production_v1
```

The plotting command writes PNG and PDF curves. It does not run automatically.

## Outputs

| File | Purpose |
|---|---|
| `prepared.json`, `config.json`, `registry.yaml` | Frozen input/code identities and sample counts |
| `inputs/parents.tsv`, `inputs/queries.tsv` | Full parent and fragment manifests |
| `inputs/paired_exclusions.tsv`, `inputs/paired_coverage.tsv` | Attrition and per-source/fold support |
| `inputs/embedding.faa`, `inputs/embedding_manifest.tsv` | Unique sequences for both encoders |
| `embeddings/{esmc_6b,esm2_3b}/` | Resumable checksum-verified feature bundles |
| `scores/predictions.tsv`, `scores/fold_contracts.tsv` | All queries, raw scores, gates and calibration contracts |
| `results/metrics.tsv`, `results/paired_deltas.tsv` | Per-length/position/source rates, counts, CIs and paired differences |
| `results/REPORT.md`, `results/length_curves.{png,pdf}` | Numeric report and optional curves |

Run data are gitignored. Reports reject missing prediction rows rather than
silently counting successful inferences alone. Full neural embedding and real
performance computation must finish before any scientific accuracy is reported.

## Tests

```bash
python -m pytest -q tests/test_short_sequence_benchmark.py
```

Tests cover deterministic coordinates, Train-only isolation, cross-fold fragment
collisions, short-parent exclusion, raw-threshold saturation/ties, independent
component counts, gate denominators, corrupt embeddings, missing predictions,
and a complete CPU pipeline with **synthetic test features**. They do not
validate the GPU backend or imply real protein prediction performance.

## 中文说明

这是 DJR-MCP-Finder 自身的短片段压力测试。用冻结 Train 数据的五折划分，
先按 component 分折，再生成 50–300 aa 片段；每折使用完整蛋白训练、校准，
用评价折的完整蛋白和片段测性能。主结果是 MCP 召回率、假阳性率随长度的变化，
并比较 V0 与 V0.1 Candidate。H3 分门结果单独报告。

主曲线固定同一批 >=300 aa 母序列，阴性也按相同方式截短；先对同一母序列的
片段取平均，再按 component 计算 bootstrap 置信区间。真实输入长度分层另表输出。
原始输入长度分层已复用历史 embedding 在 CPU 上完成；配对截短结果仍待完成。
不能把预检数量或合成测试结果当成短序列准确率。具体命令见上方 Run，gds2 的 CPU 汇总作业见 `pbs/score_gds2.pbs`。

## MCP-positive length statistics

The curated full dataset has 560 labeled MCP positives: Train 336, Validation 112,
Test 112. [All-split length statistics](results/mcp_positive_lengths_all_20260928/summary.tsv)
and the [distribution figure](results/mcp_positive_lengths_all_20260928/mcp_positive_lengths.pdf)
describe metadata only; they do not score the held-out sets. The full positive
range is 254–2,906 aa, median 473 aa; 22 records are 250–299 aa and none are below
250 aa. These counts differ from the Train-only benchmark by design.

Reproduce with `python3 benchmarks/short_sequence_v1/length_statistics.py --parents data/processed/v0/master_manifest.tsv --scope all --out benchmarks/short_sequence_v1/run/lengths_all`.

## Requested 50-aa benchmark bins (250–500+ aa)

The [re-binned table](results/length_bins_250_500_20260928/confusion_by_length.tsv)
and [figure](results/length_bins_250_500_20260928/visualization_en_v2/overview.en.pdf) reuse the same
Train-only cross-fit predictions. No model, threshold or split is changed.
Intervals are half-open: 250–299, 300–349, 350–399, 400–449, 450–499, >=500 aa;
<250 is retained as a supplementary diagnostic. V0.1 MCP recall is respectively
13/13, 14/15, 38/38, 75/77, 71/71 and 120/122. No false positives are observed
among the 6,298 non-MCP records. This does not imply a zero population error rate.
The first two positive groups are small (13 and 15), and length is confounded
with family composition. No monotonic length effect or optimal cutoff is established.

An MCP prediction below 250 aa is outside the positive length support of this
curated dataset. Its correctness and calibration are unvalidated in that range;
absence of reference positives does not show that all such calls are false.
The observed absence of false positives among 559 short negatives cannot estimate
short-positive sensitivity or deployment precision. This reporting change does
not add a hard rejection rule to inference.

```bash
python3 benchmarks/short_sequence_v1/length_bins_report.py --run benchmarks/short_sequence_v1/run/observed_production_20260928 --out benchmarks/short_sequence_v1/run/length_bins_250_500_new
```

This is descriptive re-binning requested after the initial analysis. Full-data
length statistics use 560 positives; performance here still uses 336 Train positives.

### English visualization update

The main figure now aligns recall bars with detected/positive counts, missed
proteins and false positives. Uncertainty and phylum detail are separate
supplements: [V0 comparison and intervals](results/length_bins_250_500_20260928/visualization_en_v2/comparison.en.pdf),
[phylum detail](results/length_bins_250_500_20260928/visualization_en_v2/phylum_detail.en.pdf).
Original tables and predictions are unchanged. All figure text is English.
