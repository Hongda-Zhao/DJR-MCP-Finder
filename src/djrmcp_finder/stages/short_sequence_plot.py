"""Presentation of observed-length metrics; no scoring or model operations."""

LENGTH_BINS = ("0-99", "100-129", "130-149", "150-199", "200-249", "250-299", "300+")


def plot_observed(out, read_tsv, length_bins=LENGTH_BINS):
    """Discrete bins, explicit missing estimates, and the actual denominators."""
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 7,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    rows = [
        r
        for r in read_tsv(out / "results/metrics.tsv")
        if r["panel"] == "observed_length" and r["source_dataset"] == "all"
    ]
    table = {(r["method"], r["length"], r["metric"]): r for r in rows}
    methods = (("v0", "#0072B2", "V0"), ("v01_candidate", "#D55E00", "V0.1 recipe"))
    panels = (
        ("mcp_recall", "MCP detection recall"),
        ("mcp_fpr", "MCP false-positive rate"),
        ("h1_recall", "H1 DJR recall"),
        ("h3_end_to_end_recall_Nucleocytoviricota", "Nucleocytoviricota recall (end-to-end)"),
        ("h3_end_to_end_recall_Preplasmiviricota", "Preplasmiviricota recall (end-to-end)"),
    )
    fig, axes = plt.subplots(3, 2, figsize=(7.2, 7.1), constrained_layout=True)
    x = np.arange(len(length_bins))
    for panel_index, (ax, (metric, title)) in enumerate(zip(axes.flat, panels)):
        for j, (method, color, label) in enumerate(methods):
            for i, length in enumerate(length_bins):
                row = table.get((method, length, metric))
                if not row or row["estimate"] == "":
                    continue
                estimate = float(row["estimate"])
                # Percentile intervals need not contain the point estimate.
                xpos = i + (j - 0.5) * 0.18
                if row["ci_low"] != "":
                    ax.vlines(xpos, float(row["ci_low"]), float(row["ci_high"]), color=color, lw=1)
                ax.plot(
                    xpos,
                    estimate,
                    "o",
                    ms=4,
                    color=color,
                    label=label
                    if i
                    == next(
                        k
                        for k, z in enumerate(length_bins)
                        if table[(method, z, metric)]["estimate"] != ""
                    )
                    else None,
                )
        labels = []
        for length in length_bins:
            r = table[("v01_candidate", length, metric)]
            n_label = f"n={r['parents']}" if r["parents"] != "0" else "NA; n=0"
            labels.append(length.replace("-", "–") + "\n" + n_label)
        ax.set(
            title=f"{'abcde'[panel_index]}  {title}",
            ylim=(-0.03, 1.04),
            xticks=x,
            xticklabels=labels,
            xlabel="Observed sequence length (aa)",
        )
        ax.tick_params(axis="x", labelsize=6)
        ax.xaxis.labelpad = 8
        if metric == "mcp_fpr":
            upper = max(
                float(r["ci_high"] or r["estimate"] or 0) for r in rows if r["metric"] == metric
            )
            ax.set_ylim(-0.0005, min(1.04, max(0.015, upper * 1.15)))
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        if panel_index == 0:
            ax.legend(frameon=False, loc="lower right")
    ax = axes.flat[-1]
    for j, (metric, color, label) in enumerate(
        (("mcp_recall", "#666666", "MCP"), ("mcp_fpr", "#BBBBBB", "Non-MCP"))
    ):
        counts = [int(table[("v01_candidate", z, metric)]["parents"]) for z in length_bins]
        bars = ax.bar(x + (j - 0.5) * 0.34, counts, 0.32, color=color, label=label)
        ax.bar_label(bars, fontsize=6, padding=2)
    ax.set(
        title="f  Evaluated proteins",
        xticks=x,
        xticklabels=[z.replace("-", "–") for z in length_bins],
        ylabel="Number of proteins",
        xlabel="Observed sequence length (aa)",
    )
    ax.tick_params(axis="x", labelsize=6)
    ax.legend(frameon=False, loc="upper left")
    ax.margins(y=0.18)
    fig.suptitle(
        "Observed-length benchmark | frozen historical embeddings\n"
        "Train-only component cross-fit; points and 95% component-bootstrap intervals",
        fontsize=9,
    )
    fig.savefig(out / "results/observed_length.png", dpi=300)
    fig.savefig(out / "results/observed_length.pdf")
    fig.savefig(out / "results/observed_length.svg")
    plt.close(fig)
    return out / "results/observed_length.pdf"
