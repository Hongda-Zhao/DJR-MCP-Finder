# Security Policy

## Supported surfaces

| Surface | Status |
| --- | --- |
| Latest `v0.1.x` repository release | Security fixes accepted |
| Released `model-v0` inference package | Security and integrity fixes accepted without retuning the model |
| `model-v0.1-candidate` | Development candidate; fixes are best effort and do not promote its evidence status |
| Historical research snapshots | Preserved provenance; normally not patched in place |

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private vulnerability
reporting entry under the repository **Security** tab. If that entry is not available, contact the
repository owner through an established private channel and withhold public technical details until
a private reporting path is agreed.

Include:

- the affected release, package, command, or container;
- impact and realistic attack scenario;
- minimal reproduction steps using non-sensitive data;
- whether integrity checks, path handling, model loading, or output overwrite behavior are involved;
- a proposed mitigation, if known.

The maintainer will acknowledge the report, assess severity, and coordinate disclosure and a fix.
Response time depends on maintainer availability; this document does not promise a fixed remediation
window.

## Security boundaries

- Model checkpoints and external runtimes are downloaded separately and retain upstream security
  and licensing responsibilities.
- Checksums detect accidental or malicious modification of frozen local artifacts; they are not a
  substitute for signed provenance or a trusted download channel.
- Protein FASTA files are untrusted input. Reports should call out parsing, path traversal, resource
  exhaustion, unsafe deserialization, or output-overwrite risks explicitly.
- Never include private sequences, access tokens, filesystem credentials, or unpublished dataset
  records in a report.

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for external components and
[`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for the frozen-artifact boundary.
