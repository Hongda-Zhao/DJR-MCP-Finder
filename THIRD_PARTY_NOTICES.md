# Third-party notices and license scope

The root [`LICENSE`](LICENSE) applies to project-authored source code,
documentation, configuration, figures, and the original bundled linear
classifier-head artifacts, unless a file states otherwise.

That license does not relicense external model checkpoints, software,
datasets, protein sequences, structures, database content, or trademarks.
Those materials remain subject to their own terms. References, accessions,
checksums, and derived scientific results in this repository do not imply that
the underlying third-party source material is redistributed under MIT.

## Models and runtime software

| Component | Upstream terms | Distribution in this repository |
| --- | --- | --- |
| [`Biohub/ESMC-6B`](https://huggingface.co/Biohub/ESMC-6B) | MIT; review the upstream model card and [Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/) | The checkpoint is downloaded separately and is not redistributed here. |
| [`Biohub/transformers`](https://github.com/Biohub/transformers) | Apache-2.0 | Installed from the pinned upstream Git revision; no vendored source. |
| [`facebook/esm2_t36_3B_UR50D`](https://huggingface.co/facebook/esm2_t36_3B_UR50D) | MIT | Used only by the unreleased V0.1 candidate; the checkpoint is downloaded separately. |
| Python dependencies declared in `pyproject.toml` files | Each dependency retains its upstream license and notices. | Installed through Python package tooling; source is not vendored here. |

The formal V0 bundle also carries a release-specific notice at
[`user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md`](user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/THIRD_PARTY_NOTICES.md).

## Data and database references

The research workflow records provenance for external resources such as NCBI,
UniProt, AlphaFold DB, ICTV materials, MGnify, and site-local archives. Users
must obtain those resources from their authoritative providers and follow the
providers' current licenses, attribution requirements, access policies, and
terms of use. The compact GitHub release does not grant additional rights to
those external resources.
