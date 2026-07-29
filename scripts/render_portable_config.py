#!/usr/bin/env python3
"""Render a local runtime config without modifying frozen provenance configs.

The checked-in V0 configs record the absolute gds2 paths used for the frozen
analyses.  Those strings are scientific provenance and therefore stay
byte-for-byte unchanged.  This helper rewrites only a generated copy for a
different checkout/storage layout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


LEGACY_PROJECT_ROOT = "/aptmp/hongda/DJR-MCP-Finder"
LEGACY_ARCHIVE_ROOT = "/aptmp/hongda/DJRMCP_Develope"
LEGACY_DATABASE_ROOT = "/aptmp/hongda/database"
LEGACY_SOFTWARE_ROOT = "/usr/appli/freeware"

ENVIRONMENT_MAPPINGS = (
    (LEGACY_PROJECT_ROOT, "DJRMCP_PROJECT_ROOT"),
    (LEGACY_ARCHIVE_ROOT, "DJRMCP_ARCHIVE_ROOT"),
    (LEGACY_DATABASE_ROOT, "DJRMCP_DATABASE_ROOT"),
    (LEGACY_SOFTWARE_ROOT, "DJRMCP_SOFTWARE_ROOT"),
)

# This value is part of the schema-5 exact numerical-replay attestation.  It is
# evidence about the historical runtime, not a path used to locate a movable
# input.  Rewriting it would make the generated config claim a run that did not
# occur.  Full Amendment-D exact replay consequently still requires the frozen
# environment at its attested location; compact-result inspection does not.
PROVENANCE_ONLY_FIELDS = {
    ("legacy_schema4_numerical_operator", "venv_root"),
}


class RenderError(RuntimeError):
    """Raised when a portable config cannot be produced safely."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _absolute_target(value: str, *, label: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute() or path == Path("/"):
        raise RenderError(f"{label} must be a non-root absolute path: {value!r}")
    return os.path.abspath(os.fspath(path))


def parse_mapping(value: str) -> tuple[str, str]:
    source, separator, target = value.partition("=")
    if not separator or not source or not target:
        raise argparse.ArgumentTypeError("path mappings must use OLD_ABSOLUTE=NEW_ABSOLUTE")
    if not Path(source).is_absolute() or source == "/":
        raise argparse.ArgumentTypeError(
            f"mapping source must be a non-root absolute path: {source!r}"
        )
    try:
        normalized_target = _absolute_target(target, label="mapping target")
    except RenderError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return source.rstrip("/"), normalized_target.rstrip("/")


def environment_mappings(
    environ: Mapping[str, str], *, default_project_root: Path
) -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    for source, variable in ENVIRONMENT_MAPPINGS:
        raw = environ.get(variable)
        if raw:
            target = _absolute_target(raw, label=variable)
        elif variable == "DJRMCP_PROJECT_ROOT":
            target = os.path.abspath(os.fspath(default_project_root))
        else:
            continue
        mappings.append((source, target.rstrip("/")))
    return mappings


def normalize_mappings(
    defaults: Iterable[tuple[str, str]], overrides: Iterable[tuple[str, str]]
) -> tuple[tuple[str, str], ...]:
    """Return deterministic longest-prefix-first mappings.

    Explicit ``--map`` values replace environment-derived mappings with the
    same source.  Longest-prefix matching prevents the archive/database roots
    from being swallowed by a broader site-root rule.
    """

    merged: dict[str, str] = {}
    for source, target in (*tuple(defaults), *tuple(overrides)):
        merged[source.rstrip("/")] = target.rstrip("/")
    return tuple(sorted(merged.items(), key=lambda item: (-len(item[0]), item[0])))


def remap_string(value: str, mappings: Sequence[tuple[str, str]]) -> str:
    for source, target in mappings:
        if value == source:
            return target
        if value.startswith(source + "/"):
            return target + value[len(source) :]
    return value


def remap_value(
    value: Any,
    mappings: Sequence[tuple[str, str]],
    *,
    field_path: tuple[str, ...] = (),
) -> Any:
    if field_path in PROVENANCE_ONLY_FIELDS:
        return value
    if isinstance(value, dict):
        return {
            key: remap_value(
                item,
                mappings,
                field_path=field_path + (str(key),),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [remap_value(item, mappings, field_path=field_path) for item in value]
    if isinstance(value, str):
        return remap_string(value, mappings)
    return value


def _walk_strings(value: Any, field_path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, field_path + (str(key),))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, field_path + (str(index),))
    elif isinstance(value, str):
        yield field_path, value


def unmapped_legacy_paths(value: Any) -> list[tuple[str, str]]:
    legacy_prefixes = tuple(source for source, _ in ENVIRONMENT_MAPPINGS)
    unresolved: list[tuple[str, str]] = []
    for field_path, item in _walk_strings(value):
        if field_path in PROVENANCE_ONLY_FIELDS:
            continue
        if any(item == prefix or item.startswith(prefix + "/") for prefix in legacy_prefixes):
            unresolved.append((".".join(field_path), item))
    return unresolved


def _load(path: Path) -> tuple[Any, str]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8")), "json"
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RenderError("PyYAML is required to render YAML configs") from exc
        return yaml.safe_load(path.read_text(encoding="utf-8")), "yaml"
    raise RenderError(f"unsupported config extension: {path.suffix or '<none>'}")


def _serialize(value: Any, config_format: str) -> str:
    if config_format == "json":
        return json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    import yaml

    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="checked-in frozen JSON/YAML config")
    parser.add_argument("output", type=Path, help="generated local JSON/YAML config")
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        type=parse_mapping,
        metavar="OLD=NEW",
        help="additional or overriding absolute-prefix mapping (repeatable)",
    )
    parser.add_argument(
        "--allow-unmapped",
        action="store_true",
        help="write even if operational legacy roots remain (unsafe for normal runs)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input.resolve()
    destination = args.output.resolve()
    if not source.is_file():
        raise RenderError(f"config does not exist: {source}")
    if source == destination:
        raise RenderError("refusing to overwrite the checked-in frozen config")

    config, config_format = _load(source)
    if not isinstance(config, dict):
        raise RenderError("config root must be a mapping")
    mappings = normalize_mappings(
        environment_mappings(os.environ, default_project_root=repository_root()),
        args.map,
    )
    rendered = remap_value(config, mappings)

    # A generated overlay must continue to resolve its checksum-pinned base
    # relative to the original config, not relative to the generated file.
    extends = rendered.get("extends")
    if isinstance(extends, str) and extends:
        base = Path(extends)
        if not base.is_absolute():
            rendered["extends"] = str((source.parent / base).resolve())

    unresolved = unmapped_legacy_paths(rendered)
    if unresolved and not args.allow_unmapped:
        details = "\n".join(f"  {field}: {value}" for field, value in unresolved)
        raise RenderError(
            "unmapped site-specific operational paths remain; set the matching "
            "DJRMCP_*_ROOT variable or pass --map:\n" + details
        )

    _atomic_write(destination, _serialize(rendered, config_format))
    print(f"rendered {source} -> {destination}")
    for field, value in sorted(
        (field, value)
        for field, value in _walk_strings(rendered)
        if field in PROVENANCE_ONLY_FIELDS
    ):
        print(
            f"preserved provenance-only field {'.'.join(field)}={value}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
