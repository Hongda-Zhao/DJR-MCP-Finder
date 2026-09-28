#!/usr/bin/env python3
"""Train-only, component-disjoint short-sequence stress test.

Preparation requires only the Python standard library. Neural encoders and
sklearn are imported only by their respective stages. No released head is used
to score its own training fragments.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
KNOWN = ("Nucleocytoviricota", "Preplasmiviricota")
SOURCES = {"viral_vma_djr", "cellular_djr_none", "hard_non_djr", "background_non_djr"}
LENGTH_BINS = ("0-99", "100-129", "130-149", "150-199", "200-249", "250-299", "300+")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def sequence_hash(sequence):
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def read_tsv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


def read_fasta(path):
    records = {}
    current = None
    with Path(path).open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                parts = line[1:].split()
                if not parts or parts[0] in records:
                    raise ValueError("Empty or duplicate FASTA ID")
                current = parts[0]
                records[current] = ""
            else:
                if current is None:
                    raise ValueError("Sequence before FASTA header")
                records[current] += line.upper()
    if not records or any(
        not seq or set(seq) - set("ACDEFGHIKLMNPQRSTVWYX") for seq in records.values()
    ):
        raise ValueError("Empty sequence or unsupported amino acid in FASTA")
    return records


def fold_roles(evaluation, count=5, offset=1):
    calibration = (evaluation - 1 + offset) % count + 1
    if calibration == evaluation:
        raise ValueError("Calibration and evaluation folds overlap")
    return calibration, [f for f in range(1, count + 1) if f not in (evaluation, calibration)]


def config_check(config):
    if config.get("evaluation_mode", "truncation") not in {"truncation", "observed"}:
        raise ValueError("Unknown evaluation mode")
    lengths = config["lengths"]
    if (
        not lengths
        or lengths != sorted(set(lengths))
        or any(type(x) is not int or x < 1 for x in lengths)
    ):
        raise ValueError("lengths must be unique, increasing positive integers")
    if config["folds"] != 5 or config["random_replicates"] < 1:
        raise ValueError("Five folds and at least one internal fragment are required")
    if not 0 < config["classifier"]["head3_known_acceptance"] < 1:
        raise ValueError("Invalid H3 acceptance target")
    if config["bootstrap_replicates"] < 100:
        raise ValueError("At least 100 bootstrap replicates required")
    if config["methods"] != {"v0": "esmc_6b", "v01_candidate": "esm2_3b"}:
        raise ValueError("This benchmark requires the paired V0/V0.1 encoder contract")
    fold_roles(1, config["folds"], config["calibration_fold_offset"])


def fragment_windows(sequence, length, seed, parent_id, replicates):
    """0-based half-open coordinates; internal positions exclude both termini."""
    n = len(sequence)
    if length > n:
        raise ValueError("Fragment longer than its parent")
    yield "n_terminal", 0, length
    yield "c_terminal", n - length, n
    internal = list(range(1, n - length))
    key = f"{seed}|{parent_id}|{length}".encode()
    rng = random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))
    for index, start in enumerate(rng.sample(internal, min(replicates, len(internal))), 1):
        yield f"internal_{index}", start, start + length


def source_bindings(config, root):
    bindings = {}
    if digest(root / config["registry"]) != config["registry_sha256"]:
        raise ValueError("Frozen encoder registry checksum mismatch")
    if set(config["inputs"]) != {"train_manifest", "train_fasta", "fold_map"}:
        raise ValueError("Only Train manifest/FASTA and frozen component folds are accepted")
    for key, relative in config["inputs"].items():
        path = root / relative
        observed = digest(path)
        if config["expected_sha256"].get(key) != observed:
            raise ValueError(f"Frozen input checksum mismatch: {key}")
        bindings[key] = {"path": str(path.resolve()), "sha256": observed}
    return bindings


def prepare(config, root, out):
    config_check(config)
    bindings = source_bindings(config, root)
    if out.exists() and any(out.iterdir()):
        raise ValueError(
            "Run directory is not empty; use a new directory to preserve prior results"
        )
    parents = read_tsv(root / config["inputs"]["train_manifest"])
    sequences = read_fasta(root / config["inputs"]["train_fasta"])
    folds = read_tsv(root / config["inputs"]["fold_map"])
    fold_map = {r["global_component_id"]: int(r["fold"]) for r in folds}
    if len(fold_map) != len(folds) or set(fold_map.values()) != set(range(1, 6)):
        raise ValueError("Duplicate component or invalid fold map")
    ids = [r["protein_id"] for r in parents]
    if len(ids) != len(set(ids)) or set(ids) != set(sequences):
        raise ValueError("Duplicate ID or manifest/FASTA ID mismatch")
    parents.sort(key=lambda r: r["protein_id"])
    normalized = []
    full_hash_folds = defaultdict(set)
    for r in parents:
        pid, seq = r["protein_id"], sequences[r["protein_id"]]
        if r["split"] != "train":
            raise ValueError("Protected non-Train record entered benchmark")
        if sequence_hash(seq) != r["sequence_sha256"] or len(seq) != int(r["length_aa"]):
            raise ValueError(f"Sequence hash/length mismatch: {pid}")
        if r["head1_mask"] != "1" or r["head1_label"] not in {"djr", "non_djr"}:
            raise ValueError(f"Missing H1 ground truth: {pid}")
        djr = int(r["head1_label"] == "djr")
        mcp = int(r["head2_mask"] == "1" and r["head2_label"] == "viral_morphogenesis_associated")
        if djr and (
            r["head2_mask"] != "1"
            or r["head2_label"] not in {"none", "viral_morphogenesis_associated"}
        ):
            raise ValueError(f"Missing H2 ground truth: {pid}")
        if mcp > djr or r["source_dataset"] not in SOURCES:
            raise ValueError(f"Invalid source/labels: {pid}")
        h3 = r.get("head3_operational_label", "")
        h3 = h3 if mcp and r.get("head3_mask") == "1" and h3 in KNOWN else "unknown/other"
        row = {
            "protein_id": pid,
            "global_component_id": r["global_component_id"],
            "fold": fold_map[r["global_component_id"]],
            "split": "train",
            "source_dataset": r["source_dataset"],
            "family_metadata": r.get("family_metadata", ""),
            "is_djr": djr,
            "is_mcp": mcp,
            "phylum": h3,
            "length_aa": len(seq),
            "sequence_sha256": sequence_hash(seq),
            "embedding_id": "e_" + sequence_hash(seq),
        }
        normalized.append(row)
        full_hash_folds[row["sequence_sha256"]].add(row["fold"])
    if any(len(f) > 1 for f in full_hash_folds.values()):
        raise ValueError("Exact full sequences cross frozen folds")
    if {r["fold"] for r in normalized} != set(range(1, 6)):
        raise ValueError("Train cohort does not populate all five folds")
    queries, unique = [], {}
    # A fixed parent cohort gives paired absolute-length curves. All full records
    # remain available for separate descriptive observed-length strata.
    for parent_index, parent in enumerate(normalized):
        seq = sequences[parent["protein_id"]]
        eligible = config.get("evaluation_mode", "truncation") == "truncation" and len(seq) >= max(
            config["lengths"]
        )
        windows = [("full", 0, len(seq), "full")]
        if eligible:
            for length in config["lengths"]:
                windows.extend(
                    (kind, start, end, str(length))
                    for kind, start, end in fragment_windows(
                        seq,
                        length,
                        config["seed"],
                        parent["protein_id"],
                        config["random_replicates"],
                    )
                )
        for kind, start, end, length in windows:
            fragment = seq[start:end]
            sha = sequence_hash(fragment)
            eid = "e_" + sha
            unique[eid] = fragment
            queries.append(
                {
                    "sample_id": f"q{parent_index:06d}_{length}_{kind}",
                    "parent_id": parent["protein_id"],
                    "embedding_id": eid,
                    "global_component_id": parent["global_component_id"],
                    "fold": parent["fold"],
                    "source_dataset": parent["source_dataset"],
                    "is_djr": parent["is_djr"],
                    "is_mcp": parent["is_mcp"],
                    "phylum": parent["phylum"],
                    "parent_length": len(seq),
                    "length": length,
                    "length_aa": len(fragment),
                    "retained_fraction": len(fragment) / len(seq),
                    "position": kind,
                    "start": start,
                    "end": end,
                    "sequence_sha256": sha,
                    "paired_eligible": int(eligible),
                }
            )
    # New exact fragment collisions can appear despite component-disjoint parents.
    # Exclude the entire affected parent from ALL paired lengths, preserving pairing.
    hash_folds = defaultdict(set)
    for q in queries:
        hash_folds[q["sequence_sha256"]].add(q["fold"])
    collision_parents = {
        q["parent_id"] for q in queries if len(hash_folds[q["sequence_sha256"]]) > 1
    }
    for q in queries:
        q["paired_eligible"] = int(q["paired_eligible"] and q["parent_id"] not in collision_parents)
    if config.get("evaluation_mode", "truncation") == "truncation" and not any(
        q["paired_eligible"] for q in queries
    ):
        raise ValueError("No eligible paired parents after length/collision checks")
    exclusions = [
        {
            "parent_id": p["protein_id"],
            "reason": "cross_fold_exact_fragment_collision"
            if p["protein_id"] in collision_parents
            else "parent_shorter_than_max_length",
        }
        for p in normalized
        if p["protein_id"] in collision_parents or p["length_aa"] < max(config["lengths"])
    ]
    if config.get("evaluation_mode") == "observed":
        exclusions = []
    inputs = out / "inputs"
    write_tsv(inputs / "parents.tsv", normalized)
    write_tsv(inputs / "queries.tsv", queries)
    write_tsv(inputs / "paired_exclusions.tsv", exclusions, ["parent_id", "reason"])
    embedding_rows = [
        {
            "protein_id": eid,
            "sequence_sha256": sequence_hash(seq),
            "length_aa": len(seq),
            "split": "train",
        }
        for eid, seq in sorted(unique.items())
    ]
    write_tsv(inputs / "embedding_manifest.tsv", embedding_rows)
    with (inputs / "embedding.faa").open("w") as handle:
        for eid, seq in sorted(unique.items()):
            handle.write(f">{eid}\n{seq}\n")
    write_json(out / "config.json", config)
    from shutil import copyfile

    copyfile(root / config["registry"], out / "registry.yaml")
    coverage = Counter(
        (q["source_dataset"], str(q["fold"]))
        for q in queries
        if q["length"] == "full" and q["paired_eligible"]
    )
    write_tsv(
        inputs / "paired_coverage.tsv",
        [{"source_dataset": s, "fold": f, "parents": n} for (s, f), n in sorted(coverage.items())],
        ["source_dataset", "fold", "parents"],
    )
    bound = [*inputs.iterdir(), out / "config.json", out / "registry.yaml"]
    receipt = {
        "status": "PASS",
        "scope": "TRAIN_ONLY_INTERNAL_CROSSFIT",
        "benchmark_id": config["benchmark_id"],
        "source_inputs": bindings,
        "script_sha256": digest(Path(__file__)),
        "files": {str(p.relative_to(out)): digest(p) for p in bound},
        "parents": len(parents),
        "query_rows": len(queries),
        "unique_embeddings": len(unique),
        "paired_parents": sum(coverage.values()),
        "collision_excluded_parents": len(collision_parents),
        "validation_prediction_rows": 0,
        "test_prediction_rows": 0,
    }
    write_json(out / "prepared.json", receipt)
    return receipt


def check_prepared(out):
    receipt = read_json(out / "prepared.json")
    if receipt["status"] != "PASS" or receipt["script_sha256"] != digest(Path(__file__)):
        raise ValueError("Preparation failed or benchmark code changed; prepare a new run")
    for name, expected in receipt["files"].items():
        if digest(out / name) != expected:
            raise ValueError(f"Prepared input changed: {name}")
    return read_json(out / "config.json")


def embedding_settings(out, encoder):
    from djrmcp_finder.config import load_config
    from djrmcp_finder.benchmark_config import expand_benchmark_model

    config = expand_benchmark_model(load_config(out / "registry.yaml"), encoder)
    config["paths"].update(
        {
            "v0_manifest": str(out / "inputs/embedding_manifest.tsv"),
            "v0_fasta": str(out / "inputs/embedding.faa"),
            "embedding_output": str(out / "embeddings" / encoder),
        }
    )
    return config


def embed(out, encoder, device, limit):
    check_prepared(out)
    from djrmcp_finder.stages.benchmark_embedding import run

    return run(embedding_settings(out, encoder), device_override=device, limit=limit)


def verify_bundle_checksums(root):
    declared = {}
    for line in (root / "CHECKSUMS.sha256").read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        name = name.lstrip("* ")
        if name in declared:
            raise ValueError("Duplicate embedding checksum entry")
        declared[name] = sha
    for name in ("metadata.json", "index.tsv", "completed.npy", "embeddings.float16.npy"):
        if digest(root / name) != declared.get(name):
            raise ValueError(f"Embedding checksum mismatch: {root.name}/{name}")
    return declared


def reuse(out, encoder, source, require_complete=False):
    """Seed a new resumable bundle from exact Train sequence matches, on CPU.

    Source arrays may also contain protected splits; only Train rows are selected.
    Historical vectors are immutable. A separate receipt survives encoder resume.
    """
    import numpy as np
    import tempfile
    from djrmcp_finder.stages.benchmark_embedding import _pooling_contract, _special_token_policy

    check_prepared(out)
    settings = embedding_settings(out, encoder)["embedding"]
    dest = out / "embeddings" / encoder
    if dest.exists():
        raise ValueError("Embedding destination already exists; reuse requires a new bundle")
    declared = verify_bundle_checksums(source)
    meta = read_json(source / "metadata.json")
    adapter_keys = (
        "model_loader",
        "tokenizer_loader",
        "sequence_format",
        "sequence_prefix",
        "replace_rare_with_x",
        "trust_remote_code",
        "repo_subfolder",
        "library_import",
        "prefix_token_count",
        "native_model_max_tokens",
        "mimic_checkpoint_version",
        "mimic_code_revision",
        "esm_code_revision",
        "transformers_code_revision",
    )
    contract = {
        "schema_version": 3,
        "benchmark_model_id": encoder,
        "model_name": settings["model_name"],
        "requested_model_revision": settings["model_revision"],
        "resolved_model_revision": settings["model_revision"],
        "backend": settings.get("backend", "transformer_residue"),
        "pooling": _pooling_contract(settings),
        "window_residues": settings["window_residues"],
        "stride": settings["stride"],
        "dtype": settings["output_dtype"],
        "compute_precision": settings["precision"],
        "long_sequence_policy": "overlapping_windows_no_truncation",
        "special_token_policy": _special_token_policy(settings),
        "adapter_options": {k: settings[k] for k in adapter_keys if settings.get(k) is not None},
    }
    for key, expected in {**contract, "status": "complete"}.items():
        observed = meta.get(key)
        if key == "adapter_options":
            observed = {k: v for k, v in (observed or {}).items() if v is not None}
        if observed != expected:
            raise ValueError(f"Cached embedding contract mismatch: {encoder}/{key}")
    rows = read_tsv(source / "index.tsv")
    x = np.load(source / "embeddings.float16.npy", mmap_mode="r", allow_pickle=False)
    completed = np.load(source / "completed.npy", allow_pickle=False)
    if (
        x.shape != (len(rows), meta["embedding_dimension"])
        or x.dtype != np.dtype(settings["output_dtype"])
        or completed.shape != (len(rows),)
        or completed.dtype != np.bool_
        or not completed.all()
        or meta["record_count"] != len(rows)
        or meta["completed_records"] != len(rows)
    ):
        raise ValueError("Malformed cached embedding bundle")
    manifest = read_tsv(out / "inputs/embedding_manifest.tsv")
    wanted = {r["sequence_sha256"]: int(r["length_aa"]) for r in manifest}
    lookup = {}
    for i, row in enumerate(rows):
        if int(row["embedding_row"]) != i:
            raise ValueError("Cached embedding index order mismatch")
        sha = row["sequence_sha256"]
        if row["split"] != "train" or sha not in wanted:
            continue
        if int(row["length_aa"]) != wanted[sha] or not np.isfinite(x[i]).all():
            raise ValueError("Invalid matched cached length/vector")
        if sha in lookup and not np.array_equal(x[lookup[sha]], x[i]):
            raise ValueError("Conflicting cached vectors for the same sequence")
        lookup.setdefault(sha, i)
    mapping = [
        {
            "target_row": i,
            "sequence_sha256": r["sequence_sha256"],
            "source_row": lookup[r["sequence_sha256"]],
            "source_protein_id": rows[lookup[r["sequence_sha256"]]]["protein_id"],
        }
        for i, r in enumerate(manifest)
        if r["sequence_sha256"] in lookup
    ]
    if require_complete and len(mapping) != len(manifest):
        raise ValueError(f"Cache covers only {len(mapping)}/{len(manifest)} sequences")
    if not mapping:
        raise ValueError("No matching Train sequences in cache")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{encoder}-reuse-", dir=dest.parent) as temp:
        staging = Path(temp) / "bundle"
        staging.mkdir()
        v = np.lib.format.open_memmap(
            staging / "embeddings.float16.npy",
            mode="w+",
            dtype=x.dtype,
            shape=(len(manifest), x.shape[1]),
        )
        done = np.zeros(len(manifest), dtype=bool)
        for r in mapping:
            v[r["target_row"]] = x[r["source_row"]]
            done[r["target_row"]] = True
        v.flush()
        del v
        np.save(staging / "completed.npy", done)
        write_tsv(
            staging / "index.tsv", [{"embedding_row": i, **r} for i, r in enumerate(manifest)]
        )
        new_meta = {
            **contract,
            "status": "complete" if done.all() else "partial",
            "embedding_dimension": x.shape[1],
            "record_count": len(manifest),
            "completed_records": int(done.sum()),
            "reused_records": int(done.sum()),
            "manifest_sha256": digest(out / "inputs/embedding_manifest.tsv"),
            "fasta_sha256": digest(out / "inputs/embedding.faa"),
            "accumulated_embedding_seconds": 0.0,
            "operation": "exact_sequence_cache_reuse",
        }
        write_json(staging / "metadata.json", new_meta)
        (staging / "CHECKSUMS.sha256").write_text(
            "".join(
                f"{digest(staging / name)}  {name}\n"
                for name in (
                    "metadata.json",
                    "index.tsv",
                    "completed.npy",
                    "embeddings.float16.npy",
                )
            )
        )
        mapping_path = out / "reuse" / f"{encoder}.mapping.tsv"
        write_tsv(mapping_path, mapping)
        receipt = {
            "status": "PASS",
            "encoder": encoder,
            "source": str(source.resolve()),
            "source_checksums": declared,
            "prepared_sha256": digest(out / "prepared.json"),
            "mapping_sha256": digest(mapping_path),
            "reused_records": len(mapping),
            "missing_records": len(manifest) - len(mapping),
            "source_split": "train",
            "validation_rows_imported": 0,
            "test_rows_imported": 0,
        }
        write_json(out / "reuse" / f"{encoder}.json", receipt)
        staging.rename(dest)
    return receipt


def load_vectors(out, encoder):
    import numpy as np

    root = out / "embeddings" / encoder
    verify_bundle_checksums(root)
    receipt_path = out / "reuse" / f"{encoder}.json"
    if receipt_path.exists():
        reused = read_json(receipt_path)
        if reused["prepared_sha256"] != digest(out / "prepared.json") or reused[
            "mapping_sha256"
        ] != digest(out / "reuse" / f"{encoder}.mapping.tsv"):
            raise ValueError("Cache reuse receipt mismatch")
    meta = read_json(root / "metadata.json")
    settings = embedding_settings(out, encoder)["embedding"]
    expected = {
        "status": "complete",
        "benchmark_model_id": encoder,
        "model_name": settings["model_name"],
        "resolved_model_revision": settings["model_revision"],
        "manifest_sha256": digest(out / "inputs/embedding_manifest.tsv"),
        "fasta_sha256": digest(out / "inputs/embedding.faa"),
        "window_residues": settings["window_residues"],
        "stride": settings["stride"],
        "compute_precision": settings["precision"],
        "pooling": "residue_mean_then_window_mean",
    }
    for name, value in expected.items():
        if meta.get(name) != value:
            raise ValueError(f"Embedding contract mismatch: {encoder}/{name}")
    rows = read_tsv(root / "index.tsv")
    manifest = read_tsv(out / "inputs/embedding_manifest.tsv")
    if len(rows) != len(manifest):
        raise ValueError("Embedding index length mismatch")
    for i, (r, m) in enumerate(zip(rows, manifest)):
        if int(r["embedding_row"]) != i or any(
            r[k] != m[k] for k in ("protein_id", "sequence_sha256", "split")
        ):
            raise ValueError("Embedding index/sequence identity mismatch")
    vectors = np.load(root / "embeddings.float16.npy", mmap_mode="r", allow_pickle=False)
    completed = np.load(root / "completed.npy", allow_pickle=False)
    if (
        vectors.ndim != 2
        or vectors.shape[0] != len(rows)
        or completed.shape != (len(rows),)
        or not completed.all()
    ):
        raise ValueError("Incomplete or malformed embedding matrix")
    for start in range(0, len(vectors), 1024):
        if not np.isfinite(vectors[start : start + 1024]).all():
            raise ValueError("Nonfinite embedding")
    return vectors, {r["protein_id"]: i for i, r in enumerate(rows)}


def choose_threshold(y, raw, metric):
    """Exact raw-score sweep, including predict-none; ties prefer higher threshold."""
    import numpy as np

    y, raw = np.asarray(y, dtype=int), np.asarray(raw, dtype=float)
    if set(y) != {0, 1} or not np.isfinite(raw).all():
        raise ValueError("Calibration needs both classes and finite scores")
    order = np.argsort(-raw, kind="stable")
    values, labels = raw[order], y[order]
    ends = np.r_[np.flatnonzero(values[1:] != values[:-1]), len(values) - 1]
    tp = np.r_[0, np.cumsum(labels)[ends]].astype(float)
    fp = np.r_[0, ends + 1 - np.cumsum(labels)[ends]].astype(float)
    fn, tn = y.sum() - tp, (1 - y).sum() - fp
    if metric == "mcc":
        denominator = np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
        score = np.divide(
            tp * tn - fp * fn, denominator, out=np.zeros_like(tp), where=denominator > 0
        )
    elif metric == "macro_f1":
        score = tp / (2 * tp + fp + fn) + tn / (2 * tn + fp + fn)
    else:
        raise ValueError("Unknown threshold metric")
    thresholds = np.r_[np.nextafter(values[0], np.inf), values[ends]]
    return float(thresholds[int(np.argmax(score))])


def score(out):
    import numpy as np
    import sklearn
    from djrmcp_finder.stages.classifier import _fit_model, _decision_scores

    config = check_prepared(out)
    if (out / "scores").exists():
        raise ValueError("Scores already exist; use a new run for a different scoring attempt")
    parents, queries = read_tsv(out / "inputs/parents.tsv"), read_tsv(out / "inputs/queries.tsv")
    vectors = {encoder: load_vectors(out, encoder) for encoder in ("esmc_6b", "esm2_3b")}

    def matrix(rows, encoder):
        v, index = vectors[encoder]
        return np.asarray(v[[index[r["embedding_id"]] for r in rows]], dtype=np.float32)

    settings = config["classifier"]
    predictions, contracts = [], []
    for fold in range(1, 6):
        cal_fold, fit_folds = fold_roles(fold, 5, config["calibration_fold_offset"])
        fit = [p for p in parents if int(p["fold"]) in fit_folds]
        cal = [p for p in parents if int(p["fold"]) == cal_fold]
        query = [q for q in queries if int(q["fold"]) == fold]
        groups = [{r["global_component_id"] for r in rows} for rows in (fit, cal, query)]
        if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
            raise ValueError("Component leakage")
        h3_fit = [p for p in fit if p["is_mcp"] == "1" and p["phylum"] in KNOWN]
        h3_cal = [p for p in cal if p["is_mcp"] == "1" and p["phylum"] in KNOWN]
        if any({p["phylum"] for p in rows} != set(KNOWN) for rows in (h3_fit, h3_cal)):
            raise ValueError(f"Both known phyla required for H3 fit/calibration in fold {fold}")
        h3 = _fit_model(
            "head3_phylum",
            matrix(h3_fit, "esmc_6b"),
            np.array([KNOWN.index(p["phylum"]) for p in h3_fit]),
            h3_fit,
            settings["head3_c"],
            settings,
            config["seed"] + fold + 2,
        )
        cal3 = _decision_scores(h3, matrix(h3_cal, "esmc_6b"))
        # Binary confidence is monotonic in |logit|. A rank-based rejection gate
        # needs no temperature fit and cannot suffer sigmoid saturation.
        h3_threshold = float(
            np.quantile(np.abs(cal3), 1 - settings["head3_known_acceptance"], method="lower")
        )
        for method, encoder in config["methods"].items():
            thresholds, models = [], []
            for head, label, parameter, metric in (
                ("head1", "is_djr", "head1_alpha", "mcc"),
                ("head2", "is_mcp", "head2_c", "macro_f1"),
            ):
                training = fit if head == "head1" else [p for p in fit if p["is_djr"] == "1"]
                calibration = cal if head == "head1" else [p for p in cal if p["is_djr"] == "1"]
                labels = np.array([int(p[label]) for p in training])
                if set(labels) != {0, 1}:
                    raise ValueError(f"Missing fit class: {fold}/{head}")
                model = _fit_model(
                    head,
                    matrix(training, encoder),
                    labels,
                    training,
                    settings[parameter],
                    settings,
                    config["seed"] + fold + (head == "head2"),
                )
                threshold = choose_threshold(
                    [int(p[label]) for p in calibration],
                    _decision_scores(model, matrix(calibration, encoder)),
                    metric,
                )
                models.append(model)
                thresholds.append(threshold)
            contracts.append(
                {
                    "method": method,
                    "evaluation_fold": fold,
                    "calibration_fold": cal_fold,
                    "fit_folds": ",".join(map(str, fit_folds)),
                    "fit_parents": len(fit),
                    "calibration_parents": len(cal),
                    "h1_threshold": thresholds[0],
                    "h2_threshold": thresholds[1],
                    "h3_abs_logit_threshold": h3_threshold,
                    "h3_calibration_acceptance": float(np.mean(np.abs(cal3) >= h3_threshold)),
                    "component_overlap": 0,
                    "calibration_fragments": 0,
                }
            )
            for start in range(0, len(query), 512):
                block = query[start : start + 512]
                x = matrix(block, encoder)
                r1, r2 = [_decision_scores(model, x) for model in models]
                r3 = _decision_scores(h3, matrix(block, "esmc_6b"))
                for q, s1, s2, s3 in zip(block, r1, r2, r3):
                    h1, h2 = int(s1 >= thresholds[0]), int(s2 >= thresholds[1])
                    h3_label = KNOWN[int(s3 > 0)] if abs(s3) >= h3_threshold else "unknown/other"
                    final = "non_djr" if not h1 else "djr_non_mcp" if not h2 else "mcp::" + h3_label
                    predictions.append(
                        {
                            **q,
                            "method": method,
                            "head1_raw": float(s1),
                            "head2_raw": float(s2),
                            "head3_raw": float(s3),
                            "head1_positive": h1,
                            "head2_positive": h2,
                            "mcp_positive": h1 * h2,
                            "head3_diagnostic_label": h3_label,
                            "final_label": final,
                        }
                    )
        print(f"Scored evaluation fold {fold}/5", flush=True)
    dest = out / "scores"
    write_tsv(dest / "predictions.tsv", predictions)
    write_tsv(dest / "fold_contracts.tsv", contracts)
    classifier_module = Path(sys.modules[_fit_model.__module__].__file__)
    write_json(
        dest / "receipt.json",
        {
            "status": "PASS",
            "scope": "TRAIN_ONLY_INTERNAL_CROSSFIT",
            "prepared_sha256": digest(out / "prepared.json"),
            "script_sha256": digest(Path(__file__)),
            "classifier_module_sha256": digest(classifier_module),
            "encoder_bundles": {
                k: digest(out / "embeddings" / k / "CHECKSUMS.sha256") for k in vectors
            },
            "files": {p.name: digest(p) for p in dest.iterdir()},
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "sklearn": sklearn.__version__,
            "validation_prediction_rows": 0,
            "test_prediction_rows": 0,
        },
    )
    return {"status": "PASS", "prediction_rows": len(predictions)}


def validated_predictions(out):
    config = check_prepared(out)
    receipt = read_json(out / "scores/receipt.json")
    if receipt["status"] != "PASS" or receipt["prepared_sha256"] != digest(out / "prepared.json"):
        raise ValueError("Score receipt is not bound to preparation")
    if receipt["script_sha256"] != digest(Path(__file__)):
        raise ValueError("Scoring code changed")
    for name, expected in receipt["files"].items():
        if digest(out / "scores" / name) != expected:
            raise ValueError(f"Score file changed: {name}")
    queries = {q["sample_id"]: q for q in read_tsv(out / "inputs/queries.tsv")}
    rows = read_tsv(out / "scores/predictions.tsv")
    seen = set()
    contracts = {
        (r["method"], r["evaluation_fold"]): r for r in read_tsv(out / "scores/fold_contracts.tsv")
    }
    if len(contracts) != 5 * len(config["methods"]):
        raise ValueError("Missing fold contracts")
    for r in rows:
        key = r["method"], r["sample_id"]
        if key in seen or r["method"] not in config["methods"]:
            raise ValueError("Duplicate or unexpected prediction")
        seen.add(key)
        original = queries.get(r["sample_id"])
        if original is None or any(r[k] != v for k, v in original.items()):
            raise ValueError("Prediction metadata differs from frozen query")
        contract = contracts[(r["method"], r["fold"])]
        cal, fit = fold_roles(int(r["fold"]), 5, config["calibration_fold_offset"])
        if (
            int(contract["calibration_fold"]) != cal
            or contract["fit_folds"] != ",".join(map(str, fit))
            or contract["component_overlap"] != "0"
            or contract["calibration_fragments"] != "0"
        ):
            raise ValueError("Invalid fold role contract")
        s1, s2, s3 = (float(r[k]) for k in ("head1_raw", "head2_raw", "head3_raw"))
        if not all(math.isfinite(v) for v in (s1, s2, s3)):
            raise ValueError("Nonfinite raw score")
        h1, h2 = (
            int(s1 >= float(contract["h1_threshold"])),
            int(s2 >= float(contract["h2_threshold"])),
        )
        h3 = (
            KNOWN[int(s3 > 0)]
            if abs(s3) >= float(contract["h3_abs_logit_threshold"])
            else "unknown/other"
        )
        final = "non_djr" if not h1 else "djr_non_mcp" if not h2 else "mcp::" + h3
        if (
            r["head1_positive"],
            r["head2_positive"],
            r["mcp_positive"],
            r["head3_diagnostic_label"],
            r["final_label"],
        ) != (str(h1), str(h2), str(h1 * h2), h3, final):
            raise ValueError("Prediction does not obey frozen gates")
    if len(seen) != len(queries) * len(config["methods"]):
        raise ValueError("Missing prediction rows; failures must not be silently dropped")
    return config, rows


def outcomes(row):
    """Return eligible binary outcomes; absence means outside that denominator."""
    djr, mcp = int(row["is_djr"]), int(row["is_mcp"])
    h1, h2, called = (int(row[k]) for k in ("head1_positive", "head2_positive", "mcp_positive"))
    values = {"h1_recall" if djr else "h1_fpr": h1, "mcp_recall" if mcp else "mcp_fpr": called}
    if djr:
        values["h2_conditional_recall" if mcp else "h2_conditional_fpr"] = h2
    if mcp and row["phylum"] in KNOWN:
        correct = row["head3_diagnostic_label"] == row["phylum"]
        values["h3_known_end_to_end_recall"] = int(called and correct)
        values["h3_end_to_end_recall_" + row["phylum"]] = int(called and correct)
        if called:
            values["h3_known_gated_accuracy"] = int(correct)
            values["h3_known_gated_reject_rate"] = int(
                row["head3_diagnostic_label"] == "unknown/other"
            )
            values["h3_known_gated_wrong_phylum_rate"] = int(
                not correct and row["head3_diagnostic_label"] in KNOWN
            )
    elif mcp and called:
        values["h3_unknown_gated_reject_rate"] = int(
            row["head3_diagnostic_label"] == "unknown/other"
        )
    return values


def length_bin(length):
    for upper in (100, 130, 150, 200, 250, 300):
        if length < upper:
            lower = {100: 0, 130: 100, 150: 130, 200: 150, 250: 200, 300: 250}[upper]
            return f"{lower}-{upper - 1}"
    return "300+"


def cluster_interval(parent_values, replicates, seed):
    """Parent-balanced point estimate; resample whole components, retaining weights."""
    import numpy as np

    grouped = defaultdict(list)
    for component, value in parent_values.values():
        grouped[component].append(value)
    if not grouped:
        return {
            "estimate": "",
            "ci_low": "",
            "ci_high": "",
            "parents": 0,
            "components": 0,
            "ci_status": "NOT_ESTIMABLE",
        }
    blocks = np.array([[sum(v), len(v)] for _, v in sorted(grouped.items())], dtype=float)
    result = {
        "estimate": float(blocks[:, 0].sum() / blocks[:, 1].sum()),
        "parents": len(parent_values),
        "components": len(blocks),
        "ci_low": "",
        "ci_high": "",
        "ci_status": "INSUFFICIENT_COMPONENTS",
    }
    if len(blocks) < 2:
        return result
    rng = np.random.default_rng(seed)
    draws = []
    for start in range(0, replicates, 64):
        indexes = rng.integers(0, len(blocks), size=(min(64, replicates - start), len(blocks)))
        sampled = blocks[indexes].sum(axis=1)
        draws.extend((sampled[:, 0] / sampled[:, 1]).tolist())
    result.update(
        ci_low=float(np.quantile(draws, 0.025)),
        ci_high=float(np.quantile(draws, 0.975)),
        ci_status="OK",
    )
    if (
        all(v in (0, 1) for _, v in parent_values.values())
        and len({v for _, v in parent_values.values()}) == 1
    ):
        result["ci_status"] = "BOUNDARY_BOOTSTRAP_NOT_A_POPULATION_BOUND"
    return result


def summarize(out):
    config, rows = validated_predictions(out)
    groups = defaultdict(list)
    for r in rows:
        if r["paired_eligible"] == "1":
            position = (
                r["position"].split("_")[0]
                if r["position"].startswith("internal_")
                else r["position"]
            )
            for pos in {"pooled", position}:
                for source in {"all", r["source_dataset"]}:
                    groups[(r["method"], "paired_truncation", r["length"], pos, source)].append(r)
        if r["position"] == "full":
            for source in {"all", r["source_dataset"]}:
                groups[
                    (
                        r["method"],
                        "observed_length",
                        length_bin(int(r["length_aa"])),
                        "full",
                        source,
                    )
                ].append(r)
    # Keep empty bins visible: absence of short proteins is not zero recall.
    for method in config["methods"]:
        for length in LENGTH_BINS:
            groups[(method, "observed_length", length, "full", "all")]
    metric_names = (
        "h1_recall",
        "h1_fpr",
        "h2_conditional_recall",
        "h2_conditional_fpr",
        "mcp_recall",
        "mcp_fpr",
        "h3_known_end_to_end_recall",
        "h3_known_gated_accuracy",
        "h3_known_gated_reject_rate",
        "h3_known_gated_wrong_phylum_rate",
        "h3_unknown_gated_reject_rate",
        *("h3_end_to_end_recall_" + phylum for phylum in KNOWN),
    )
    summaries, parent_store = [], {}
    for group, records in sorted(groups.items()):
        collected = defaultdict(lambda: defaultdict(list))
        components = {}
        for r in records:
            components[r["parent_id"]] = r["global_component_id"]
            for name, value in outcomes(r).items():
                collected[name][r["parent_id"]].append(value)
        for metric in metric_names:
            by_parent = collected[metric]
            parent_values = {
                pid: (components[pid], sum(v) / len(v)) for pid, v in by_parent.items()
            }
            key = (*group, metric)
            parent_store[key] = parent_values
            stats = cluster_interval(parent_values, config["bootstrap_replicates"], config["seed"])
            summaries.append(
                dict(
                    zip(("method", "panel", "length", "position", "source_dataset", "metric"), key)
                )
                | stats
                | {"eligible_fragments": sum(map(len, by_parent.values()))}
            )
    # Paired differences use exactly the same parents and the same component draws.
    deltas = []
    for key, values in sorted(parent_store.items()):
        method, panel, length, position, source, metric = key
        if panel != "paired_truncation" or position != "pooled" or source != "all":
            continue
        comparisons = []
        if length != "full":
            comparisons.append(
                ("length_minus_full", (method, panel, "full", position, source, metric))
            )
        if method == "v01_candidate":
            comparisons.append(("v01_minus_v0", ("v0", panel, length, position, source, metric)))
        for comparison, baseline in comparisons:
            other = parent_store.get(baseline, {})
            common = set(values) & set(other)
            differences = {pid: (values[pid][0], values[pid][1] - other[pid][1]) for pid in common}
            deltas.append(
                {
                    "comparison": comparison,
                    "method": method,
                    "length": length,
                    "metric": metric,
                    **cluster_interval(differences, config["bootstrap_replicates"], config["seed"]),
                    "denominator": "intersection_of_eligible_parents",
                }
            )
    dest = out / "results"
    write_tsv(dest / "metrics.tsv", summaries)
    write_tsv(
        dest / "paired_deltas.tsv",
        deltas,
        [
            "comparison",
            "method",
            "length",
            "metric",
            "estimate",
            "parents",
            "components",
            "ci_low",
            "ci_high",
            "ci_status",
            "denominator",
        ],
    )
    report = [
        "# Short-sequence benchmark",
        "",
        "TRAIN-ONLY INTERNAL CROSS-FIT — NOT AN EXTERNAL TEST.",
        "",
        "Estimates first average eligible fragments within each parent. CIs resample entire homology components.",
        "Native/observed-length strata describe input records, not independently verified complete short proteins.",
        "Unknown phylum still counts as MCP detection. H3 gated denominators differ from end-to-end denominators.",
        "Zero observed errors and a boundary bootstrap interval do not prove zero population error.",
        "",
        "| Method | Length | MCP recall | MCP FPR |",
        "|---|---|---:|---:|",
    ]
    main = {
        (r["method"], r["length"], r["metric"]): r
        for r in summaries
        if r["panel"] == "paired_truncation"
        and r["position"] == "pooled"
        and r["source_dataset"] == "all"
    }
    for method in config["methods"]:
        for length in ["full", *map(str, reversed(config["lengths"]))]:
            cells = []
            for metric in ("mcp_recall", "mcp_fpr"):
                r = main.get((method, length, metric))
                cells.append(
                    "not estimable" if not r or r["estimate"] == "" else f"{r['estimate']:.4f}"
                )
            report.append(f"| {method} | {length} | {' | '.join(cells)} |")
    if config.get("evaluation_mode") == "observed":
        report = report[:9]
    report.extend(
        [
            "",
            "## Observed input length (unmodified sequences)",
            "",
            "Different bins contain different proteins and source mixtures; this is not a paired truncation experiment.",
            "Empty bins are not estimable. Intervals condition on the fitted cross-fit models.",
            "",
            "| Method | Length (aa) | MCP recall [95% CI]; n | MCP FPR [95% CI]; n |",
            "|---|---|---|---|",
        ]
    )
    observed = {
        (r["method"], r["length"], r["metric"]): r
        for r in summaries
        if r["panel"] == "observed_length" and r["source_dataset"] == "all"
    }
    for method in config["methods"]:
        for length in LENGTH_BINS:
            cells = []
            for metric in ("mcp_recall", "mcp_fpr"):
                r = observed[(method, length, metric)]
                if r["estimate"] == "":
                    cells.append("not estimable; n=0")
                else:
                    ci = (
                        f"[{r['ci_low']:.4f}, {r['ci_high']:.4f}]"
                        if r["ci_low"] != ""
                        else "[CI unavailable]"
                    )
                    cells.append(f"{r['estimate']:.4f} {ci}; n={r['parents']}")
            report.append(f"| {method} | {length} | {' | '.join(cells)} |")
    (dest / "REPORT.md").write_text("\n".join(report) + "\n")
    write_json(
        dest / "receipt.json",
        {
            "status": "PASS",
            "score_receipt_sha256": digest(out / "scores/receipt.json"),
            "files": {
                name: digest(dest / name)
                for name in ("metrics.tsv", "paired_deltas.tsv", "REPORT.md")
            },
            "bootstrap_replicates": config["bootstrap_replicates"],
        },
    )
    return {"status": "PASS", "metric_rows": len(summaries), "paired_delta_rows": len(deltas)}


def validate_results(out):
    receipt = read_json(out / "results/receipt.json")
    if receipt.get("status") != "PASS" or receipt.get("score_receipt_sha256") != digest(
        out / "scores/receipt.json"
    ):
        raise ValueError("Results are not bound to these scores")
    if set(receipt["files"]) != {"metrics.tsv", "paired_deltas.tsv", "REPORT.md"}:
        raise ValueError("Incomplete numeric results")
    for name, sha in receipt["files"].items():
        if digest(out / "results" / name) != sha:
            raise ValueError("Result file changed")


def validate(out):
    check_prepared(out)
    stage = "prepared"
    if (out / "scores").exists():
        validated_predictions(out)
        stage = "scored"
    if (out / "results").exists():
        validate_results(out)
        stage = "summarized"
    return {"status": "PASS", "stage": stage}


def plot(out):
    validate(out)
    validate_results(out)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from djrmcp_finder.stages.short_sequence_plot import plot_observed

    observed_figure = plot_observed(out, read_tsv)

    rows = [
        r
        for r in read_tsv(out / "results/metrics.tsv")
        if r["panel"] == "paired_truncation"
        and r["position"] == "pooled"
        and r["source_dataset"] == "all"
    ]
    if not any(r["length"] != "full" for r in rows):
        return {"status": "PASS", "figure": str(observed_figure)}
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.8), constrained_layout=True)
    for ax, metric, title in zip(
        axes, ("mcp_recall", "mcp_fpr"), ("MCP recall", "MCP false-positive rate")
    ):
        for method, color in (("v0", "#0072B2"), ("v01_candidate", "#D55E00")):
            selected = sorted(
                [
                    r
                    for r in rows
                    if r["method"] == method
                    and r["metric"] == metric
                    and r["length"] != "full"
                    and r["estimate"] != ""
                ],
                key=lambda r: int(r["length"]),
            )
            if not selected:
                continue
            x, y = [int(r["length"]) for r in selected], [float(r["estimate"]) for r in selected]
            ax.plot(x, y, "o-", color=color, label=method)
            if all(r["ci_low"] != "" for r in selected):
                ax.fill_between(
                    x,
                    [float(r["ci_low"]) for r in selected],
                    [float(r["ci_high"]) for r in selected],
                    color=color,
                    alpha=0.15,
                )
            full = next(
                (
                    r
                    for r in rows
                    if r["method"] == method and r["metric"] == metric and r["length"] == "full"
                ),
                None,
            )
            if full and full["estimate"] != "":
                ax.axhline(float(full["estimate"]), color=color, linestyle="--", linewidth=1)
        ax.set(xlabel="Fragment length (aa)", ylabel=title, ylim=(-0.02, 1.02))
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle(
        "Internal cross-fit: paired short-sequence stress test\nShading: component bootstrap 95% CI; dashed: full sequence",
        fontsize=10,
    )
    for suffix in ("png", "pdf"):
        fig.savefig(out / "results" / f"length_curves.{suffix}", dpi=300)
    plt.close(fig)
    return {"status": "PASS", "figure": str(out / "results/length_curves.pdf")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser(
        "prepare", help="Validate frozen Train inputs and generate deterministic fragments"
    )
    prep.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    prep.add_argument("--project-root", type=Path, default=REPO)
    prep.add_argument("--out", required=True, type=Path)
    prep.add_argument("--mode", choices=("truncation", "observed"), default="truncation")
    for command in ("embed", "reuse", "score", "summarize", "plot", "validate"):
        stage = sub.add_parser(command)
        stage.add_argument("--run", required=True, type=Path)
        if command in {"embed", "reuse"}:
            stage.add_argument("--encoder", required=True, choices=("esmc_6b", "esm2_3b"))
        if command == "reuse":
            stage.add_argument("--source", required=True, type=Path)
            stage.add_argument("--require-complete", action="store_true")
        if command == "embed":
            stage.add_argument("--device", default="cuda")
            stage.add_argument(
                "--limit", type=int, help="Partial embedding smoke test; cannot be scored"
            )
    args = parser.parse_args()
    if args.command == "prepare":
        config = read_json(args.config)
        config["evaluation_mode"] = args.mode
        result = prepare(config, args.project_root.resolve(), args.out.resolve())
    elif args.command == "reuse":
        result = reuse(
            args.run.resolve(), args.encoder, args.source.resolve(), args.require_complete
        )
    elif args.command == "embed":
        result = embed(args.run.resolve(), args.encoder, args.device, args.limit)
    else:
        result = globals()[args.command](args.run.resolve())
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
