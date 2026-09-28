"""Leakage, denominator, and numerical regression tests; no model download."""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import f1_score, matthews_corrcoef

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "short_sequence_benchmark", ROOT / "benchmarks/short_sequence_v1/benchmark.py"
)
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)


@pytest.fixture
def cohort(tmp_path):
    config = b.read_json(ROOT / "benchmarks/short_sequence_v1/config.json")
    config.update(lengths=[50, 100, 300], bootstrap_replicates=100)
    config["classifier"]["head1_epochs"] = 4
    config["registry"] = str(ROOT / "configs/model_benchmark_v0.yaml")
    config["inputs"] = {
        "train_manifest": "train.tsv",
        "train_fasta": "train.faa",
        "fold_map": "folds.tsv",
    }
    rng = random.Random(17)
    rows, fasta, folds = [], {}, []
    for fold in range(1, 6):
        for kind in range(8):
            pid = f"p{fold}_{kind}"
            source = ["viral_vma_djr", "cellular_djr_none", "hard_non_djr", "background_non_djr"][
                kind // 2
            ]
            djr, mcp = kind < 4, kind < 2
            seq = "".join(rng.choices("ACDEFGHIKLMNPQRSTVWY", k=320 + kind))
            fasta[pid] = seq
            component = f"c{fold}_{kind // 2}"  # two related parents per block
            phylum = b.KNOWN[kind] if mcp else ""
            rows.append(
                {
                    "protein_id": pid,
                    "source_dataset": source,
                    "global_component_id": component,
                    "split": "train",
                    "head1_mask": "1",
                    "head1_label": "djr" if djr else "non_djr",
                    "head2_mask": "1" if djr else "0",
                    "head2_label": "viral_morphogenesis_associated" if mcp else "none",
                    "head3_mask": "1" if mcp else "0",
                    "head3_operational_label": phylum,
                    "length_aa": len(seq),
                    "sequence_sha256": b.sequence_hash(seq),
                }
            )
            if kind % 2 == 0:
                folds.append({"global_component_id": component, "fold": fold})

    def save():
        b.write_tsv(tmp_path / "train.tsv", rows)
        b.write_tsv(tmp_path / "folds.tsv", folds)
        (tmp_path / "train.faa").write_text("".join(f">{k}\n{v}\n" for k, v in fasta.items()))
        config["expected_sha256"] = {k: b.digest(tmp_path / p) for k, p in config["inputs"].items()}

    save()
    return config, tmp_path, rows, fasta, folds, save


def test_prepare_is_deterministic_and_parent_disjoint(cohort):
    config, root, rows, fasta, _, save = cohort
    result = b.prepare(config, root, root / "run1")
    assert result["parents"] == result["paired_parents"] == 40
    assert result["test_prediction_rows"] == result["validation_prediction_rows"] == 0
    queries = b.read_tsv(root / "run1/inputs/queries.tsv")
    for q in queries:
        fragment = fasta[q["parent_id"]][int(q["start"]) : int(q["end"])]
        assert b.sequence_hash(fragment) == q["sequence_sha256"]
        assert int(q["length_aa"]) == len(fragment)
    rows.reverse()
    save()
    b.prepare(config, root, root / "run2")
    assert b.digest(root / "run1/inputs/queries.tsv") == b.digest(root / "run2/inputs/queries.tsv")
    for fold in range(1, 6):
        cal, fit = b.fold_roles(fold)
        assert len(set([fold, cal, *fit])) == 5


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("split", "non-Train"),
        ("hash", "hash/length"),
        ("fold", "Duplicate component"),
        ("label", "H2 ground truth"),
    ],
)
def test_fail_closed_input_validation(cohort, mutation, error):
    config, root, rows, _, folds, save = cohort
    if mutation == "split":
        rows[0]["split"] = "test"
    elif mutation == "hash":
        rows[0]["sequence_sha256"] = "0" * 64
    elif mutation == "fold":
        folds.append(folds[0].copy())
    else:
        rows[0]["head2_mask"] = "0"
    save()
    with pytest.raises(ValueError, match=error):
        b.prepare(config, root, root / "run")


def test_collision_excludes_entire_parent_across_all_lengths(cohort):
    config, root, rows, fasta, _, save = cohort
    shared = "ACDEF" * 10
    for pid in ("p1_0", "p2_0"):
        fasta[pid] = shared + fasta[pid][50:]
        next(r for r in rows if r["protein_id"] == pid)["sequence_sha256"] = b.sequence_hash(
            fasta[pid]
        )
    save()
    result = b.prepare(config, root, root / "run")
    assert result["collision_excluded_parents"] == 2
    queries = b.read_tsv(root / "run/inputs/queries.tsv")
    assert all(q["paired_eligible"] == "0" for q in queries if q["parent_id"] in {"p1_0", "p2_0"})
    assert {q["length"] for q in queries if q["parent_id"] == "p1_0"} == {
        "full",
        "50",
        "100",
        "300",
    }


def test_short_parent_and_boundary_windows(cohort):
    config, root, rows, fasta, _, save = cohort
    fasta["p1_0"] = fasta["p1_0"][:130]
    rows[0].update(length_aa=130, sequence_sha256=b.sequence_hash(fasta["p1_0"]))
    save()
    b.prepare(config, root, root / "run")
    queries = b.read_tsv(root / "run/inputs/queries.tsv")
    selected = [q for q in queries if q["parent_id"] == "p1_0"]
    assert (
        len(selected) == 1
        and selected[0]["position"] == "full"
        and selected[0]["paired_eligible"] == "0"
    )
    assert list(b.fragment_windows("A" * 300, 300, 1, "p", 1)) == [
        ("n_terminal", 0, 300),
        ("c_terminal", 0, 300),
    ]


@pytest.mark.parametrize("metric", ["mcc", "macro_f1"])
def test_raw_threshold_matches_exhaustive_sweep_without_saturation(metric):
    y = np.array([0, 1, 0, 1, 1, 0])
    raw = np.array([1000.0, 1001.0, 1001.0, 1002.0, -1000.0, -2000.0])
    candidates = [*np.unique(raw), np.nextafter(raw.max(), np.inf)]
    fn = matthews_corrcoef if metric == "mcc" else lambda a, p: f1_score(a, p, average="macro")
    expected = max(candidates, key=lambda t: (fn(y, raw >= t), t))
    assert b.choose_threshold(y, raw, metric) == expected
    with pytest.raises(ValueError):
        b.choose_threshold([1, 1], [1.0, 2.0], metric)


def test_mcp_unknown_and_h3_denominators():
    r = {
        "is_djr": "1",
        "is_mcp": "1",
        "head1_positive": "1",
        "head2_positive": "1",
        "mcp_positive": "1",
        "phylum": b.KNOWN[0],
        "head3_diagnostic_label": "unknown/other",
    }
    assert b.outcomes(r)["mcp_recall"] == 1
    assert b.outcomes(r)["h3_known_end_to_end_recall"] == 0
    assert b.outcomes(r)["h3_known_gated_reject_rate"] == 1
    r.update(head1_positive="0", mcp_positive="0")
    assert "h3_known_gated_accuracy" not in b.outcomes(r)
    assert b.outcomes(r)["mcp_recall"] == 0
    r.update(is_mcp="0", head1_positive="1", mcp_positive="1")
    assert b.outcomes(r)["mcp_fpr"] == 1
    assert b.outcomes(r)["h2_conditional_fpr"] == 1


def test_component_bootstrap_counts_independent_units_and_boundaries():
    result = b.cluster_interval({"p1": ("c1", 0.5), "p2": ("c1", 1), "p3": ("c2", 0)}, 300, 2)
    assert result["estimate"] == 0.5 and result["parents"] == 3 and result["components"] == 2
    assert 0 <= result["ci_low"] <= result["estimate"] <= result["ci_high"] <= 1
    assert b.cluster_interval({}, 100, 2)["ci_status"] == "NOT_ESTIMABLE"
    assert b.cluster_interval({"p1": ("c1", 1)}, 100, 2)["ci_low"] == ""
    assert "BOUNDARY" in b.cluster_interval({"p1": ("c1", 0), "p2": ("c2", 0)}, 100, 2)["ci_status"]


def fake_bundles(out):
    """Synthetic features for testing contracts only, never model evidence."""
    queries = b.read_tsv(out / "inputs/queries.tsv")
    index = {
        r["protein_id"]: i for i, r in enumerate(b.read_tsv(out / "inputs/embedding_manifest.tsv"))
    }
    x = np.zeros((len(index), 4), dtype=np.float16)
    for q in queries:
        x[index[q["embedding_id"]]] = [
            2 * int(q["is_djr"]) - 1,
            2 * int(q["is_mcp"]) - 1,
            1 if q["phylum"] == b.KNOWN[1] else -1,
            int(q["length_aa"]) / 400,
        ]
    for encoder in ("esmc_6b", "esm2_3b"):
        dest = out / "embeddings" / encoder
        dest.mkdir(parents=True)
        np.save(dest / "embeddings.float16.npy", x)
        np.save(dest / "completed.npy", np.ones(len(x), dtype=bool))
        manifest = b.read_tsv(out / "inputs/embedding_manifest.tsv")
        b.write_tsv(dest / "index.tsv", [{**r, "embedding_row": i} for i, r in enumerate(manifest)])
        settings = b.embedding_settings(out, encoder)["embedding"]
        b.write_json(
            dest / "metadata.json",
            {
                "status": "complete",
                "benchmark_model_id": encoder,
                "model_name": settings["model_name"],
                "resolved_model_revision": settings["model_revision"],
                "manifest_sha256": b.digest(out / "inputs/embedding_manifest.tsv"),
                "fasta_sha256": b.digest(out / "inputs/embedding.faa"),
                "window_residues": 1022,
                "stride": 511,
                "compute_precision": settings["precision"],
                "pooling": "residue_mean_then_window_mean",
            },
        )
        rehash(dest)


def rehash(dest):
    (dest / "CHECKSUMS.sha256").write_text(
        "".join(
            f"{b.digest(dest / name)}  {name}\n"
            for name in ("index.tsv", "metadata.json", "completed.npy", "embeddings.float16.npy")
        )
    )


@pytest.mark.parametrize("bad", ["revision", "completion", "index", "nonfinite", "checksum"])
def test_embedding_corruption_rejected(cohort, bad):
    config, root, *_ = cohort
    out = root / "run"
    b.prepare(config, root, out)
    fake_bundles(out)
    dest = out / "embeddings/esmc_6b"
    if bad == "revision":
        meta = b.read_json(dest / "metadata.json")
        meta["resolved_model_revision"] = "wrong"
        b.write_json(dest / "metadata.json", meta)
    elif bad == "completion":
        np.save(dest / "completed.npy", np.zeros(len(b.read_tsv(dest / "index.tsv")), dtype=bool))
    elif bad == "index":
        rows = b.read_tsv(dest / "index.tsv")
        rows[0]["sequence_sha256"] = "bad"
        b.write_tsv(dest / "index.tsv", rows)
    elif bad == "nonfinite":
        x = np.load(dest / "embeddings.float16.npy")
        x[0, 0] = np.nan
        np.save(dest / "embeddings.float16.npy", x)
    else:
        (dest / "metadata.json").write_text("{}")
    if bad != "checksum":
        rehash(dest)
    with pytest.raises(ValueError):
        b.load_vectors(out, "esmc_6b")


def test_end_to_end_cpu_pipeline_and_missing_prediction_failure(cohort):
    config, root, *_ = cohort
    out = root / "run"
    b.prepare(config, root, out)
    fake_bundles(out)
    assert b.score(out)["prediction_rows"] == 800
    b.validated_predictions(out)
    assert b.summarize(out)["metric_rows"] > 0
    assert b.validate(out)["stage"] == "summarized"
    metrics = b.read_tsv(out / "results/metrics.tsv")
    full = next(
        r
        for r in metrics
        if r["method"] == "v0"
        and r["panel"] == "paired_truncation"
        and r["length"] == "full"
        and r["source_dataset"] == "all"
        and r["position"] == "pooled"
        and r["metric"] == "mcp_recall"
    )
    assert (
        float(full["estimate"]) == 1 and int(full["parents"]) == 10 and int(full["components"]) == 5
    )
    # Shared encoder and fold-specific H3 are identical for the two methods.
    predictions = b.read_tsv(out / "scores/predictions.tsv")
    h3 = {}
    for r in predictions:
        if r["sample_id"] in h3:
            assert r["head3_raw"] == h3[r["sample_id"]]
        h3[r["sample_id"]] = r["head3_raw"]
    if importlib.util.find_spec("matplotlib") is not None:  # optional figure extra
        b.plot(out)
        assert (out / "results/length_curves.pdf").stat().st_size > 1000
    b.write_tsv(out / "scores/predictions.tsv", predictions[:-1])
    receipt = b.read_json(out / "scores/receipt.json")
    receipt["files"]["predictions.tsv"] = b.digest(out / "scores/predictions.tsv")
    b.write_json(out / "scores/receipt.json", receipt)
    with pytest.raises(ValueError, match="Missing prediction"):
        b.validated_predictions(out)


def test_prepared_file_drift_is_rejected(cohort):
    config, root, *_ = cohort
    out = root / "run"
    b.prepare(config, root, out)
    with (out / "inputs/queries.tsv").open("a") as handle:
        handle.write("corruption\n")
    with pytest.raises(ValueError, match="Prepared input changed"):
        b.check_prepared(out)


def test_result_receipt_rejects_changed_tables(tmp_path):
    scores = tmp_path / "scores"
    scores.mkdir()
    b.write_json(scores / "receipt.json", {"status": "PASS"})
    dest = tmp_path / "results"
    dest.mkdir()
    for name in ("metrics.tsv", "paired_deltas.tsv", "REPORT.md"):
        (dest / name).write_text("original\n")
    b.write_json(
        dest / "receipt.json",
        {
            "status": "PASS",
            "score_receipt_sha256": b.digest(scores / "receipt.json"),
            "files": {p.name: b.digest(p) for p in dest.iterdir()},
        },
    )
    b.validate_results(tmp_path)
    (dest / "metrics.tsv").write_text("changed\n")
    with pytest.raises(ValueError, match="Result file changed"):
        b.validate_results(tmp_path)


def historical_fixture(out):
    """Give synthetic vectors the complete legacy contract; IDs deliberately differ."""
    from djrmcp_finder.stages.benchmark_embedding import _special_token_policy

    fake_bundles(out)
    for encoder in ("esm2_3b", "esmc_6b"):
        dest = out / "embeddings" / encoder
        s = b.embedding_settings(out, encoder)["embedding"]
        rows = b.read_tsv(dest / "index.tsv")
        for i, r in enumerate(rows):
            r["protein_id"] = f"historical_{i}"
        b.write_tsv(dest / "index.tsv", rows)
        meta = b.read_json(dest / "metadata.json")
        meta.update(
            schema_version=3,
            requested_model_revision=s["model_revision"],
            backend=s["backend"],
            dtype="float16",
            embedding_dimension=4,
            record_count=len(rows),
            completed_records=len(rows),
            long_sequence_policy="overlapping_windows_no_truncation",
            special_token_policy=_special_token_policy(s),
            adapter_options={
                k: s[k]
                for k in (
                    "model_loader",
                    "tokenizer_loader",
                    "sequence_format",
                    "sequence_prefix",
                    "replace_rare_with_x",
                    "trust_remote_code",
                    "transformers_code_revision",
                )
                if k in s
            },
        )
        b.write_json(dest / "metadata.json", meta)
        rehash(dest)


def test_observed_reuse_pipeline_has_no_fragments_and_preserves_empty_bins(cohort):
    config, root, *_ = cohort
    config["evaluation_mode"] = "observed"
    old, out = root / "historical", root / "observed"
    b.prepare(config, root, old)
    historical_fixture(old)
    result = b.prepare(config, root, out)
    assert result["query_rows"] == result["unique_embeddings"] == 40
    assert result["paired_parents"] == 0
    for encoder in ("esm2_3b", "esmc_6b"):
        source = old / "embeddings" / encoder
        before = b.digest(source / "CHECKSUMS.sha256")
        receipt = b.reuse(out, encoder, source, require_complete=True)
        assert receipt["reused_records"] == 40 and receipt["missing_records"] == 0
        assert b.digest(source / "CHECKSUMS.sha256") == before
        x, _ = b.load_vectors(out, encoder)
        assert np.array_equal(x, np.load(source / "embeddings.float16.npy"))
    assert b.score(out)["prediction_rows"] == 80
    b.summarize(out)
    assert b.read_tsv(out / "results/paired_deltas.tsv") == []
    metrics = b.read_tsv(out / "results/metrics.tsv")
    assert {r["panel"] for r in metrics} == {"observed_length"}
    empty = [r for r in metrics if r["length"] == "0-99"]
    assert empty and all(r["estimate"] == "" and r["parents"] == "0" for r in empty)
    if importlib.util.find_spec("matplotlib") is not None:  # optional figure extra
        b.plot(out)
        assert (out / "results/observed_length.pdf").stat().st_size > 1000
    assert not (out / "results/length_curves.pdf").exists()


@pytest.mark.parametrize("bad", ["revision", "pooling", "adapter", "checksum"])
def test_reuse_rejects_incompatible_or_corrupt_cache(cohort, bad):
    config, root, *_ = cohort
    config["evaluation_mode"] = "observed"
    old, out = root / "historical", root / "observed"
    b.prepare(config, root, old)
    historical_fixture(old)
    b.prepare(config, root, out)
    source = old / "embeddings/esm2_3b"
    meta = b.read_json(source / "metadata.json")
    if bad == "revision":
        meta["resolved_model_revision"] = "wrong"
    elif bad == "pooling":
        meta["pooling"] = "wrong"
    elif bad == "adapter":
        meta["adapter_options"]["replace_rare_with_x"] = True
    else:
        meta["untracked_edit"] = True
    b.write_json(source / "metadata.json", meta)
    if bad != "checksum":
        rehash(source)
    with pytest.raises(ValueError, match="mismatch"):
        b.reuse(out, "esm2_3b", source)
    assert not (out / "embeddings/esm2_3b").exists()


def test_reuse_excludes_protected_rows_and_marks_only_exact_matches_complete(cohort, monkeypatch):
    config, root, *_ = cohort
    config["evaluation_mode"] = "observed"
    old, out = root / "historical", root / "observed"
    b.prepare(config, root, old)
    historical_fixture(old)
    b.prepare(config, root, out)
    source = old / "embeddings/esm2_3b"
    rows = b.read_tsv(source / "index.tsv")
    rows[0]["split"] = "test"
    rows[1]["split"] = "validation"
    rows[2]["sequence_sha256"] = "0" * 64
    b.write_tsv(source / "index.tsv", rows)
    rehash(source)
    with pytest.raises(ValueError, match="37/40"):
        b.reuse(out, "esm2_3b", source, require_complete=True)
    result = b.reuse(out, "esm2_3b", source)
    assert result["reused_records"] == 37 and result["missing_records"] == 3
    dest = out / "embeddings/esm2_3b"
    assert np.load(dest / "completed.npy").tolist() == [False] * 3 + [True] * 37
    assert b.read_json(dest / "metadata.json")["status"] == "partial"
    with pytest.raises(ValueError, match="contract mismatch"):
        b.load_vectors(out, "esm2_3b")
    with pytest.raises(ValueError, match="already exists"):
        b.reuse(out, "esm2_3b", source)

    # Exercise the production resume loop without a neural model or GPU.
    import sys
    from types import SimpleNamespace
    from djrmcp_finder.stages import benchmark_embedding as embedding

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            __version__="test",
            version=SimpleNamespace(cuda=None),
            cuda=SimpleNamespace(is_available=lambda: False),
            device=lambda name: SimpleNamespace(type=name),
        ),
    )
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(__version__="test"))
    settings = b.embedding_settings(out, "esm2_3b")["embedding"]
    monkeypatch.setattr(
        embedding,
        "_load_adapter",
        lambda *_: SimpleNamespace(
            resolved_revision=settings["model_revision"], embedding_dim=4, parameter_count=0
        ),
    )
    seen = []

    def fake_encode(records, *_):
        seen.extend(r.protein_id for r in records)
        return np.full((len(records), 4), 7, dtype=np.float32)

    monkeypatch.setattr(embedding, "_embed_record_batch", fake_encode)
    assert b.embed(out, "esm2_3b", "cpu", 1)["completed_records"] == 38
    assert b.embed(out, "esm2_3b", "cpu", None)["status"] == "complete"
    assert len(seen) == len(set(seen)) == 3
    completed_vectors, _ = b.load_vectors(out, "esm2_3b")
    assert np.array_equal(completed_vectors[3:], np.load(source / "embeddings.float16.npy")[3:])
    assert np.all(completed_vectors[:3] == 7)
