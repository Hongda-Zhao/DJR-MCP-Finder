#!/usr/bin/env python3
"""Check engineering documentation structure and local Markdown links."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^]]+\]\(([^)]+)\)")
DOCUMENTS = [
    "README.md",
    "docs/repository/README.cn.md",
    "docs/repository/README.ja.md",
    "docs/repository/CHANGELOG.md",
    "docs/repository/THIRD_PARTY_NOTICES.md",
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
    "README.md",
}
I18N_MANIFEST = ROOT / "docs/i18n/manifest.json"


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


def _check_i18n_manifest() -> list[Path]:
    _require(I18N_MANIFEST.is_file(), "missing docs/i18n/manifest.json")
    payload = json.loads(I18N_MANIFEST.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "i18n manifest schema mismatch")
    records = payload.get("documents")
    _require(isinstance(records, list) and records, "i18n manifest has no documents")

    repository_files = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    source_markdown = {
        relative
        for relative in repository_files
        if (ROOT / relative).is_file()
        if not relative.startswith("docs/i18n/")
        and not relative.endswith((".cn.md", ".ja.md"))
    }
    declared_sources = {record.get("source") for record in records}
    _require(
        declared_sources == source_markdown,
        "i18n source coverage changed: "
        f"{sorted(declared_sources.symmetric_difference(source_markdown))}",
    )

    all_versions: list[Path] = []
    seen_versions: set[str] = set()
    for record in records:
        source = record.get("source")
        source_language = record.get("source_language")
        mode = record.get("mode")
        _require(source_language in {"en", "cn"}, f"invalid source language for {source}")
        _require(
            mode in {"sibling", "relocated", "mirror", "hybrid"},
            f"invalid i18n mode for {source}",
        )
        _require(record.get(source_language) == source, f"source-language path mismatch for {source}")

        translated_paths = {
            language: record.get(language)
            for language in ("en", "cn", "ja")
            if language != source_language
        }
        mirrored = {
            language: isinstance(relative, str)
            and relative.startswith(f"docs/i18n/{language}/")
            for language, relative in translated_paths.items()
        }
        if mode == "sibling":
            _require(not any(mirrored.values()), f"sibling document uses mirror path: {source}")
        elif mode == "relocated":
            _require(
                all(
                    isinstance(relative, str)
                    and relative.startswith("docs/repository/")
                    for relative in translated_paths.values()
                ),
                f"relocated landing-page translation is outside docs/repository: {source}",
            )
        elif mode == "mirror":
            _require(all(mirrored.values()), f"mirror document has a non-mirror translation: {source}")
        else:
            _require(
                any(mirrored.values()) and not all(mirrored.values()),
                f"hybrid document must mix frozen sibling and mirror translations: {source}",
            )

        for language in ("en", "cn", "ja"):
            relative = record.get(language)
            _require(isinstance(relative, str) and relative, f"missing {language} path for {source}")
            _require(relative not in seen_versions, f"duplicate i18n path: {relative}")
            seen_versions.add(relative)
            path = ROOT / relative
            _require(path.is_file(), f"missing {language} version for {source}: {relative}")
            all_versions.append(path)

            if (
                mode in {"mirror", "hybrid"}
                and language != source_language
                and relative.startswith(f"docs/i18n/{language}/")
            ):
                marker = f"<!-- i18n-mirror: non-authoritative translation; source={source} -->"
                _require(
                    marker in path.read_text(encoding="utf-8").splitlines()[:5],
                    f"missing translation authority marker: {relative}",
                )

    return all_versions


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

    i18n_documents = _check_i18n_manifest()
    checked_links = sum(_check_links(path) for path in i18n_documents)
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    _require(manifest.get("schema_version") == 1, "release-manifest schema mismatch")
    print(
        json.dumps(
            {"documents": len(i18n_documents), "links": checked_links, "status": "valid"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
