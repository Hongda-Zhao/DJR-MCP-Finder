# Figure 1 QA notes

- Core conclusion: corrected raw-score AP, paired one-SE, Validation gates and preregistered tie breaks select ESM-C 6B from the exact 14-model registry.
- Metric lineage: binary ranking metrics use raw decision-function scores; calibrated probabilities are reserved for calibration/threshold metrics.
- Archetype/backend: quantitative grid; Python/Matplotlib only.
- Final size: 183 × 238 mm; SVG/PDF editable vectors, TIFF 600 dpi, PNG 300 dpi.
- Input integrity: exact candidate count before/after = 14/14; exclusions = 0; sampling = none; hidden failed candidates = 0.
- Boundary: development-only; every frozen candidate row must say `test_status=not_evaluated`.
- Statistics: one shared Train-only five-fold global-component map; per-head/composite SE = SD/√5; paired SEΔ uses same-fold differences.
- H3 limitation: `unknown/other` is an operational rejection diagnostic (Validation n=5), not an arbitrary unseen-virus detector.
- Compute limitation: NA: frozen comparison has no per-model peak_gpu_memory_source attestation. Timing has 2 comparability groups, so panel c is descriptive and no Pareto frontier is claimed.
- Image integrity: all panels are programmatic quantitative vector graphics; no microscopy, photographs, crops, local contrast adjustment or pseudo-colour processing.
- Automated export QA: PASS (dimensions and editable SVG text checked before publication).
- Visual QA status: passed.
- Manual native-resolution inspection: all five panels are legible, with no clipping, overlap, or missing labels.
- The plotted numeric source is unchanged; this refresh binds provenance to the corrected frozen Test policy.
