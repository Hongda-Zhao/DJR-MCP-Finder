from __future__ import annotations

import csv
import json

import pytest

from djrmcp_predict_v01 import cli
from djrmcp_predict_v01 import v02_preview as preview
from djrmcp_predict_v01.fasta import read_protein_fasta
from djrmcp_predict_v01.output import PREDICTION_FIELDS, write_run
from djrmcp_predict_v01.release import sha256_file


def fasta(tmp_path, entries):
    path = tmp_path / "input.faa"
    path.write_text("".join(f">{name}\n{seq}\n" for name, seq in entries))
    return path


def run(path, output, *extra):
    return preview.main(["predict", str(path), "--outdir", str(output), *extra])


def read_run(output):
    with (output / "predictions.tsv").open() as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    metadata = json.loads((output / "run_metadata.json").read_text())
    assert metadata["predictions_sha256"] == sha256_file(output / "predictions.tsv")
    assert (output / "CHECKSUMS.sha256").read_text().splitlines() == [
        f"{sha256_file(output / name)}  {name}" for name in ("predictions.tsv", "run_metadata.json")
    ]
    return rows, metadata


def test_all_short_skips_entire_baseline_and_missing_dependencies(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Short inputs must not load releases or invoke workers")

    monkeypatch.setattr(cli, "_predict_command", forbidden)
    monkeypatch.setattr(preview, "load_release", forbidden)
    path = fasta(tmp_path, [("short full header", "M" * 249), ("tiny", "M")])
    output = tmp_path / "output"
    assert (
        run(
            path,
            output,
            "--device",
            "cuda",
            "--release",
            "/missing",
            "--esm2-python",
            "/missing",
            "--esmc-python",
            "/missing",
        )
        == 0
    )
    rows, metadata = read_run(output)
    assert [r["final_prediction"] for r in rows] == [preview.SHORT_LABEL] * 2
    assert rows[0]["original_header"] == "short full header"
    for row in rows:
        assert row["status"] == "not_evaluated_short_sequence"
        assert row["head3_reached"] == "0"
        assert "length_below_250_aa" in row["warnings"]
        for field in PREDICTION_FIELDS:
            if "probability" in field or "raw_score" in field or "confidence" in field:
                assert row[field] == "NA"
            if field.startswith("head") and field.endswith(("prediction", "encoder")):
                assert row[field] == "not_reached"
    assert metadata["routing"]["scoring_coverage"] == 0
    assert metadata["baseline_subset_run"] is None


def install_baseline(monkeypatch, *, tamper=None):
    observed = []
    emitted = []

    def baseline(args):
        records = read_protein_fasta(args.fasta)
        observed.extend(records)
        rows = []
        for record in records:
            row = preview._short_row(record)
            row.update(
                status="ok",
                final_prediction="djr_non_mcp",
                head1_encoder="esm2_3b",
                head1_prediction="djr",
                head1_djr_probability=0.9123456789012345,
                head2_encoder="esm2_3b",
                head2_raw_prediction="none",
                head2_operational_prediction="none",
                head2_mcp_probability=0.1,
                warnings=";".join(record.warnings),
            )
            rows.append(row)
        if tamper == "order":
            rows.reverse()
        write_run(args.outdir, rows, {"schema_version": 3, "status": "complete"})
        with (args.outdir / "predictions.tsv").open() as handle:
            emitted.extend(csv.DictReader(handle, delimiter="\t"))
        if tamper == "checksum":
            with (args.outdir / "predictions.tsv").open("a") as handle:
                handle.write("corruption\n")
        return 0

    monkeypatch.setattr(cli, "_predict_command", baseline)
    return observed, emitted


def test_mixed_boundary_order_duplicates_and_exact_score_passthrough(tmp_path, monkeypatch):
    observed, emitted = install_baseline(monkeypatch)
    path = fasta(
        tmp_path,
        [
            ("a", "m" * 249),
            ("b at boundary", "m " * 249 + "x"),
            ("c", "M"),
            ("d same sequence", "M" * 249 + "X"),
            ("e", "M" * 500),
        ],
    )
    output = tmp_path / "output"
    assert run(path, output) == 0
    assert [r.protein_id for r in observed] == ["b", "d", "e"]
    assert [r.length_aa for r in observed] == [250, 250, 500]
    rows, metadata = read_run(output)
    assert [r["input_row"] for r in rows] == ["1", "2", "3", "4", "5"]
    assert [r["protein_id"] for r in rows] == list("abcde")
    assert rows[0]["final_prediction"] == rows[2]["final_prediction"] == preview.SHORT_LABEL
    for row, source in zip((rows[1], rows[3], rows[4]), emitted, strict=True):
        assert {k: v for k, v in row.items() if k != "input_row"} == {
            k: v for k, v in source.items() if k != "input_row"
        }
    assert metadata["routing"]["scored_record_count"] == 3
    assert metadata["routing"]["abstained_record_count"] == 2
    assert metadata["routing"]["scoring_coverage"] == 0.6
    assert metadata["input"]["sha256"] == sha256_file(path)


@pytest.mark.parametrize("bad", ["M*", "", "ACGT" * 10])
def test_invalid_short_record_rejected_before_any_prediction(tmp_path, monkeypatch, bad):
    observed, _ = install_baseline(monkeypatch)
    path = fasta(tmp_path, [("long", "M" * 300), ("bad", bad)])
    assert run(path, tmp_path / "output") == 2
    assert observed == []
    assert not (tmp_path / "output" / "predictions.tsv").exists()


@pytest.mark.parametrize("tamper", ["order", "checksum"])
def test_bad_baseline_output_is_not_published(tmp_path, monkeypatch, tamper):
    install_baseline(monkeypatch, tamper=tamper)
    path = fasta(tmp_path, [("a", "M" * 250), ("b", "M" * 300), ("c", "M")])
    assert run(path, tmp_path / "output") == 2
    assert not (tmp_path / "output" / "predictions.tsv").exists()


def test_inference_failure_does_not_publish_partial_abstentions(tmp_path, monkeypatch):
    def failure(args):
        raise RuntimeError("worker failed")

    monkeypatch.setattr(cli, "_predict_command", failure)
    path = fasta(tmp_path, [("short", "M"), ("long", "M" * 250)])
    assert run(path, tmp_path / "output") == 2
    assert not (tmp_path / "output" / "predictions.tsv").exists()


def test_overwrite_is_explicit(tmp_path):
    path = fasta(tmp_path, [("a", "M")])
    output = tmp_path / "output"
    assert run(path, output) == 0
    before = (output / "predictions.tsv").read_bytes()
    path.write_text(">b\nMM\n")
    assert run(path, output) == 2
    assert (output / "predictions.tsv").read_bytes() == before
    assert run(path, output, "--overwrite") == 0
    assert read_run(output)[0][0]["protein_id"] == "b"


def test_duplicate_ids_still_rejected(tmp_path):
    path = fasta(tmp_path, [("same", "M"), ("same", "MM")])
    assert run(path, tmp_path / "output") == 2
