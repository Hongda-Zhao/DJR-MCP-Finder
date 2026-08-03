**English** | [简体中文](README.cn.md)

# Project V0 current figure release

The active release retains one main figure and one supplementary figure. Figure 1 selects and
explains the primary model. Supplementary Fig. S1 is a post-freeze schema 5 family-neighbour
evaluation and cannot feed back into Figure 1.

| Figure | Directory | Conclusion | Interpretation boundary |
| --- | --- | --- | --- |
| 1. 14-model development benchmark | `model_benchmark_metric_revision_1/` | selects ESM-C 6B under raw-score ranking, `S=0.997145`; the old 650M H1 CV AP of `0.857` was a sigmoid-tie artifact, corrected to `0.997917` | Train/Validation development selection; ESM-C 6B Test=`not_evaluated` |
| Supplementary Fig. S1. Schema 5 head-focused robustness | `validation_family_robustness_v0_schema5_head_focus/` | eight homogeneous systems and nine preregistered mixed recipes; the Train-CV nominee is H1/H2 ESM-2 3B + H3 ESM-C 6B, with `0/4` warnings across four sources | auxiliary only; robustness does not affect ranking and is not an equivalence test, release gate, independent Test, or unseen-family benchmark |

Supplementary Fig. S1 shows three layers: per-head performance, expected-path performance, and
the Train-CV → nomination → four-source checking sequence for the 3×3 mixed recipes. H3 rare and
unclassified categories remain separate and must not be combined into a general unknown-virus
detector. See `FIGURE_GUIDE.md` in that directory for the full interpretation guide.

Each completed directory retains editable SVG/PDF files, PNG exports, panel source data,
QA/provenance records, and its own checksum manifest; available TIFF files are also included in the
current compact release. The primary-workflow manifest binds Figure 1, while the head-focus figure
manifest binds Supplementary Fig. S1. No additional manifest-of-manifests index is required.

Historical Test data were opened only for ESM-2 650M. The current active figures do not include an
ESM-C 6B Test panel, preventing evidence from the older model from being incorrectly attributed to
the new model.
