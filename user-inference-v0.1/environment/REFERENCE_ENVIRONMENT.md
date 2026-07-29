# Frozen mixed-encoder reference environment

This is the historical environment used for validation, not a required host or
checkout location. Portable wrappers record the environment actually observed
for every inference run.

```text
Common       Python 3.12.3; NumPy 2.5.1; PyTorch 2.13.0+cu130
ESM-2 3B    Transformers 5.14.1; CUDA FP16; window batch 2
ESM-C 6B    Biohub Transformers 4.57.6 @ ef32577f55da19a4989cd7b22e004dc43a4998cb;
             CUDA BF16; window batch 1
GPU          NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition
OS           Linux x86_64; glibc 2.39; CUDA runtime 13.0
```

Both encoders produce 2560-dimensional vectors using residue mean followed by
overlapping-window mean (1022 residues, stride 511), then the frozen float16
storage round-trip consumed by the classifiers. The public runtime verifies both
checkpoint revisions and the encoder-specific Transformers installation, and
records actual model, package, GPU, parameter-count, and peak-memory provenance.

Scientific status: Train-only shared five-fold CV nomination, zero prospective
external Test records, external confirmation required, released V0 unchanged.
