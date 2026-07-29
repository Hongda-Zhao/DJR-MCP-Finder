# Project V0 ESM-C 6B inference bundle

This bundle contains the three frozen DJR-MCP Finder project-V0 linear heads in a
pickle-free NumPy representation. It does not contain the ESM-C 6B checkpoint.

## Intended use

- H1: DJR versus non-DJR.
- H2: viral-morphogenesis association, operationally reached only after H1.
- H3: Nucleocytoviricota versus Preplasmiviricota with a frozen low-confidence
  rejection, operationally reached only after H1 and H2.

## Fixed representation

- Model: `Biohub/ESMC-6B`
- Window/stride: 1022/511 amino acids
- Pooling: residue mean followed by window mean
- Dimension: 2560
- Classifier input: float16 storage round-trip, then float32 linear inference

## Limitations

- The selected ESM-C 6B has not been scored on a new prospective external Test.
- Calibrated scores are not prevalence-adjusted posterior probabilities.
- H3 `unknown/other` is not a general unknown-virus or OOD detector.
- Training sources and labels are partially confounded; independent same-source
  validation remains necessary.
- Inputs outside the observed training alphabet/length domain require caution.

See `release.json` and `PARITY_REPORT.json` for exact identities and verification.

