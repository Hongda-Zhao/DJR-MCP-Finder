#!/usr/bin/env python3
"""Check engineering documentation structure and local Markdown links."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^]]+\]\(([^)]+)\)")
DOCUMENTS = [
    "README.md",
    "README.cn.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/README.md",
    "docs/ARCHITECTURE.md",
    "docs/REPRODUCIBILITY.md",
    "docs/SCIENTIFIC_EVIDENCE.md",
    "docs/VERSIONING.md",
    "docs/research/WORKFLOW_V0.md",
    "docs/research/PROJECT_V0_FINAL_REPORT.md",
    "docs/research/VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_PROTOCOL.md",
    "user-inference-v0/README.md",
    "user-inference-v0/README.cn.md",
    "user-inference-v0.1/README.md",
    "user-inference-v0.1/README.cn.md",
]
REQUIRED_COMMUNITY_FILES = [
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/scientific_question.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/pull_request_template.md",
]
ALLOWED_ROOT_MARKDOWN = {
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "README.cn.md",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"documentation check failed: {message}")


def _check_links(path: Path) -> int:
    checked = 0
    text = path.read_text(encoding="utf-8")
    for raw_target in LINK.findall(text):
        target = raw_target.strip().split()[0].strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not relative:
            continue
        resolved = (path.parent / relative).resolve()
        _require(resolved.exists(), f"broken link in {path.relative_to(ROOT)}: {target}")
        checked += 1
    return checked


def main() -> None:
    for relative in DOCUMENTS + REQUIRED_COMMUNITY_FILES:
        _require((ROOT / relative).is_file(), f"missing required file: {relative}")

    readme_lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    _require(len(readme_lines) <= 180, f"README.md grew to {len(readme_lines)} lines")
    root_markdown = {path.name for path in ROOT.glob("*.md")}
    _require(
        root_markdown == ALLOWED_ROOT_MARKDOWN,
        f"root Markdown surface changed: {sorted(root_markdown ^ ALLOWED_ROOT_MARKDOWN)}",
    )
    forbidden = {"## Frozen V0", "## Current evidence hierarchy", "## Running the research workflow from another location"}
    _require(not forbidden.intersection(readme_lines), "research detail returned to README.md")

    checked_links = sum(_check_links(ROOT / relative) for relative in DOCUMENTS)
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    _require(manifest.get("schema_version") == 1, "release-manifest schema mismatch")
    print(json.dumps({"documents": len(DOCUMENTS), "links": checked_links, "status": "valid"}, indent=2))


if __name__ == "__main__":
    main()
