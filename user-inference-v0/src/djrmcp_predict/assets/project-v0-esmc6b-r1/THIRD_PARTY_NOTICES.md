# Third-party notices

The embedding model is obtained separately from:

- `Biohub/ESMC-6B`
- https://huggingface.co/Biohub/ESMC-6B

The frozen adapter uses the Biohub Transformers fork:

- https://github.com/Biohub/transformers
- revision `ef32577f55da19a4989cd7b22e004dc43a4998cb`

The Biohub ESM code and ESM-C model weights are published under MIT. Review the
upstream model card, third-party notices, and
[Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/) before
redistribution or deployment. The pinned
[Biohub Transformers fork](https://github.com/Biohub/transformers) is published
under Apache-2.0. This inference bundle does not redistribute the 6B checkpoint.

The DJR-MCP Finder package code and original bundled linear classifier heads are
covered by the package-level MIT `LICENSE`. That license does not relicense the
external checkpoint, upstream runtime software, or source datasets.
