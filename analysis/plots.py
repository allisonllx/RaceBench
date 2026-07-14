"""Comparison plots from the aggregated metric table."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_CACHE_DIR = Path(tempfile.gettempdir()) / "racebench-cache"
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(_CACHE_DIR / "matplotlib"))

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


def strategy_bars(overall: pd.DataFrame, metric: str, title: str, note: str,
                  out: Path, *, index_col: str = "strategy") -> Path:
    """Single-level bar chart (across-task rollup)."""
    plot_df = overall
    if "n_agents" in overall.columns and index_col == "strategy":
        # Prefer one bar group per strategy when multiple n cells exist.
        if overall["n_agents"].nunique() > 1:
            pivot = overall.pivot_table(
                index="strategy", columns="n_agents", values=metric,
                aggfunc="mean")
            ax = pivot.plot(kind="bar", figsize=(7, 4), width=0.8)
            ax.legend(title="n_agents", fontsize=8)
        else:
            plot_df = overall.set_index("strategy")
            ax = plot_df[metric].plot(kind="bar", figsize=(7, 4), width=0.7)
    else:
        plot_df = overall.set_index(index_col)
        ax = plot_df[metric].plot(kind="bar", figsize=(7, 4), width=0.7)
    ax.set_title(f"{title}  ({note})")
    ax.set_xlabel("")
    ax.set_ylabel(metric)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    return out


def make_all_plots(agg: pd.DataFrame, out_dir: Path = FIGURES_DIR,
                   overall: pd.DataFrame | None = None,
                   by_strategy: pd.DataFrame | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for metric, title, note in METRIC_SPECS:
        if metric in agg.columns:
            paths.append(grouped_bars(agg, metric, title, note,
                                      out_dir / f"{metric}.png"))
        if overall is not None and metric in overall.columns:
            paths.append(strategy_bars(
                overall, metric, f"Overall {title}", note,
                out_dir / f"overall_{metric}.png"))
        if by_strategy is not None and metric in by_strategy.columns:
            paths.append(strategy_bars(
                by_strategy, metric, f"Overall {title} (all n)", note,
                out_dir / f"by_strategy_{metric}.png",
                index_col="strategy"))
    return paths
