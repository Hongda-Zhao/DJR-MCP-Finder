# Design decisions and exclusions

## Why 3/1/1 instead of ordinary five-fold OOF thresholding?

Ordinary OOF ranking is adequate for a fold-specific AP, but using scores from
the other four OOF fits to calibrate fold *k* would indirectly reuse fold *k* in
those models/reference libraries.  It would also exchange thresholds among
different-sized maximum-similarity databases.  The cyclic design therefore
uses three fit/reference folds, one dedicated calibration fold, and one
evaluation fold.  Every original component is evaluated once and used for
calibration once, but never for both roles in the same cycle.

## Why are supervised ESM-C and family HMMs not in the controlled headline?

The supervised ESM-C system learns from labelled negatives, whereas controlled
retrievers only receive the positive reference FASTA.  Conversely, the family
HMM grouping uses curated family/taxonomy metadata.  Both are useful operational
systems, but mixing them into the controlled representation comparison would
confound the source of any sensitivity difference.

ESM-C 6B and its classifier hyperparameters were selected during earlier
development involving these folds/Validation.  Its operational rows are thus
labelled `selected_model_descriptive_only`, even though each cyclic fit itself
keeps calibration and evaluation components out of training.

## Why not use the historical project HMM bundles?

They predate the frozen split and participated in curation or exclusion logic.
Their result would be circular for this cohort.  Only Train-only profiles built
inside each cycle are eligible here; historical bundles may be evaluated later
on a genuinely external cohort.

## Why is 99.5% specificity primary here?

The current internal cohort has too few negative components to estimate 99.9%
specificity stably, particularly for conditional H2.  The future external
benchmark endpoint remains 99.9%; this internal protocol explicitly amends its
primary endpoint to 99.5% and labels 99.9% as resolution-limited secondary.

## Why are some 99.5% sensitivity intervals labelled conditional?

The frozen fold map is balanced mainly by records, not by independent
components. In fold 3, all 62 cellular-DJR negatives belong to one component.
That fold is the H2 calibration fold for cycle 2 and the H2 evaluation fold for
cycle 3. The cycle-2 calibration therefore cannot admit even one false-positive
record at 99.5%, while the single-component bootstrap stratum cannot express
between-component uncertainty. End-to-end VMA calibration contains this same
cellular source alongside other negative sources and inherits the corresponding
source-specific limitation.

We keep the pre-registered estimand and expose the limitation in separate
resolution-status fields; we do not silently widen the FPR target or treat a
conditional interval as external low-FPR evidence.

## Why is deployed PLMSearch not in the primary matrix?

The gds2 PLMSearch module is an uncommitted 2024 CPU deployment built around
ESM-1b and an externally trained SCOP/CATH similarity model.  It truncates
sequences beyond 1,022 residues and its score is directional.  Those properties
make it a useful future exploratory resource tier, not a drop-in controlled
replacement for the project embeddings.  The primary PLM retrieval track uses
fully checksum-frozen ESM-C 6B and ESM-2 650M embeddings.  pLM-BLAST is not
installed on gds2.
