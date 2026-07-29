"""Non-destructive, checksum-verified archival support for the project V0 tree.

The implementation intentionally supports only same-filesystem atomic renames.  It never falls
back to copy-and-delete, and it never removes a staging directory after a failure.  That makes an
interrupted run inspectable and keeps every scientific artifact recoverable by rename.
"""

from __future__ import annotations

import csv
import ctypes
import errno
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


DEFAULT_PROJECT_ROOT = Path(
    os.path.abspath(
        os.fspath(
            Path(
                os.environ.get(
                    "DJRMCP_PROJECT_ROOT", Path(__file__).resolve().parents[2]
                )
            ).expanduser()
        )
    )
)
DEFAULT_ARCHIVE_BASE = Path(
    os.path.abspath(
        os.fspath(
            Path(
                os.environ.get(
                    "DJRMCP_ARCHIVE_ROOT",
                    DEFAULT_PROJECT_ROOT.parent / "DJRMCP_Develope",
                )
            ).expanduser()
        )
    )
)
_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_EVIDENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_INVENTORY_HEADER = (
    "relative_path",
    "entry_type",
    "size_bytes",
    "content_sha256",
    "mode",
    "mtime_ns",
    "link_target",
)


class ArchiveError(RuntimeError):
    """Raised when an archive precondition or integrity check fails."""


@dataclass(frozen=True)
class ExternalEvidence:
    """One immutable file outside the active tree that must exist before minimization."""

    evidence_id: str
    path: Path
    sha256: str
    purpose: str


@dataclass(frozen=True)
class VerifiedExternalEvidence:
    """Observed immutable-file identity captured during preflight."""

    evidence_id: str
    path: Path
    size_bytes: int
    sha256: str
    purpose: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute path without resolving mount aliases or symlinked ancestors."""

    return Path(os.path.abspath(os.fspath(path)))


def _normalize_relative_path(value: object, field: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise ArchiveError(f"{field} entries must be strings")
    if not value or value in {".", "./"}:
        raise ArchiveError(f"{field} must not contain the project root")
    if "\\" in value:
        raise ArchiveError(
            f"{field} uses POSIX relative paths; backslashes are not allowed: {value}"
        )
    if any(character in value for character in "\x00\n\r\t"):
        raise ArchiveError(f"{field} contains a control character: {value!r}")
    if any(character in value for character in "*?["):
        raise ArchiveError(f"{field} must be explicit and must not contain globs: {value}")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ArchiveError(f"{field} contains an empty, dot, or parent segment: {value}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ArchiveError(f"{field} entries must be relative: {value}")
    return path


def _same_or_parent(left: PurePosixPath, right: PurePosixPath) -> bool:
    return left == right or left in right.parents


def _validate_nonoverlap(paths: Sequence[PurePosixPath], field: str) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if _same_or_parent(left, right) or _same_or_parent(right, left):
                raise ArchiveError(f"{field} entries overlap: {left} and {right}")


@dataclass(frozen=True)
class ArchivePlan:
    """Validated keep/archive policy loaded from the JSON manifest."""

    schema_version: int
    project_name: str
    project_version: str
    data_curation_release: str
    # Legacy aliases are retained so the already-executed schema-v1/database-v3 archive
    # remains readable without rewriting its immutable manifest.
    project_dataset_version: str
    upstream_database_release: str
    version_mapping: str
    release_id: str
    source_project_root: Path
    archive_base: Path
    archive_paths: tuple[PurePosixPath, ...]
    keep_paths: tuple[PurePosixPath, ...]
    required_active_paths: tuple[PurePosixPath, ...]
    required_file_sha256: tuple[tuple[PurePosixPath, str], ...]
    allow_internal_symlinks: bool
    allowed_internal_symlinks: tuple[tuple[PurePosixPath, str], ...]
    exact_partition: bool
    expected_unclassified_count: int | None
    active_inventory_manifest: Path | None
    active_inventory_manifest_sha256: str | None
    active_inventory_control_paths: tuple[PurePosixPath, ...]
    variable_active_subtrees: tuple[PurePosixPath, ...]
    external_evidence: tuple[ExternalEvidence, ...]
    raw: dict[str, Any]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ArchivePlan":
        schema_version = payload.get("schema_version")
        if schema_version not in {1, 2}:
            raise ArchiveError("archive manifest schema_version must be 1 or 2")
        if payload.get("project_name") != "DJR-MCP-Finder":
            raise ArchiveError("project_name must be DJR-MCP-Finder")

        if schema_version == 1:
            if payload.get("project_dataset_version") != "v0":
                raise ArchiveError("project_dataset_version must remain v0")
            if payload.get("upstream_database_release") != "V3":
                raise ArchiveError("upstream_database_release must be V3")
            project_version = "V0"
            data_curation_release = "V3"
            project_dataset_version = "v0"
            upstream_database_release = "V3"
        else:
            if payload.get("project_version") != "V0":
                raise ArchiveError("schema-v2 project_version must be exactly V0")
            if payload.get("data_curation_release") != "V3":
                raise ArchiveError("schema-v2 data_curation_release must be exactly V3")
            # These aliases may be present for compatibility but may not contradict the
            # canonical semantics.  V3 is a data-curation release, not a project version.
            if payload.get("project_dataset_version", "v0") != "v0":
                raise ArchiveError("project_dataset_version compatibility alias must be v0")
            if payload.get("upstream_database_release", "V3") != "V3":
                raise ArchiveError("upstream_database_release compatibility alias must be V3")
            project_version = "V0"
            data_curation_release = "V3"
            project_dataset_version = "v0"
            upstream_database_release = "V3"
        mapping = payload.get("version_mapping")
        if not isinstance(mapping, str) or "V3" not in mapping or not (
            "V0" in mapping or "v0" in mapping
        ):
            raise ArchiveError(
                "version_mapping must explicitly map data-curation V3 to project V0"
            )

        release_id = payload.get("release_id")
        if not isinstance(release_id, str) or not _RELEASE_ID.fullmatch(release_id):
            raise ArchiveError("release_id must contain only letters, numbers, '.', '_' and '-'")

        source_project_root = Path(payload.get("source_project_root", DEFAULT_PROJECT_ROOT))
        archive_base = Path(payload.get("archive_base", DEFAULT_ARCHIVE_BASE))
        if _lexical_absolute(archive_base) != DEFAULT_ARCHIVE_BASE:
            raise ArchiveError(f"archive_base must be exactly {DEFAULT_ARCHIVE_BASE}")

        archive_values = payload.get("archive_paths")
        active_field = "active_allowlist" if schema_version == 2 else "keep_paths"
        keep_values = payload.get(active_field)
        if not isinstance(archive_values, list) or not archive_values:
            raise ArchiveError("archive_paths must be a non-empty list of explicit paths")
        if not isinstance(keep_values, list) or not keep_values:
            raise ArchiveError(f"{active_field} must be a non-empty list of explicit paths")
        archive_paths = tuple(
            _normalize_relative_path(value, "archive_paths") for value in archive_values
        )
        keep_paths = tuple(
            _normalize_relative_path(value, active_field) for value in keep_values
        )
        if len(set(archive_paths)) != len(archive_paths):
            raise ArchiveError("archive_paths contains duplicate entries")
        if len(set(keep_paths)) != len(keep_paths):
            raise ArchiveError(f"{active_field} contains duplicate entries")
        _validate_nonoverlap(archive_paths, "archive_paths")
        for archived in archive_paths:
            for kept in keep_paths:
                if schema_version == 1:
                    if _same_or_parent(archived, kept) or _same_or_parent(kept, archived):
                        raise ArchiveError(
                            f"keep/archive policy overlaps: {kept} and {archived}"
                        )
                elif archived == kept or archived in kept.parents:
                    raise ArchiveError(
                        "archive path would remove an active allowlist path: "
                        f"{archived} and {kept}"
                    )

        exact_partition = payload.get("classification_policy") == "exact_partition"
        expected_unclassified_count = payload.get("expected_unclassified_count")
        if schema_version == 2:
            if not exact_partition:
                raise ArchiveError(
                    "schema-v2 classification_policy must be exact_partition"
                )
            if expected_unclassified_count != 0:
                raise ArchiveError(
                    "schema-v2 expected_unclassified_count must be exactly 0"
                )
        elif expected_unclassified_count is not None:
            raise ArchiveError(
                "expected_unclassified_count is supported only by schema_version 2"
            )

        active_inventory_manifest: Path | None = None
        active_inventory_manifest_sha256: str | None = None
        active_inventory_control_paths: tuple[PurePosixPath, ...] = ()
        variable_active_subtrees: tuple[PurePosixPath, ...] = ()
        if schema_version == 2:
            manifest_value = payload.get("active_inventory_manifest")
            if not isinstance(manifest_value, str) or not Path(manifest_value).is_absolute():
                raise ArchiveError(
                    "schema-v2 active_inventory_manifest must be an absolute path"
                )
            active_inventory_manifest = _lexical_absolute(Path(manifest_value))
            archive_boundary = _lexical_absolute(archive_base)
            if (
                active_inventory_manifest == archive_boundary
                or archive_boundary not in active_inventory_manifest.parents
            ):
                raise ArchiveError(
                    "active_inventory_manifest must be below archive_base"
                )
            binding = payload.get("active_inventory_manifest_sha256")
            if binding != "UNBOUND" and not (
                isinstance(binding, str) and re.fullmatch(r"[0-9a-f]{64}", binding)
            ):
                raise ArchiveError(
                    "active_inventory_manifest_sha256 must be UNBOUND or a lowercase SHA-256"
                )
            active_inventory_manifest_sha256 = binding
            control_values = payload.get("active_inventory_control_paths")
            if not isinstance(control_values, list) or not control_values:
                raise ArchiveError(
                    "schema-v2 active_inventory_control_paths must be a non-empty list"
                )
            active_inventory_control_paths = tuple(
                _normalize_relative_path(value, "active_inventory_control_paths")
                for value in control_values
            )
            if len(set(active_inventory_control_paths)) != len(
                active_inventory_control_paths
            ):
                raise ArchiveError(
                    "active_inventory_control_paths contains duplicate entries"
                )
            variable_values = payload.get("variable_active_subtrees")
            if variable_values != [".git"]:
                raise ArchiveError(
                    "schema-v2 variable_active_subtrees must be exactly ['.git']"
                )
            variable_active_subtrees = (PurePosixPath(".git"),)
            for special in (
                *active_inventory_control_paths,
                *variable_active_subtrees,
            ):
                if not any(
                    _path_is_at_or_below(special, active) for active in keep_paths
                ):
                    raise ArchiveError(
                        "active inventory exclusions must be covered by active_allowlist: "
                        f"{special}"
                    )
                if any(
                    _path_is_at_or_below(special, archived)
                    or _path_is_at_or_below(archived, special)
                    for archived in archive_paths
                ):
                    raise ArchiveError(
                        f"active inventory exclusion overlaps archive_paths: {special}"
                    )

        required_active_values = payload.get("required_active_paths", [])
        if not isinstance(required_active_values, list):
            raise ArchiveError("required_active_paths must be a JSON list")
        required_active_paths = tuple(
            _normalize_relative_path(value, "required_active_paths")
            for value in required_active_values
        )
        if len(set(required_active_paths)) != len(required_active_paths):
            raise ArchiveError("required_active_paths contains duplicate entries")
        for required_active in required_active_paths:
            if not any(
                _path_is_at_or_below(required_active, active) for active in keep_paths
            ):
                raise ArchiveError(
                    "required_active_paths must be covered by active_allowlist: "
                    f"{required_active}"
                )
            if any(
                _path_is_at_or_below(required_active, archived)
                or _path_is_at_or_below(archived, required_active)
                for archived in archive_paths
            ):
                raise ArchiveError(
                    "required_active_paths overlaps archive_paths: "
                    f"{required_active}"
                )

        required_payload = payload.get("required_file_sha256", {})
        if not isinstance(required_payload, dict):
            raise ArchiveError("required_file_sha256 must be a JSON object")
        required_file_sha256 = []
        for raw_path, raw_digest in required_payload.items():
            required_path = _normalize_relative_path(raw_path, "required_file_sha256")
            if not isinstance(raw_digest, str) or not re.fullmatch(
                r"[0-9a-f]{64}", raw_digest
            ):
                raise ArchiveError(
                    f"required_file_sha256 has an invalid lowercase SHA-256 for {required_path}"
                )
            required_file_sha256.append((required_path, raw_digest))

        symlink_policy = payload.get("symlink_policy", "reject_all")
        if symlink_policy not in {
            "reject_all",
            "allow_internal_targets_without_dereference",
            "allow_declared_without_dereference",
        }:
            raise ArchiveError(
                "symlink_policy must be reject_all, "
                "allow_internal_targets_without_dereference, or "
                "allow_declared_without_dereference"
            )
        allowed_symlink_payload = payload.get("allowed_internal_symlinks", {})
        if not isinstance(allowed_symlink_payload, dict):
            raise ArchiveError("allowed_internal_symlinks must be a JSON object")
        allowed_internal_symlinks = []
        for raw_path, raw_target in allowed_symlink_payload.items():
            allowed_path = _normalize_relative_path(raw_path, "allowed_internal_symlinks")
            if not isinstance(raw_target, str) or not raw_target:
                raise ArchiveError(
                    f"allowed_internal_symlinks has an invalid target for {allowed_path}"
                )
            if any(character in raw_target for character in "\x00\n\r"):
                raise ArchiveError(
                    f"allowed_internal_symlinks target contains a control character: {allowed_path}"
                )
            allowed_internal_symlinks.append((allowed_path, raw_target))
        if allowed_internal_symlinks and symlink_policy == "reject_all":
            raise ArchiveError(
                "allowed_internal_symlinks requires "
                "symlink_policy=allow_internal_targets_without_dereference"
            )

        external_payload = payload.get("external_evidence", [])
        if not isinstance(external_payload, list):
            raise ArchiveError("external_evidence must be a JSON list")
        external_evidence: list[ExternalEvidence] = []
        seen_evidence_ids: set[str] = set()
        seen_evidence_paths: set[Path] = set()
        for index, item in enumerate(external_payload):
            field = f"external_evidence[{index}]"
            if not isinstance(item, dict):
                raise ArchiveError(f"{field} must be a JSON object")
            evidence_id = item.get("evidence_id")
            if not isinstance(evidence_id, str) or not _EVIDENCE_ID.fullmatch(evidence_id):
                raise ArchiveError(f"{field}.evidence_id is invalid")
            if evidence_id in seen_evidence_ids:
                raise ArchiveError(f"external_evidence duplicate evidence_id: {evidence_id}")
            path_value = item.get("path")
            if not isinstance(path_value, str) or not Path(path_value).is_absolute():
                raise ArchiveError(f"{field}.path must be an absolute path")
            evidence_path = _lexical_absolute(Path(path_value))
            if evidence_path in seen_evidence_paths:
                raise ArchiveError(f"external_evidence duplicate path: {evidence_path}")
            digest = item.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ArchiveError(f"{field}.sha256 must be a lowercase SHA-256")
            purpose = item.get("purpose")
            if not isinstance(purpose, str) or not purpose.strip():
                raise ArchiveError(f"{field}.purpose must be a non-empty string")
            archive_boundary = _lexical_absolute(archive_base)
            if (
                evidence_path == archive_boundary
                or archive_boundary not in evidence_path.parents
            ):
                raise ArchiveError(
                    f"{field}.path must be below archive_base {archive_boundary}"
                )
            seen_evidence_ids.add(evidence_id)
            seen_evidence_paths.add(evidence_path)
            external_evidence.append(
                ExternalEvidence(evidence_id, evidence_path, digest, purpose.strip())
            )

        if schema_version == 2 and not external_evidence:
            raise ArchiveError(
                "schema-v2 final minimization requires non-empty external_evidence"
            )

        return cls(
            schema_version=schema_version,
            project_name="DJR-MCP-Finder",
            project_version=project_version,
            data_curation_release=data_curation_release,
            project_dataset_version=project_dataset_version,
            upstream_database_release=upstream_database_release,
            version_mapping=mapping,
            release_id=release_id,
            source_project_root=source_project_root,
            archive_base=archive_base,
            archive_paths=archive_paths,
            keep_paths=keep_paths,
            required_active_paths=required_active_paths,
            required_file_sha256=tuple(sorted(required_file_sha256)),
            allow_internal_symlinks=(
                symlink_policy
                in {
                    "allow_internal_targets_without_dereference",
                    "allow_declared_without_dereference",
                }
            ),
            allowed_internal_symlinks=tuple(sorted(allowed_internal_symlinks)),
            exact_partition=exact_partition,
            expected_unclassified_count=expected_unclassified_count,
            active_inventory_manifest=active_inventory_manifest,
            active_inventory_manifest_sha256=active_inventory_manifest_sha256,
            active_inventory_control_paths=active_inventory_control_paths,
            variable_active_subtrees=variable_active_subtrees,
            external_evidence=tuple(external_evidence),
            raw=json.loads(json.dumps(payload)),
        )

    @classmethod
    def from_json(cls, path: Path) -> "ArchivePlan":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArchiveError(f"could not read archive manifest {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ArchiveError("archive manifest root must be a JSON object")
        return cls.from_mapping(payload)


@dataclass(frozen=True)
class InventoryEntry:
    """One deterministic inventory row."""

    relative_path: str
    entry_type: str
    size_bytes: int
    content_sha256: str
    mode: str
    mtime_ns: int
    link_target: str

    def integrity_tuple(self) -> tuple[str, str, int, str, str, str]:
        return (
            self.relative_path,
            self.entry_type,
            self.size_bytes,
            self.content_sha256,
            self.mode,
            self.link_target,
        )


def _stable_file_sha256(path: Path) -> tuple[int, str, os.stat_result]:
    before = os.lstat(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    after = os.lstat(path)
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise ArchiveError(f"file changed while it was hashed: {path}")
    return before.st_size, digest.hexdigest(), before


def _scan_path(
    absolute_path: Path,
    relative_path: PurePosixPath,
    output: list[InventoryEntry],
) -> None:
    before = os.lstat(absolute_path)
    mode = stat.S_IMODE(before.st_mode)
    common = {
        "relative_path": relative_path.as_posix(),
        "mode": f"0o{mode:04o}",
        "mtime_ns": before.st_mtime_ns,
    }
    if stat.S_ISLNK(before.st_mode):
        target = os.readlink(absolute_path)
        target_bytes = os.fsencode(target)
        after = os.lstat(absolute_path)
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (
            after.st_ino,
            after.st_mtime_ns,
            after.st_size,
        ):
            raise ArchiveError(f"symbolic link changed while it was inventoried: {absolute_path}")
        output.append(
            InventoryEntry(
                entry_type="symlink",
                size_bytes=len(target_bytes),
                content_sha256=hashlib.sha256(b"symlink\0" + target_bytes).hexdigest(),
                link_target=target,
                **common,
            )
        )
        return
    if stat.S_ISREG(before.st_mode):
        size, digest, stable_stat = _stable_file_sha256(absolute_path)
        output.append(
            InventoryEntry(
                entry_type="file",
                size_bytes=size,
                content_sha256=digest,
                mode=f"0o{stat.S_IMODE(stable_stat.st_mode):04o}",
                mtime_ns=stable_stat.st_mtime_ns,
                relative_path=relative_path.as_posix(),
                link_target="",
            )
        )
        return
    if stat.S_ISDIR(before.st_mode):
        output.append(
            InventoryEntry(
                entry_type="directory",
                size_bytes=0,
                content_sha256="",
                link_target="",
                **common,
            )
        )
        try:
            children = sorted(absolute_path.iterdir(), key=lambda item: os.fsencode(item.name))
        except OSError as exc:
            raise ArchiveError(f"could not enumerate directory {absolute_path}: {exc}") from exc
        for child in children:
            _scan_path(child, relative_path / child.name, output)
        after = os.lstat(absolute_path)
        stable_fields = ("st_dev", "st_ino", "st_mode", "st_mtime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
            raise ArchiveError(f"directory changed while it was inventoried: {absolute_path}")
        return
    raise ArchiveError(f"unsupported special filesystem entry: {absolute_path}")


def build_inventory(
    root: Path,
    relative_paths: Sequence[PurePosixPath] | None = None,
) -> tuple[InventoryEntry, ...]:
    """Hash a full tree or a set of explicit paths without following symbolic links."""

    root = _lexical_absolute(root)
    if not root.is_dir() or root.is_symlink():
        raise ArchiveError(f"inventory root must be a real directory: {root}")
    output: list[InventoryEntry] = []
    if relative_paths is None:
        before = os.lstat(root)
        children = sorted(root.iterdir(), key=lambda item: os.fsencode(item.name))
        for child in children:
            _scan_path(child, PurePosixPath(child.name), output)
        after = os.lstat(root)
        stable_fields = ("st_dev", "st_ino", "st_mode", "st_mtime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
            raise ArchiveError(f"inventory root changed while it was scanned: {root}")
    else:
        for relative_path in sorted(relative_paths, key=lambda item: os.fsencode(item.as_posix())):
            absolute_path = root.joinpath(*relative_path.parts)
            if not os.path.lexists(absolute_path):
                raise ArchiveError(f"planned path does not exist: {relative_path}")
            _scan_path(absolute_path, relative_path, output)
    return tuple(sorted(output, key=lambda entry: os.fsencode(entry.relative_path)))


def render_inventory(entries: Sequence[InventoryEntry]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(_INVENTORY_HEADER)
    for entry in entries:
        writer.writerow(
            (
                entry.relative_path,
                entry.entry_type,
                entry.size_bytes,
                entry.content_sha256,
                entry.mode,
                entry.mtime_ns,
                entry.link_target,
            )
        )
    return buffer.getvalue().encode("utf-8")


def parse_inventory(data: bytes, context: str) -> tuple[InventoryEntry, ...]:
    """Parse a deterministic inventory TSV and reject malformed or duplicate rows."""

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArchiveError(f"{context} is not valid UTF-8: {exc}") from exc
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t")
    try:
        header = tuple(next(reader))
    except StopIteration as exc:
        raise ArchiveError(f"{context} is empty") from exc
    if header != _INVENTORY_HEADER:
        raise ArchiveError(f"{context} has an invalid inventory header")
    entries: list[InventoryEntry] = []
    observed_paths: set[str] = set()
    for line_number, row in enumerate(reader, start=2):
        if len(row) != len(_INVENTORY_HEADER):
            raise ArchiveError(
                f"{context} line {line_number} has {len(row)} fields; expected 7"
            )
        relative_text, entry_type, size_text, digest, mode, mtime_text, target = row
        relative = _normalize_relative_path(relative_text, context).as_posix()
        if relative in observed_paths:
            raise ArchiveError(f"{context} has duplicate path: {relative}")
        if entry_type not in {"file", "directory", "symlink"}:
            raise ArchiveError(
                f"{context} line {line_number} has invalid entry_type {entry_type!r}"
            )
        try:
            size = int(size_text)
            mtime_ns = int(mtime_text)
        except ValueError as exc:
            raise ArchiveError(
                f"{context} line {line_number} has a non-integer size or mtime"
            ) from exc
        if size < 0 or mtime_ns < 0:
            raise ArchiveError(
                f"{context} line {line_number} has a negative size or mtime"
            )
        if not re.fullmatch(r"0o[0-7]{4}", mode):
            raise ArchiveError(f"{context} line {line_number} has invalid mode {mode!r}")
        if entry_type == "directory":
            if size != 0 or digest or target:
                raise ArchiveError(
                    f"{context} line {line_number} has invalid directory fields"
                )
        else:
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ArchiveError(
                    f"{context} line {line_number} has an invalid content SHA-256"
                )
            if entry_type == "file" and target:
                raise ArchiveError(
                    f"{context} line {line_number} gives a link target for a file"
                )
        observed_paths.add(relative)
        entries.append(
            InventoryEntry(
                relative_path=relative,
                entry_type=entry_type,
                size_bytes=size,
                content_sha256=digest,
                mode=mode,
                mtime_ns=mtime_ns,
                link_target=target,
            )
        )
    if not entries:
        raise ArchiveError(f"{context} contains no inventory entries")
    ordered = tuple(sorted(entries, key=lambda entry: os.fsencode(entry.relative_path)))
    if tuple(entries) != ordered:
        raise ArchiveError(f"{context} rows are not bytewise path-sorted")
    return ordered


def inventory_sha256(entries: Sequence[InventoryEntry]) -> str:
    return hashlib.sha256(render_inventory(entries)).hexdigest()


def retained_active_inventory(
    entries: Sequence[InventoryEntry],
    plan: ArchivePlan,
) -> tuple[InventoryEntry, ...]:
    """Return the immutable retained inventory, excluding archive, control and `.git`."""

    excluded_roots = (
        *plan.archive_paths,
        *plan.active_inventory_control_paths,
        *plan.variable_active_subtrees,
    )
    return tuple(
        entry
        for entry in entries
        if not any(
            _path_is_at_or_below(PurePosixPath(entry.relative_path), root)
            for root in excluded_roots
        )
    )


def build_active_inventory_candidate(
    project_root: Path,
    plan: ArchivePlan,
) -> tuple[InventoryEntry, ...]:
    """Build, but do not trust or bind, a candidate exact retained-tree inventory."""

    if plan.schema_version != 2 or not plan.exact_partition:
        raise ArchiveError("active inventory candidates require a schema-v2 exact plan")
    project_root = _lexical_absolute(project_root)
    if not project_root.is_dir() or project_root.is_symlink():
        raise ArchiveError(f"project root must be a real directory: {project_root}")
    for path in (*plan.keep_paths, *plan.required_active_paths, *plan.archive_paths):
        if not os.path.lexists(project_root.joinpath(*path.parts)):
            raise ArchiveError(f"candidate inventory planned path does not exist: {path}")
    full_inventory = build_inventory(project_root)
    classification = classify_inventory(
        full_inventory,
        plan.keep_paths,
        plan.archive_paths,
    )
    if classification["unclassified_count"] != 0:
        raise ArchiveError(
            f"candidate exact partition failed: UNCLASSIFIED="
            f"{classification['unclassified_count']}; "
            f"paths={classification['unclassified_paths'][:20]}"
        )
    by_path = {entry.relative_path: entry for entry in full_inventory}
    for required_path, required_digest in plan.required_file_sha256:
        entry = by_path.get(required_path.as_posix())
        if entry is None or entry.entry_type != "file":
            raise ArchiveError(
                f"candidate required checksum path is not a file: {required_path}"
            )
        if entry.content_sha256 != required_digest:
            raise ArchiveError(
                f"candidate required checksum mismatch for {required_path}"
            )
    return retained_active_inventory(full_inventory, plan)


def write_active_inventory_candidate(
    project_root: Path,
    plan: ArchivePlan,
    output: Path,
) -> dict[str, Any]:
    """Write an untrusted candidate with O_EXCL semantics for manual review and binding."""

    if plan.active_inventory_manifest is None:
        raise ArchiveError("plan has no active_inventory_manifest")
    output = _lexical_absolute(output)
    if output != plan.active_inventory_manifest:
        raise ArchiveError(
            "candidate output must exactly equal plan.active_inventory_manifest"
        )
    if os.path.lexists(output) or os.path.lexists(output.with_suffix(output.suffix + ".sha256")):
        raise ArchiveError(f"refusing to overwrite active inventory candidate: {output}")
    entries = build_active_inventory_candidate(project_root, plan)
    data = render_inventory(entries)
    digest = hashlib.sha256(data).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    sidecar = output.with_suffix(output.suffix + ".sha256")
    try:
        with sidecar.open("xb") as handle:
            handle.write(f"{digest}  {output.name}\n".encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # The candidate remains intentionally recoverable and must be reviewed/removed manually.
        raise
    return {
        "status": "candidate_untrusted_requires_manual_review",
        "writes_performed": True,
        "moves_performed": False,
        "project_version": plan.project_version,
        "data_curation_release": plan.data_curation_release,
        "candidate": str(output),
        "candidate_sha256": digest,
        "entry_count": len(entries),
        "regular_file_bytes": sum(
            entry.size_bytes for entry in entries if entry.entry_type == "file"
        ),
        "next_step": (
            "inspect every row, then set active_inventory_manifest_sha256 in the plan "
            "to candidate_sha256; generation never edits or approves the plan"
        ),
    }


def inventory_summary(entries: Sequence[InventoryEntry]) -> dict[str, int | str]:
    return {
        "entry_count": len(entries),
        "regular_file_count": sum(entry.entry_type == "file" for entry in entries),
        "directory_count": sum(entry.entry_type == "directory" for entry in entries),
        "symlink_count": sum(entry.entry_type == "symlink" for entry in entries),
        "regular_file_bytes": sum(
            entry.size_bytes for entry in entries if entry.entry_type == "file"
        ),
        "inventory_sha256": inventory_sha256(entries),
    }


def _path_is_at_or_below(path: PurePosixPath, root: PurePosixPath) -> bool:
    return path == root or root in path.parents


def classify_inventory(
    entries: Sequence[InventoryEntry],
    active_allowlist: Sequence[PurePosixPath],
    archive_paths: Sequence[PurePosixPath],
) -> dict[str, Any]:
    """Classify every source inventory entry under an explicit project-finalization policy.

    Archive rules take precedence over active parent directories.  A directory that is only an
    ancestor of an explicit active/archive rule is structural; every other path is unclassified.
    """

    counts = {"active": 0, "archive": 0, "structural": 0, "unclassified": 0}
    unclassified_paths: list[str] = []
    planned = tuple(active_allowlist) + tuple(archive_paths)
    for entry in entries:
        path = PurePosixPath(entry.relative_path)
        if any(_path_is_at_or_below(path, root) for root in archive_paths):
            role = "archive"
        elif any(_path_is_at_or_below(path, root) for root in active_allowlist):
            role = "active"
        elif entry.entry_type == "directory" and any(path in root.parents for root in planned):
            role = "structural"
        else:
            role = "unclassified"
            unclassified_paths.append(entry.relative_path)
        counts[role] += 1
    return {
        "counts": counts,
        "unclassified_count": counts["unclassified"],
        "unclassified_paths": unclassified_paths,
    }


def _verify_external_evidence(
    evidence: Sequence[ExternalEvidence],
    archive_base: Path,
) -> tuple[VerifiedExternalEvidence, ...]:
    archive_base = _lexical_absolute(archive_base)
    if evidence and (not archive_base.is_dir() or archive_base.is_symlink()):
        raise ArchiveError(
            f"external evidence archive base must be a real directory: {archive_base}"
        )
    verified: list[VerifiedExternalEvidence] = []
    for item in evidence:
        try:
            relative = item.path.relative_to(archive_base)
        except ValueError as exc:  # defensive: the parser already enforces this boundary
            raise ArchiveError(
                f"external evidence escaped archive_base: {item.path}"
            ) from exc
        cursor = archive_base
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ArchiveError(
                    f"external evidence path contains a symbolic link: {cursor}"
                )
        if not item.path.is_file():
            raise ArchiveError(
                f"external evidence is missing or not a regular file: {item.path}"
            )
        size, observed_digest, _ = _stable_file_sha256(item.path)
        if observed_digest != item.sha256:
            raise ArchiveError(
                f"external evidence checksum mismatch for {item.evidence_id}: "
                f"expected {item.sha256}, observed {observed_digest}"
            )
        verified.append(
            VerifiedExternalEvidence(
                evidence_id=item.evidence_id,
                path=item.path,
                size_bytes=size,
                sha256=observed_digest,
                purpose=item.purpose,
            )
        )
    return tuple(verified)


def _load_bound_active_inventory(plan: ArchivePlan) -> tuple[tuple[InventoryEntry, ...], str]:
    if plan.schema_version != 2:
        return (), ""
    if plan.active_inventory_manifest is None:
        raise ArchiveError("schema-v2 plan has no active inventory manifest")
    if plan.active_inventory_manifest_sha256 == "UNBOUND":
        raise ArchiveError(
            "active inventory manifest is UNBOUND; generate and manually review the "
            "candidate, then bind its SHA-256 before dry-run or execute"
        )
    archive_base = _lexical_absolute(plan.archive_base)
    manifest = plan.active_inventory_manifest
    try:
        relative = manifest.relative_to(archive_base)
    except ValueError as exc:
        raise ArchiveError("active inventory manifest escaped archive_base") from exc
    cursor = archive_base
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ArchiveError(
                f"active inventory manifest path contains a symbolic link: {cursor}"
            )
    if not manifest.is_file():
        raise ArchiveError(f"active inventory manifest is missing: {manifest}")
    _, observed_digest, _ = _stable_file_sha256(manifest)
    if observed_digest != plan.active_inventory_manifest_sha256:
        raise ArchiveError(
            "active inventory manifest binding mismatch: "
            f"expected {plan.active_inventory_manifest_sha256}, observed {observed_digest}"
        )
    entries = parse_inventory(manifest.read_bytes(), str(manifest))
    return entries, observed_digest


def _entries_under(
    entries: Sequence[InventoryEntry],
    relative_path: PurePosixPath,
) -> tuple[InventoryEntry, ...]:
    selected = []
    for entry in entries:
        entry_path = PurePosixPath(entry.relative_path)
        if entry_path == relative_path or relative_path in entry_path.parents:
            selected.append(entry)
    return tuple(selected)


def _assert_inventory_equal(
    expected: Sequence[InventoryEntry],
    observed: Sequence[InventoryEntry],
    context: str,
) -> None:
    expected_map = {entry.relative_path: entry.integrity_tuple() for entry in expected}
    observed_map = {entry.relative_path: entry.integrity_tuple() for entry in observed}
    if expected_map == observed_map:
        return
    missing = sorted(set(expected_map) - set(observed_map))
    unexpected = sorted(set(observed_map) - set(expected_map))
    changed = sorted(
        path
        for path in set(expected_map) & set(observed_map)
        if expected_map[path] != observed_map[path]
    )
    raise ArchiveError(
        f"{context} inventory mismatch; missing={missing[:5]}, "
        f"unexpected={unexpected[:5]}, changed={changed[:5]}"
    )


@dataclass(frozen=True)
class PreparedArchive:
    plan: ArchivePlan
    project_root: Path
    full_inventory: tuple[InventoryEntry, ...]
    archive_inventory: tuple[InventoryEntry, ...]
    classification: dict[str, Any]
    active_inventory_expected: tuple[InventoryEntry, ...]
    active_inventory_manifest_sha256: str
    verified_external_evidence: tuple[VerifiedExternalEvidence, ...]

    def dry_run_summary(self) -> dict[str, Any]:
        return {
            "status": "dry_run",
            "writes_performed": False,
            "moves_performed": False,
            "project_name": self.plan.project_name,
            "project_version": self.plan.project_version,
            "data_curation_release": self.plan.data_curation_release,
            "project_dataset_version": self.plan.project_dataset_version,
            "upstream_database_release": self.plan.upstream_database_release,
            "version_mapping": self.plan.version_mapping,
            "frozen_dataset_contract": self.plan.raw.get("frozen_dataset_contract", {}),
            "evidence_scope": self.plan.raw.get("evidence_scope", {}),
            "release_id": self.plan.release_id,
            "project_root": str(self.project_root),
            "planned_release": str(self.plan.archive_base / self.plan.release_id),
            "archive_paths": [path.as_posix() for path in self.plan.archive_paths],
            "active_allowlist": [path.as_posix() for path in self.plan.keep_paths],
            "keep_paths": [path.as_posix() for path in self.plan.keep_paths],
            "required_active_paths": [
                path.as_posix() for path in self.plan.required_active_paths
            ],
            "classification_policy": (
                "exact_partition" if self.plan.exact_partition else "legacy_keep_guards"
            ),
            "classification": self.classification,
            "UNCLASSIFIED": self.classification["unclassified_count"],
            "exact_active_inventory": {
                "manifest": str(self.plan.active_inventory_manifest),
                "manifest_sha256": self.active_inventory_manifest_sha256,
                "entry_count": len(self.active_inventory_expected),
                "variable_active_subtrees": [
                    path.as_posix() for path in self.plan.variable_active_subtrees
                ],
                "control_paths": [
                    path.as_posix()
                    for path in self.plan.active_inventory_control_paths
                ],
                "verified": bool(self.active_inventory_expected),
            },
            "required_file_sha256_count": len(self.plan.required_file_sha256),
            "external_evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "path": str(item.path),
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                    "purpose": item.purpose,
                    "verified": True,
                }
                for item in self.verified_external_evidence
            ],
            "external_evidence_verified_count": len(self.verified_external_evidence),
            "symlink_policy": self.plan.raw.get("symlink_policy", "reject_all"),
            "source_tree_before": inventory_summary(self.full_inventory),
            "archive_payload_expected": inventory_summary(self.archive_inventory),
        }


def prepare_archive(project_root: Path, plan: ArchivePlan) -> PreparedArchive:
    """Create the read-only preflight inventory used by dry-run and execute modes."""

    project_root = _lexical_absolute(project_root)
    if not project_root.is_dir() or project_root.is_symlink():
        raise ArchiveError(f"project root must be a real directory: {project_root}")
    for kept in plan.keep_paths:
        if not os.path.lexists(project_root.joinpath(*kept.parts)):
            raise ArchiveError(f"required keep path does not exist: {kept}")
    for required_active in plan.required_active_paths:
        if not os.path.lexists(project_root.joinpath(*required_active.parts)):
            raise ArchiveError(
                f"required active path does not exist: {required_active}"
            )

    full_inventory = build_inventory(project_root)
    full_inventory_by_path = {entry.relative_path: entry for entry in full_inventory}
    for required_path, required_digest in plan.required_file_sha256:
        entry = full_inventory_by_path.get(required_path.as_posix())
        if entry is None or entry.entry_type != "file":
            raise ArchiveError(f"required checksum path is not a regular file: {required_path}")
        if entry.content_sha256 != required_digest:
            raise ArchiveError(
                f"required checksum mismatch for {required_path}: "
                f"expected {required_digest}, observed {entry.content_sha256}"
            )
    archive_inventory = build_inventory(project_root, plan.archive_paths)
    classification = classify_inventory(
        full_inventory,
        plan.keep_paths,
        plan.archive_paths,
    )
    if plan.exact_partition and (
        classification["unclassified_count"] != plan.expected_unclassified_count
    ):
        raise ArchiveError(
            f"exact partition failed: UNCLASSIFIED={classification['unclassified_count']} "
            f"(expected {plan.expected_unclassified_count}); "
            f"paths={classification['unclassified_paths'][:20]}"
        )
    active_inventory_expected, active_inventory_manifest_digest = (
        _load_bound_active_inventory(plan)
    )
    current_retained_inventory = retained_active_inventory(full_inventory, plan)
    if plan.exact_partition:
        _assert_inventory_equal(
            active_inventory_expected,
            current_retained_inventory,
            "exact retained active inventory",
        )
    verified_external_evidence = _verify_external_evidence(
        plan.external_evidence,
        plan.archive_base,
    )
    symlinks = [entry.relative_path for entry in archive_inventory if entry.entry_type == "symlink"]
    if symlinks and not plan.allow_internal_symlinks:
        raise ArchiveError(
            "archive paths contain symbolic links; materialize or explicitly resolve them first: "
            + ", ".join(symlinks[:5])
        )
    if symlinks:
        observed_symlinks = set(symlinks)
        allowed_symlinks = dict(plan.allowed_internal_symlinks)
        allowed_paths = {path.as_posix() for path in allowed_symlinks}
        if observed_symlinks != allowed_paths:
            raise ArchiveError(
                "archived symbolic links do not exactly match allowed_internal_symlinks; "
                f"unexpected={sorted(observed_symlinks - allowed_paths)}, "
                f"missing={sorted(allowed_paths - observed_symlinks)}"
            )
        for relative_path_text in symlinks:
            relative_path = PurePosixPath(relative_path_text)
            link_path = project_root.joinpath(*relative_path.parts)
            target_text = os.readlink(link_path)
            expected_target = allowed_symlinks[relative_path]
            if target_text != expected_target:
                raise ArchiveError(
                    "archived symbolic link target text changed: "
                    f"{relative_path}; expected {expected_target!r}, observed {target_text!r}"
                )
            if (
                plan.raw.get("symlink_policy")
                == "allow_internal_targets_without_dereference"
            ):
                canonical_root = Path(os.path.realpath(project_root))
                canonical_archive_roots = tuple(
                    Path(os.path.realpath(project_root.joinpath(*path.parts)))
                    for path in plan.archive_paths
                )
                target_path = Path(target_text)
                if not target_path.is_absolute():
                    target_path = link_path.parent / target_path
                canonical_target = Path(os.path.realpath(target_path))
                if (
                    canonical_target != canonical_root
                    and canonical_root not in canonical_target.parents
                ):
                    raise ArchiveError(
                        "archived symbolic link resolves outside the project root: "
                        f"{relative_path} -> {target_text}"
                    )
                if not any(
                    canonical_target == archive_root
                    or archive_root in canonical_target.parents
                    for archive_root in canonical_archive_roots
                ):
                    raise ArchiveError(
                        "archived symbolic link resolves outside the archive boundary: "
                        f"{relative_path} -> {target_text}"
                    )
    expected_from_full: list[InventoryEntry] = []
    for path in plan.archive_paths:
        expected_from_full.extend(_entries_under(full_inventory, path))
    _assert_inventory_equal(expected_from_full, archive_inventory, "preflight source")
    return PreparedArchive(
        plan=plan,
        project_root=project_root,
        full_inventory=full_inventory,
        archive_inventory=archive_inventory,
        classification=classification,
        active_inventory_expected=active_inventory_expected,
        active_inventory_manifest_sha256=active_inventory_manifest_digest,
        verified_external_evidence=verified_external_evidence,
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    with temporary.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, _json_bytes(payload))


def _write_json_with_sha256(path: Path, payload: dict[str, Any]) -> str:
    data = _json_bytes(payload)
    digest = hashlib.sha256(data).hexdigest()
    _atomic_write(path, data)
    _atomic_write(
        path.with_suffix(path.suffix + ".sha256"),
        f"{digest}  {path.name}\n".encode("utf-8"),
    )
    return digest


def _write_inventory(path: Path, entries: Sequence[InventoryEntry]) -> str:
    payload = render_inventory(entries)
    digest = hashlib.sha256(payload).hexdigest()
    _atomic_write(path, payload)
    _atomic_write(path.with_suffix(path.suffix + ".sha256"), f"{digest}  {path.name}\n".encode())
    return digest


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            raise ArchiveError(f"no existing ancestor for archive base: {path}")
        candidate = candidate.parent
    return candidate


def _paths_are_disjoint(left: Path, right: Path) -> bool:
    left = _lexical_absolute(left)
    right = _lexical_absolute(right)
    return left != right and left not in right.parents and right not in left.parents


def _atomic_noreplace_mechanism() -> str:
    """Return the preferred no-overwrite publication policy available on this host."""

    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        return (
            "renameat2(RENAME_NOREPLACE); "
            "unsupported-filesystem fallback=flock(parent-directories)+atomic rename"
        )
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        return "renamex_np(RENAME_EXCL)"
    raise ArchiveError(
        "this host has no supported atomic no-overwrite rename primitive; "
        "copy/delete and check-then-rename fallbacks are disabled"
    )


def _flock_rename_noreplace(source: Path, target: Path) -> str:
    """Rename under cooperative parent-directory locks when a filesystem lacks renameat2.

    Lustre can expose the Linux renameat2 symbol while returning EINVAL for
    RENAME_NOREPLACE.  We lock both parent directory inodes in deterministic order,
    re-check that the target is absent while holding those locks, and then use the
    filesystem's atomic rename.  All project archive writers use this helper, and the
    formal precondition separately requires that unrelated writers are stopped.
    """

    source = _lexical_absolute(source)
    target = _lexical_absolute(target)
    parent_paths = sorted({source.parent, target.parent}, key=os.fspath)
    descriptors: list[int] = []
    try:
        for parent in parent_paths:
            descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            descriptors.append(descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        if not os.path.lexists(source):
            raise ArchiveError(f"rename source disappeared while locked: {source}")
        if os.path.lexists(target):
            raise ArchiveError(f"refusing to overwrite existing rename target: {target}")
        try:
            os.rename(source, target)
        except OSError as exc:
            raise ArchiveError(
                "parent-locked atomic rename failed for "
                f"{source} -> {target}: [errno {exc.errno}] {exc.strerror}"
            ) from exc
        if os.path.lexists(source) or not os.path.lexists(target):
            raise ArchiveError(
                f"parent-locked rename postcondition failed: {source} -> {target}"
            )
        return "flock(parent-directories)+atomic rename(target absent under lock)"
    finally:
        for descriptor in reversed(descriptors):
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _atomic_rename_noreplace(source: Path, target: Path) -> str:
    """Atomically rename source to an absent target, with overwrite prohibited by the kernel."""

    mechanism = _atomic_noreplace_mechanism()
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    ctypes.set_errno(0)
    if mechanism.startswith("flock("):
        return _flock_rename_noreplace(source, target)
    if mechanism.startswith("renameat2"):
        renameat2 = libc.renameat2
        renameat2.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, source_bytes, -100, target_bytes, 1)
    else:
        renamex_np = libc.renamex_np
        renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        renamex_np.restype = ctypes.c_int
        # Darwin's RENAME_EXCL is 0x00000004.
        result = renamex_np(source_bytes, target_bytes, 0x00000004)
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise ArchiveError(f"refusing to overwrite existing rename target: {target}")
        if mechanism.startswith("renameat2") and error_number in {
            errno.EINVAL,
            errno.ENOSYS,
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }:
            return _flock_rename_noreplace(source, target)
        raise ArchiveError(
            f"atomic no-overwrite rename failed ({mechanism}) for {source} -> {target}: "
            f"[errno {error_number}] {os.strerror(error_number)}"
        )
    return mechanism


def _external_evidence_payload(
    evidence: Sequence[VerifiedExternalEvidence],
) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": item.evidence_id,
            "path": str(item.path),
            "size_bytes": item.size_bytes,
            "sha256": item.sha256,
            "purpose": item.purpose,
            "verified": True,
        }
        for item in evidence
    ]


def _restore_plan_payload(
    prepared: PreparedArchive,
    final_release: Path,
    stage: Path,
) -> dict[str, Any]:
    moves = []
    for relative_path in reversed(prepared.plan.archive_paths):
        moves.append(
            {
                "relative_path": relative_path.as_posix(),
                "from": str(
                    final_release / "05_archived_paths" / Path(*relative_path.parts)
                ),
                "from_if_interrupted_in_staging": str(
                    stage / "05_archived_paths" / Path(*relative_path.parts)
                ),
                "to": str(prepared.project_root / Path(*relative_path.parts)),
                "required_target_state": "absent",
                "mechanism": _atomic_noreplace_mechanism(),
            }
        )
    return {
        "schema_version": 1,
        "release_id": prepared.plan.release_id,
        "project_version": prepared.plan.project_version,
        "data_curation_release": prepared.plan.data_curation_release,
        "source_project_root": str(prepared.project_root),
        "archive_release": str(final_release),
        "staging_path": str(stage),
        "restore_order": "reverse_archive_order",
        "automatic_restore_execution": False,
        "deletion_required": False,
        "preconditions": [
            "stop all writers to both trees",
            "verify archive_payload_verified.tsv and its SHA-256 sidecar",
            "require every restore target to be absent",
            "use kernel atomic no-overwrite rename only",
            "verify each restored subtree against archive_payload_expected.tsv",
        ],
        "moves": moves,
    }


def _journal_payload(
    prepared: PreparedArchive,
    status: str,
    moved: Iterable[PurePosixPath],
    stage: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_utc": _utc_now(),
        "status": status,
        "release_id": prepared.plan.release_id,
        "source_project_root": str(prepared.project_root),
        "stage_path": str(stage),
        "planned_paths": [path.as_posix() for path in prepared.plan.archive_paths],
        "moved_paths": [path.as_posix() for path in moved],
        "recovery_rule": (
            "rename each moved path back to an absent source with a kernel no-overwrite "
            "primitive; never delete staging"
        ),
    }


def _rollback_moves(
    prepared: PreparedArchive,
    container: Path,
    moved: Sequence[PurePosixPath],
) -> list[str]:
    errors: list[str] = []
    payload_root = container / "05_archived_paths"
    for relative_path in reversed(moved):
        archived = payload_root.joinpath(*relative_path.parts)
        source = prepared.project_root.joinpath(*relative_path.parts)
        try:
            if not os.path.lexists(archived):
                raise ArchiveError(f"rollback target is missing: {archived}")
            if os.path.lexists(source):
                raise ArchiveError(f"rollback source is unexpectedly occupied: {source}")
            source.parent.mkdir(parents=True, exist_ok=True)
            _atomic_rename_noreplace(archived, source)
            expected = _entries_under(prepared.archive_inventory, relative_path)
            observed = build_inventory(prepared.project_root, (relative_path,))
            _assert_inventory_equal(expected, observed, f"rollback {relative_path}")
        except BaseException as exc:  # rollback must report KeyboardInterrupt/SystemExit too
            errors.append(f"{relative_path}: {type(exc).__name__}: {exc}")
    return errors


def execute_archive(prepared: PreparedArchive, archive_base: Path) -> Path:
    """Execute a checksum-verified, same-filesystem move and return the final release path."""

    archive_base = _lexical_absolute(archive_base)
    rename_mechanism = _atomic_noreplace_mechanism()
    if not _paths_are_disjoint(prepared.project_root, archive_base):
        raise ArchiveError("archive base and project root must be disjoint sibling trees")
    if archive_base.is_symlink() or (archive_base.exists() and not archive_base.is_dir()):
        raise ArchiveError(f"archive base must be a real directory: {archive_base}")
    existing_parent = _nearest_existing_parent(archive_base)
    if prepared.project_root.stat().st_dev != existing_parent.stat().st_dev:
        raise ArchiveError(
            "project and archive base are on different filesystems; copy-and-delete fallback "
            "is intentionally disabled"
        )

    final_release = archive_base / prepared.plan.release_id
    if os.path.lexists(final_release):
        raise ArchiveError(f"versioned release already exists: {final_release}")

    current_full_inventory = build_inventory(prepared.project_root)
    _assert_inventory_equal(
        prepared.full_inventory,
        current_full_inventory,
        "complete source tree immediately before execute",
    )
    current_archive = build_inventory(prepared.project_root, prepared.plan.archive_paths)
    _assert_inventory_equal(
        prepared.archive_inventory,
        current_archive,
        "source immediately before execute",
    )
    current_external_evidence = _verify_external_evidence(
        prepared.plan.external_evidence,
        prepared.plan.archive_base,
    )
    if current_external_evidence != prepared.verified_external_evidence:
        raise ArchiveError("external evidence identity changed after archive preflight")
    current_active_expected, current_active_binding = _load_bound_active_inventory(
        prepared.plan
    )
    if (
        current_active_expected != prepared.active_inventory_expected
        or current_active_binding != prepared.active_inventory_manifest_sha256
    ):
        raise ArchiveError("bound exact active inventory changed after archive preflight")

    try:
        archive_base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchiveError(f"could not create archive base {archive_base}: {exc}") from exc
    stale_stages = sorted(archive_base.glob(f".{prepared.plan.release_id}.staging-*"))
    if stale_stages:
        raise ArchiveError(
            "an earlier staging directory requires manual inspection before retry: "
            + ", ".join(str(path) for path in stale_stages)
        )
    stage = archive_base / f".{prepared.plan.release_id}.staging-{uuid.uuid4().hex}"
    manifest_dir = stage / "00_manifest"
    payload_root = stage / "05_archived_paths"
    try:
        stage.mkdir(parents=False, exist_ok=False)
        manifest_dir.mkdir()
        payload_root.mkdir()
    except OSError as exc:
        raise ArchiveError(f"could not create archive staging tree {stage}: {exc}") from exc

    moved: list[PurePosixPath] = []
    container = stage
    source_inventory_digest = ""
    payload_inventory_digest = ""
    restore_plan_digest = ""
    try:
        source_inventory_digest = _write_inventory(
            manifest_dir / "source_tree_before.tsv", prepared.full_inventory
        )
        payload_inventory_digest = _write_inventory(
            manifest_dir / "archive_payload_expected.tsv", prepared.archive_inventory
        )
        _write_json(manifest_dir / "archive_plan.json", prepared.plan.raw)
        restore_plan_digest = _write_json_with_sha256(
            manifest_dir / "restore_plan.json",
            _restore_plan_payload(prepared, final_release, stage),
        )
        _write_json(
            manifest_dir / "journal.json",
            _journal_payload(prepared, "preflight_complete", moved, stage),
        )

        for relative_path in prepared.plan.archive_paths:
            source = prepared.project_root.joinpath(*relative_path.parts)
            target = payload_root.joinpath(*relative_path.parts)
            if os.path.lexists(target):
                raise ArchiveError(f"archive target already exists: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_rename_noreplace(source, target)
            moved.append(relative_path)
            _write_json(
                manifest_dir / "journal.json",
                _journal_payload(prepared, "moving_and_verifying", moved, stage),
            )
            expected = _entries_under(prepared.archive_inventory, relative_path)
            observed = build_inventory(payload_root, (relative_path,))
            _assert_inventory_equal(expected, observed, f"target {relative_path}")

        payload_inventory = build_inventory(payload_root, prepared.plan.archive_paths)
        _assert_inventory_equal(
            prepared.archive_inventory,
            payload_inventory,
            "complete staged payload",
        )
        payload_inventory_digest = _write_inventory(
            manifest_dir / "archive_payload_verified.tsv", payload_inventory
        )
        remaining_inventory = build_inventory(prepared.project_root)
        remaining_inventory_digest = _write_inventory(
            manifest_dir / "source_tree_after.tsv", remaining_inventory
        )
        for kept in prepared.plan.keep_paths:
            if not os.path.lexists(prepared.project_root.joinpath(*kept.parts)):
                raise ArchiveError(f"keep path disappeared during archive: {kept}")
        for required_active in prepared.plan.required_active_paths:
            if not os.path.lexists(
                prepared.project_root.joinpath(*required_active.parts)
            ):
                raise ArchiveError(
                    f"required active path disappeared during archive: {required_active}"
                )
        remaining_classification = classify_inventory(
            remaining_inventory,
            prepared.plan.keep_paths,
            prepared.plan.archive_paths,
        )
        if prepared.plan.exact_partition:
            remaining_counts = remaining_classification["counts"]
            if remaining_classification["unclassified_count"] != 0:
                raise ArchiveError(
                    "post-move exact partition failed: "
                    f"UNCLASSIFIED={remaining_classification['unclassified_count']}"
                )
            if remaining_counts["archive"] != 0:
                raise ArchiveError(
                    "post-move exact partition still contains archive-classified entries: "
                    f"{remaining_counts['archive']}"
                )
            _assert_inventory_equal(
                prepared.active_inventory_expected,
                retained_active_inventory(remaining_inventory, prepared.plan),
                "post-move exact retained active inventory",
            )

        receipt = {
            "schema_version": 1,
            "status": "staged_verified",
            "created_utc": _utc_now(),
            "project_name": prepared.plan.project_name,
            "project_version": prepared.plan.project_version,
            "data_curation_release": prepared.plan.data_curation_release,
            "project_dataset_version": prepared.plan.project_dataset_version,
            "upstream_database_release": prepared.plan.upstream_database_release,
            "version_mapping": prepared.plan.version_mapping,
            "frozen_dataset_contract": prepared.plan.raw.get("frozen_dataset_contract", {}),
            "evidence_scope": prepared.plan.raw.get("evidence_scope", {}),
            "symlink_policy": prepared.plan.raw.get("symlink_policy", "reject_all"),
            "archived_symlink_count": sum(
                entry.entry_type == "symlink" for entry in prepared.archive_inventory
            ),
            "release_id": prepared.plan.release_id,
            "source_project_root": str(prepared.project_root),
            "archive_release": str(final_release),
            "move_mechanism": rename_mechanism,
            "overwrite_allowed": False,
            "copy_delete_fallback": False,
            "deletion_performed": False,
            "source_tree_before_inventory_sha256": source_inventory_digest,
            "archive_payload_inventory_sha256": payload_inventory_digest,
            "source_tree_after_inventory_sha256": remaining_inventory_digest,
            "classification_policy": (
                "exact_partition"
                if prepared.plan.exact_partition
                else "legacy_keep_guards"
            ),
            "classification_before": prepared.classification,
            "classification_after": remaining_classification,
            "UNCLASSIFIED": remaining_classification["unclassified_count"],
            "exact_active_inventory": {
                "manifest": str(prepared.plan.active_inventory_manifest),
                "manifest_sha256": prepared.active_inventory_manifest_sha256,
                "entry_count": len(prepared.active_inventory_expected),
                "variable_active_subtrees": [
                    path.as_posix()
                    for path in prepared.plan.variable_active_subtrees
                ],
                "control_paths": [
                    path.as_posix()
                    for path in prepared.plan.active_inventory_control_paths
                ],
                "verified_before_and_after": True,
            },
            "archived_paths": [path.as_posix() for path in prepared.plan.archive_paths],
            "active_allowlist": [path.as_posix() for path in prepared.plan.keep_paths],
            "required_active_paths": [
                path.as_posix() for path in prepared.plan.required_active_paths
            ],
            "external_evidence": _external_evidence_payload(
                current_external_evidence
            ),
            "external_evidence_verified": True,
            "restore_plan": "00_manifest/restore_plan.json",
            "restore_plan_sha256": restore_plan_digest,
            "source_and_target_sha_verified": True,
        }
        _write_json_with_sha256(manifest_dir / "execution_receipt.json", receipt)
        _write_json(
            manifest_dir / "journal.json",
            _journal_payload(prepared, "staged_verified", moved, stage),
        )

        _atomic_rename_noreplace(stage, final_release)
        container = final_release
        final_payload_root = final_release / "05_archived_paths"
        final_inventory = build_inventory(final_payload_root, prepared.plan.archive_paths)
        _assert_inventory_equal(
            prepared.archive_inventory,
            final_inventory,
            "final versioned release",
        )
        for relative_path in prepared.plan.archive_paths:
            if os.path.lexists(prepared.project_root.joinpath(*relative_path.parts)):
                raise ArchiveError(f"source path still exists after atomic move: {relative_path}")

        receipt["status"] = "complete"
        receipt["completed_utc"] = _utc_now()
        receipt["final_target_verified"] = True
        _write_json_with_sha256(
            final_release / "00_manifest" / "execution_receipt.json",
            receipt,
        )
        _write_json(
            final_release / "00_manifest" / "journal.json",
            _journal_payload(prepared, "complete", moved, final_release),
        )
        return final_release
    except BaseException as exc:
        rollback_errors = _rollback_moves(prepared, container, moved)
        failure_payload = {
            "schema_version": 1,
            "status": "failed_rolled_back" if not rollback_errors else "failed_needs_recovery",
            "failed_utc": _utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "moved_paths_before_rollback": [path.as_posix() for path in moved],
            "rollback_errors": rollback_errors,
            "instruction": "Do not delete this directory; inspect inventories and journal.",
        }
        try:
            _write_json(container / "00_manifest" / "FAILURE.json", failure_payload)
        except BaseException:
            pass
        if rollback_errors:
            raise ArchiveError(
                f"archive failed and rollback is incomplete: {exc}; "
                + "; ".join(rollback_errors)
            ) from exc
        raise ArchiveError(f"archive failed; all moved paths were rolled back: {exc}") from exc
