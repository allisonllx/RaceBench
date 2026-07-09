"""Comparison plots from the aggregated metric table."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

FIGURES_DIR = Path(__file__).resolve().parent / "figures"

METRIC_SPECS = [
    ("correct_rate", "Correctness rate", "higher is better"),
    ("mean_tokens", "Mean tokens per trial", "lower is better"),
    ("wasted_rate", "Wasted-token rate", "lower is better"),
    ("fp_stalls_per_trial", "False-positive stalls per trial", "lower is better"),
]


def grouped_bars(agg: pd.DataFrame, metric: str, title: str, note: str,
                 out: Path) -> Path:
    pivot = agg.pivot_table(index="task", columns="strategy", values=metric,
                            aggfunc="mean")
    ax = pivot.plot(kind="bar", figsize=(9, 4.5), width=0.8)
    ax.set_title(f"{title}  ({note})")
    ax.set_xlabel("")
    ax.set_ylabel(metric)
    ax.legend(title="strategy", fontsize=8)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    return out


def make_all_plots(agg: pd.DataFrame, out_dir: Path = FIGURES_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for metric, title, note in METRIC_SPECS:
        if metric in agg.columns:
            paths.append(grouped_bars(agg, metric, title, note,
                                      out_dir / f"{metric}.png"))
    return paths
