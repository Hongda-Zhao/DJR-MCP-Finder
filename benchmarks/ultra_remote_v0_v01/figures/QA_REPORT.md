# Figure QA report

- Core conclusion and panel hierarchy match `FIGURE_CONTRACT.md`.
- Backend: Python/matplotlib exclusively; exact versions are recorded in
  `visualization_manifest.json`.
- Static source preflight: 14 PASS, 0 WARN, 0 FAIL.
- Visual inspection: final-size PNG inspected after two layout revisions; no title,
  legend, axis-label, panel-label, or footer overlap remains; no marks are cropped.
- Final width: 180.1 mm; minimum declared text size: 5.1 pt.
- Exports: editable-text SVG, TrueType-text PDF, 300-dpi PNG preview, 600-dpi TIFF.
- Data integrity: no observations were sampled or removed. Method subsets in panels
  b/c are predeclared for legibility; complete method tables remain under `results/`.
- Statistics: paired intervals resample independent evaluation components with
  thresholds fixed from calibration; calibration uncertainty is excluded and stated.
- Specificity: open markers explicitly downgrade every pair where either system
  misses actual 99.5% specificity in at least one fold.
- Low-FPR resolution: H2 and end-to-end pAUROC are suppressed rather than interpolated
  because per-source independent-negative resolution is insufficient at FPR 0.005.
- Sample-size gate: strict qcov >=80%, identity <20% contains n=1 component and is
  displayed as insufficient evidence; it has no CI or superiority annotation.
- Source data and every export are SHA-256 bound in `visualization_manifest.json` and
  the benchmark-level `CHECKSUMS.sha256`.
