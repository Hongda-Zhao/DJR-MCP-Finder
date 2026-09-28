#!/usr/bin/env python3
"""Re-bin frozen cross-fit predictions; no model fitting or encoder inference."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import benchmark as b

EDGES = (250, 300, 350, 400, 450, 500)
LABELS = ("<250", "250-299", "300-349", "350-399", "400-449", "450-499", "500+")
METRICS = (
    "mcp_recall",
    "mcp_fpr",
    "h1_recall",
    "h1_fpr",
    "h2_conditional_recall",
    "h2_conditional_fpr",
    "h3_known_end_to_end_recall",
    "h3_known_gated_accuracy",
    "h3_known_gated_reject_rate",
    "h3_known_gated_wrong_phylum_rate",
    "h3_unknown_gated_reject_rate",
    *("h3_end_to_end_recall_" + p for p in b.KNOWN),
)


def length_bin(length):
    if length < 1:
        raise ValueError("Length must be positive")
    for i, edge in enumerate(EDGES):
        if length < edge:
            return LABELS[i]
    return LABELS[-1]


def aggregate(rows, config):
    # Only original proteins: fragments must never inflate observed-bin counts.
    rows = [r for r in rows if r["position"] == "full"]
    seen = set()
    grouped = defaultdict(list)
    for row in rows:
        key = row["method"], row["parent_id"]
        if key in seen or row["method"] not in config["methods"]:
            raise ValueError("Duplicate or unexpected full-parent prediction")
        seen.add(key)
        group = length_bin(int(row["length_aa"]))
        grouped[(row["method"], group, "all")].append(row)
        grouped[(row["method"], group, row["source_dataset"])].append(row)
    summaries, counts = [], []
    for method in config["methods"]:
        for group in LABELS:
            records = grouped[(method, group, "all")]
            tp = sum(r["is_mcp"] == "1" and r["mcp_positive"] == "1" for r in records)
            fp = sum(r["is_mcp"] == "0" and r["mcp_positive"] == "1" for r in records)
            pos = sum(r["is_mcp"] == "1" for r in records)
            neg = len(records) - pos
            counts.append(
                {
                    "method": method,
                    "length_bin_aa": group,
                    "total": len(records),
                    "positive_n": pos,
                    "negative_n": neg,
                    "tp": tp,
                    "fn": pos - tp,
                    "fp": fp,
                    "tn": neg - fp,
                    "recall": tp / pos if pos else "",
                    "fpr": fp / neg if neg else "",
                }
            )
            for source in ("all", *sorted(b.SOURCES)):
                selected = grouped[(method, group, source)]
                by_metric = defaultdict(dict)
                for row in selected:
                    for metric, value in b.outcomes(row).items():
                        by_metric[metric][row["parent_id"]] = (row["global_component_id"], value)
                for metric in METRICS:
                    values = by_metric[metric]
                    summaries.append(
                        {
                            "method": method,
                            "panel": "observed_length",
                            "length": group,
                            "position": "full",
                            "source_dataset": source,
                            "metric": metric,
                            **b.cluster_interval(
                                values, config["bootstrap_replicates"], config["seed"]
                            ),
                            "successes": sum(v for _, v in values.values()),
                            "eligible_fragments": len(values),
                        }
                    )
    for method in config["methods"]:
        assert sum(r["total"] for r in counts if r["method"] == method) == sum(
            r["method"] == method for r in rows
        )
    return summaries, counts


def run(source_run, out):
    import numpy as np
    import matplotlib

    matplotlib.use("Agg")
    from djrmcp_finder.stages.short_sequence_plot import plot_observed

    config, predictions = b.validated_predictions(source_run)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a new output directory to retain earlier reports")
    summaries, counts = aggregate(predictions, config)
    results = out / "results"
    b.write_tsv(results / "metrics.tsv", summaries)
    b.write_tsv(results / "confusion_by_length.tsv", counts)
    plot_observed(out, b.read_tsv, length_bins=LABELS)
    report = [
        "# Observed-length benchmark: 50-aa bins from 250 aa",
        "",
        "Train-only component cross-fit on 6,634 original proteins; existing predictions reused.",
        "Bins [250,300), [300,350), [350,400), [400,450), [450,500), [500,infinity).",
        "The <250-aa bin is retained as an evidence-gap and false-positive diagnostic.",
        "This is a descriptive re-binning requested after the initial analysis, not a new test or threshold optimization.",
        "Full model weights, fold membership, calibration and predictions are unchanged.",
        "95% intervals resample components 2,000 times; all-success/all-failure intervals are not population bounds.",
        "No MCP positives below 250 aa means recall is not estimable, not zero or proof all predictions are wrong.",
        "Different length bins have different protein/family mixtures. Precision here would depend on this curated prevalence.",
        "",
        "| Method | Length (aa) | MCP positives | Recall | Non-MCP | False positives | FPR |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in counts:
        recall = f"{row['recall']:.2%}" if row["recall"] != "" else "NA"
        fpr = f"{row['fpr']:.3%}" if row["fpr"] != "" else "NA"
        report.append(
            f"| {row['method']} | {row['length_bin_aa']} | {row['positive_n']} | {recall} | {row['negative_n']} | {row['fp']} | {fpr} |"
        )
    (results / "REPORT.md").write_text("\n".join(report) + "\n")
    receipt = {
        "status": "PASS",
        "scope": "TRAIN_ONLY_DESCRIPTIVE_REBINNING_OF_FROZEN_CROSSFIT",
        "bin_labels": LABELS,
        "bin_upper_edges_exclusive_aa": EDGES,
        "source_score_receipt_sha256": b.digest(source_run / "scores/receipt.json"),
        "source_predictions_sha256": b.digest(source_run / "scores/predictions.tsv"),
        "source_fold_contracts_sha256": b.digest(source_run / "scores/fold_contracts.tsv"),
        "script_sha256": b.digest(Path(__file__)),
        "statistics_script_sha256": b.digest(Path(b.__file__)),
        "plot_script_sha256": b.digest(
            Path(__import__(plot_observed.__module__, fromlist=["x"]).__file__)
        ),
        "bootstrap_replicates": config["bootstrap_replicates"],
        "seed": config["seed"],
        "numpy": np.__version__,
        "gpu_used": False,
        "new_model_fits": 0,
        "validation_scored": 0,
        "test_scored": 0,
        "files": {p.name: b.digest(p) for p in results.iterdir()},
    }
    b.write_json(results / "receipt.json", receipt)
    return {
        "status": "PASS",
        "confusion_rows": len(counts),
        "metric_rows": len(summaries),
        "results": str(results),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(run(args.run.resolve(), args.out.resolve()))
