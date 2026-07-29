import json
from pathlib import Path

from djrmcp_predict.cli import main


def test_validate_fasta_command(tmp_path: Path, capsys) -> None:
    fasta = tmp_path / "input.faa"
    fasta.write_text(
        ">p1\n" + "ACDEFGHIKLMNPQRSTVWY" * 7 + "\n", encoding="utf-8"
    )
    assert main(["validate-fasta", str(fasta)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "valid"
    assert output["record_count"] == 1


def test_model_info_verifies_release(tiny_release: Path, capsys) -> None:
    assert main(["model-info", "--release", str(tiny_release)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["release_id"] == "tiny-test-release"


def test_cli_returns_nonzero_for_invalid_fasta(tmp_path: Path, capsys) -> None:
    fasta = tmp_path / "invalid.faa"
    fasta.write_text(">p1\nACD*\n", encoding="utf-8")
    assert main(["validate-fasta", str(fasta)]) == 2
    assert "Unsupported residue" in capsys.readouterr().err


def test_predict_command_packages_outputs_without_real_gpu(
    tiny_release: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    fasta = tmp_path / "input.faa"
    fasta.write_text(
        ">p1 example\n" + "ACDEFGHIKLMNPQRSTVWY" * 7 + "\n", encoding="utf-8"
    )

    class FakeEmbedder:
        def __init__(self, *args, **kwargs):
            pass

        def embed_sequences(self, sequences):
            import numpy as np

            return np.asarray([[-2.0, 0.0, 0.0] for _ in sequences], dtype=np.float32)

        def runtime_metadata(self):
            return {"device": "mock", "resolved_model_revision": "1" * 40}

    monkeypatch.setattr("djrmcp_predict.cli.EsmcEmbedder", FakeEmbedder)
    outdir = tmp_path / "run"
    code = main(
        [
            "predict",
            str(fasta),
            "--outdir",
            str(outdir),
            "--release",
            str(tiny_release),
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["final_prediction_counts"] == {"non_djr": 1}
    assert (outdir / "predictions.tsv").is_file()
    assert (outdir / "run_metadata.json").is_file()
    assert (outdir / "CHECKSUMS.sha256").is_file()
