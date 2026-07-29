# Frozen-input and empirical-resolution audit

This audit was completed before classical-score aggregation. It is independent
of method outcomes and does not alter the frozen estimands.

## Input-contract result

Status: **PASS**.

- The cohort is the exact frozen Train ID set: 6,634 records and 5,566
  `global_component_id` values; no Validation or Test records occur.
- Labels contain 6,000 non-DJR, 298 cellular DJR, and 336 VMA-DJR records; VMA
  is a strict subset of DJR.
- Every component belongs to one fold. Every record is evaluated once,
  calibrated once, and used in the three fit/reference cycles.
- Calibration, evaluation, and reference components are disjoint in all five
  cycles. All ten DJR/VMA reference manifests exactly equal the corresponding
  fit-fold positive sets.
- TSV/FASTA IDs, order, sequences, and checksums agree. The five frozen source
  hashes and all 52 derived-input hashes match their attestations.
- The project post-split integrity report is PASS, with zero cross-split
  component, sequence-SHA, or qualifying search-edge violations.

## Evaluation-fold counts

Cells show `records/components`.

| Eval fold | H1 DJR + | H1 non-DJR - | H2 VMA + | H2 cellular - | End-to-end VMA + | End-to-end - |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 114/94 | 1200/731 | 55/47 | 59/47 | 55/47 | 1259/778 |
| 2 | 178/65 | 1200/1115 | 119/18 | 59/47 | 119/18 | 1259/1162 |
| 3 | 115/48 | 1200/1112 | 53/47 | **62/1** | 53/47 | 1262/1113 |
| 4 | 114/91 | 1200/1109 | 55/49 | 59/42 | 55/49 | 1259/1151 |
| 5 | 113/94 | 1200/1107 | 54/48 | 59/46 | 54/48 | 1259/1153 |

## Cyclic 3/1/1 counts

| Cycle | Eval | Calibration | Fit folds | H2 calibration + / - | DJR reference | VMA reference |
|---|---:|---:|---|---:|---:|---:|
| 1 | 1 | 2 | 3,4,5 | 119/18 +; 59/47 - | 342/233 | 162/144 |
| 2 | 2 | 3 | 1,4,5 | 53/47 +; **62/1 -** | 341/279 | 164/144 |
| 3 | 3 | 4 | 1,2,5 | 55/49 +; 59/42 - | 405/253 | 228/113 |
| 4 | 4 | 5 | 1,2,3 | 54/48 +; 59/46 - | 407/207 | 227/112 |
| 5 | 5 | 1 | 2,3,4 | 55/47 +; 59/47 - | 407/204 | 227/114 |

## Resolution limitations

1. Fold 3's 62 cellular-DJR negative records all belong to
   `V0GC_96fb96e7e076c167`. In H2 cycle 2 each record has 1/62 (1.61%) negative
   mass, so 99%, 99.5%, and 99.9% calibration all require zero empirical false
   positives.
2. H2 evaluation fold 3 has one independent negative component. A bootstrap
   stratum with one component has fixed multiplicity one and cannot estimate
   between-component variation for that source.
3. Fold 2 has 119 VMA positives but only 18 components, including one component
   with 101 records. Component weighting prevents record-count domination, but
   the fold still has only 18 independent positive units.
4. Fold record counts are 1,314/1,378/1,315/1,314/1,313, whereas component
   counts are 825/1,180/1,160/1,200/1,201. Fold-level ranges and component
   counts must therefore accompany macro estimates.
5. Two non-DJR components span hard/background source labels without crossing
   class labels. The larger, `V0GC_811321e4f6b69a00`, contains 470 records
   (465 hard and 5 background). Source weighting and bootstrap resampling keep
   each global component intact.

Consequently, affected H2 and end-to-end low-FPR sensitivity intervals are
reported as conditional, internal evidence. Future external evaluation should
stratify at the component level and include enough independent cellular-DJR
negative components to resolve the target FPR.
