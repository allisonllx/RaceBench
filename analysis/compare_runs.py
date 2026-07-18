"""Cross-run comparisons for RaceBench result directories.

This module compares two different questions that should stay separate:

1. Provider/model sensitivity: same Level A cells, different model providers.
2. Solo calibration: one agent doing all subtasks versus parallel agent runs.

Usage:
    python -m analysis.compare_runs \
      --provider-runs results/grid-v1 results/grid-v1-agnes-sensitivity \
      --solo-run results/grid-v1-calibration \
      --out results/cross-run-analysis
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from analysis.cross_run_html import write_cross_run_dashboard
from analysis.metrics import level_a_dataframe, run_dataframe

CELL_KEYS = ["task", "strategy", "n_agents"]
METRIC_COLUMNS = [
    "correct_rate",
    "mean_wall_s",
    "mean_tokens",
    "mean_prompt_tokens",
    "mean_completion_tokens",
    "mean_estimated_usd",
    "wasted_rate",
    "stalls_per_trial",
    "fp_stalls_per_trial",
    "mean_agent_turns",
    "mean_llm_calls",
    "mean_tool_calls",
    "mean_file_reads",
    "mean_write_attempts",
    "mean_search_events",
    "mean_coord_events",
    "mean_tokens_per_agent_turn",
]
LOWER_IS_BETTER = {
    "mean_wall_s",
    "mean_tokens",
    "mean_prompt_tokens",
    "mean_completion_tokens",
    "mean_estimated_usd",
    "wasted_rate",
    "stalls_per_trial",
    "fp_stalls_per_trial",
    "mean_agent_turns",
    "mean_llm_calls",
    "mean_tool_calls",
    "mean_file_reads",
    "mean_write_attempts",
    "mean_search_events",
    "mean_coord_events",
    "mean_tokens_per_agent_turn",
}


def write_table(df: pd.DataFrame, out_dir: Path, stem: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{stem}.csv"
    md_path = out_dir / f"{stem}.md"
    df.to_csv(csv_path, index=False)
    md_path.write_text(df.to_markdown(index=False) + "\n", encoding="utf-8")
    return csv_path


def load_level_a_runs(run_dirs: list[Path]) -> pd.DataFrame:
    frames = []
    for run_dir in run_dirs:
        frame = run_dataframe(run_dir)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return level_a_dataframe(pd.concat(frames, ignore_index=True))


def build_provider_tables(run_dirs: list[Path]) -> dict[str, pd.DataFrame]:
    """Compare provider/model runs on the shared Level A cell intersection."""
    df = load_level_a_runs(run_dirs)
    if df.empty:
        return _empty_provider_tables()

    run_ids = [run_id for run_id in _ordered_unique(df["run_id"]) if run_id]
    if len(run_ids) < 2:
        return _empty_provider_tables()

    shared = _shared_cells(df, run_ids)
    if shared.empty:
        return _empty_provider_tables()

    provider_comparison = _metric_rollup(
        shared, ["run_id", "provider", "model"])
    provider_by_strategy = _metric_rollup(
        shared, ["run_id", "provider", "model", "strategy"])
    provider_by_task_strategy = _metric_rollup(
        shared, ["run_id", "provider", "model", *CELL_KEYS])

    baseline = run_ids[0]
    return {
        "provider_comparison": provider_comparison,
        "provider_by_strategy": provider_by_strategy,
        "provider_by_task_strategy": provider_by_task_strategy,
        "provider_delta_by_strategy": _delta_against_baseline(
            provider_by_strategy, baseline, ["strategy"]),
        "provider_delta_by_task_strategy": _delta_against_baseline(
            provider_by_task_strategy, baseline, CELL_KEYS),
    }


def build_solo_tables(solo_run: Path, parallel_run: Path) -> dict[str, pd.DataFrame]:
    """Compare solo calibration against a parallel Level A run."""
    solo = load_level_a_runs([solo_run])
    parallel = load_level_a_runs([parallel_run])
    if solo.empty or parallel.empty:
        return _empty_solo_tables()

    solo = solo[solo["n_agents"] == 1].copy()
    parallel = parallel[parallel["n_agents"] > 1].copy()
    common_tasks = sorted(set(solo["task"]) & set(parallel["task"]))
    if not common_tasks:
        return _empty_solo_tables()

    solo = solo[solo["task"].isin(common_tasks)]
    parallel = parallel[parallel["task"].isin(common_tasks)]

    solo_task = _metric_rollup(solo, ["task"])
    solo_prefixed = _prefix_metrics(solo_task, "solo")
    parallel_task_strategy = _metric_rollup(parallel, CELL_KEYS)
    parallel_prefixed = _prefix_metrics(parallel_task_strategy, "parallel")
    by_cell = solo_prefixed.merge(parallel_prefixed, on=["task"], how="inner")
    by_cell = _add_metric_deltas(by_cell, "solo", "parallel")
    by_cell.insert(0, "solo_run_id", str(solo["run_id"].iloc[0]))
    by_cell.insert(1, "parallel_run_id", str(parallel["run_id"].iloc[0]))
    by_cell.insert(
        2,
        "direction",
        by_cell["parallel_run_id"].astype(str)
        + " vs "
        + by_cell["solo_run_id"].astype(str),
    )
    by_cell = _round_table(by_cell)

    by_strategy = _solo_vs_parallel_by_strategy(solo, parallel)
    return {
        "solo_vs_parallel": by_cell,
        "solo_vs_parallel_by_strategy": by_strategy,
    }


def _shared_cells(df: pd.DataFrame, run_ids: list[str]) -> pd.DataFrame:
    cell_sets = []
    for run_id in run_ids:
        cells = set(
            tuple(row)
            for row in df.loc[df["run_id"] == run_id, CELL_KEYS]
            .drop_duplicates()
            .itertuples(index=False, name=None)
        )
        cell_sets.append(cells)
    common = set.intersection(*cell_sets) if cell_sets else set()
    if not common:
        return pd.DataFrame(columns=df.columns)
    marker = df[CELL_KEYS].apply(tuple, axis=1)
    return df[marker.isin(common)].copy()


def _metric_rollup(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["_cell"] = work[CELL_KEYS].astype(str).agg("|".join, axis=1)
    if not keys:
        row = {
            "n_tasks": int(work["task"].nunique()),
            "n_strategies": int(work["strategy"].nunique()),
            "n_cells": int(work["_cell"].nunique()),
            "trials": int(len(work)),
            "correct_rate": float(work["correct"].mean()),
            "mean_wall_s": float(work["wall_clock_s"].mean()),
            "mean_tokens": float(work["total_tokens"].mean()),
            "mean_prompt_tokens": float(work["prompt_tokens"].mean()),
            "mean_completion_tokens": float(work["completion_tokens"].mean()),
            "mean_estimated_usd": float(work["estimated_usd"].mean()),
            "wasted_rate": float(work["wasted_token_rate"].mean()),
            "stalls_per_trial": float(work["stall_events"].mean()),
            "fp_stalls_per_trial": float(work["fp_stall_events"].mean()),
            "mean_agent_turns": float(work["agent_turns"].mean()),
            "mean_llm_calls": float(work["llm_calls"].mean()),
            "mean_tool_calls": float(work["tool_calls"].mean()),
            "mean_file_reads": float(work["file_read_events"].mean()),
            "mean_write_attempts": float(work["write_events"].mean()),
            "mean_search_events": float(work["search_events"].mean()),
            "mean_coord_events": float(work["coord_events"].mean()),
            "mean_tokens_per_agent_turn": float(
                work["tokens_per_agent_turn"].mean()),
        }
        return _round_table(pd.DataFrame([row]))
    agg = work.groupby(keys, dropna=False).agg(
        n_tasks=("task", "nunique"),
        n_strategies=("strategy", "nunique"),
        n_cells=("_cell", "nunique"),
        trials=("correct", "size"),
        correct_rate=("correct", "mean"),
        mean_wall_s=("wall_clock_s", "mean"),
        mean_tokens=("total_tokens", "mean"),
        mean_prompt_tokens=("prompt_tokens", "mean"),
        mean_completion_tokens=("completion_tokens", "mean"),
        mean_estimated_usd=("estimated_usd", "mean"),
        wasted_rate=("wasted_token_rate", "mean"),
        stalls_per_trial=("stall_events", "mean"),
        fp_stalls_per_trial=("fp_stall_events", "mean"),
        mean_agent_turns=("agent_turns", "mean"),
        mean_llm_calls=("llm_calls", "mean"),
        mean_tool_calls=("tool_calls", "mean"),
        mean_file_reads=("file_read_events", "mean"),
        mean_write_attempts=("write_events", "mean"),
        mean_search_events=("search_events", "mean"),
        mean_coord_events=("coord_events", "mean"),
        mean_tokens_per_agent_turn=("tokens_per_agent_turn", "mean"),
    ).reset_index()
    return _round_table(agg)


def _delta_against_baseline(
    summary: pd.DataFrame,
    baseline_run_id: str,
    keys: list[str],
) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()

    base = summary[summary["run_id"] == baseline_run_id].copy()
    compare = summary[summary["run_id"] != baseline_run_id].copy()
    if base.empty or compare.empty:
        return pd.DataFrame()

    base_meta_cols = {
        "run_id": "baseline_run_id",
        "provider": "baseline_provider",
        "model": "baseline_model",
        "trials": "baseline_trials",
        "n_cells": "baseline_cells",
    }
    compare_meta_cols = {
        "run_id": "compare_run_id",
        "provider": "compare_provider",
        "model": "compare_model",
        "trials": "compare_trials",
        "n_cells": "compare_cells",
    }
    base_cols = keys + list(base_meta_cols) + METRIC_COLUMNS
    compare_cols = keys + list(compare_meta_cols) + METRIC_COLUMNS
    base = base[base_cols].rename(columns=base_meta_cols)
    compare = compare[compare_cols].rename(columns=compare_meta_cols)
    base = base.rename(columns={m: f"baseline_{m}" for m in METRIC_COLUMNS})
    compare = compare.rename(columns={m: f"compare_{m}" for m in METRIC_COLUMNS})

    merged = compare.merge(base, on=keys, how="inner")
    merged["direction"] = (
        merged["compare_run_id"].astype(str)
        + " vs "
        + merged["baseline_run_id"].astype(str)
    )
    ordered = (
        keys
        + ["baseline_run_id", "baseline_provider", "baseline_model",
           "compare_run_id", "compare_provider", "compare_model",
           "direction", "baseline_trials", "compare_trials",
           "baseline_cells", "compare_cells"]
    )
    merged = merged[ordered + [
        c for c in merged.columns if c not in ordered
    ]]
    for metric in METRIC_COLUMNS:
        delta = merged[f"compare_{metric}"] - merged[f"baseline_{metric}"]
        if metric in LOWER_IS_BETTER:
            delta = -delta
        merged[f"delta_{metric}"] = delta
    return _round_table(merged)


def _solo_vs_parallel_by_strategy(
    solo: pd.DataFrame,
    parallel: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    solo_run_id = str(solo["run_id"].iloc[0])
    parallel_run_id = str(parallel["run_id"].iloc[0])
    for strategy in sorted(parallel["strategy"].dropna().unique()):
        parallel_part = parallel[parallel["strategy"] == strategy]
        tasks = sorted(parallel_part["task"].unique())
        solo_part = solo[solo["task"].isin(tasks)]
        solo_rollup = _metric_rollup(solo_part, [])
        parallel_rollup = _metric_rollup(parallel_part, [])
        if solo_rollup.empty or parallel_rollup.empty:
            continue
        row = {
            "strategy": strategy,
            "solo_run_id": solo_run_id,
            "parallel_run_id": parallel_run_id,
            "direction": f"{parallel_run_id} vs {solo_run_id}",
            "n_tasks": len(tasks),
            "solo_trials": int(solo_rollup["trials"].iloc[0]),
            "parallel_trials": int(parallel_rollup["trials"].iloc[0]),
            "parallel_cells": int(parallel_rollup["n_cells"].iloc[0]),
        }
        for metric in METRIC_COLUMNS:
            row[f"solo_{metric}"] = float(solo_rollup[metric].iloc[0])
            row[f"parallel_{metric}"] = float(parallel_rollup[metric].iloc[0])
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return _round_table(_add_metric_deltas(df, "solo", "parallel"))


def _prefix_metrics(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    rename = {
        "n_tasks": f"{prefix}_n_tasks",
        "n_strategies": f"{prefix}_n_strategies",
        "n_cells": f"{prefix}_cells",
        "trials": f"{prefix}_trials",
    }
    rename.update({metric: f"{prefix}_{metric}" for metric in METRIC_COLUMNS})
    return df.rename(columns=rename)


def _add_metric_deltas(
    df: pd.DataFrame,
    left_prefix: str,
    right_prefix: str,
) -> pd.DataFrame:
    for metric in METRIC_COLUMNS:
        left = f"{left_prefix}_{metric}"
        right = f"{right_prefix}_{metric}"
        if left not in df.columns or right not in df.columns:
            continue
        delta = df[right] - df[left]
        if metric in LOWER_IS_BETTER:
            delta = -delta
        df[f"delta_{metric}"] = delta
    return df


def _round_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        if col.endswith("correct_rate") or col.endswith("wasted_rate"):
            out[col] = out[col].round(3)
        elif col.endswith("wall_s"):
            out[col] = out[col].round(1)
        elif col.endswith("tokens"):
            out[col] = out[col].round(0)
        elif col.endswith("_usd"):
            out[col] = out[col].round(4)
        elif col.endswith("per_trial"):
            out[col] = out[col].round(3)
        elif col.endswith("turns") or col.endswith("calls"):
            out[col] = out[col].round(2)
        elif col.endswith("reads") or col.endswith("attempts"):
            out[col] = out[col].round(2)
        elif col.endswith("events"):
            out[col] = out[col].round(2)
        elif col.endswith("per_agent_turn"):
            out[col] = out[col].round(0)
        elif col.startswith("delta_"):
            out[col] = out[col].round(3)
    return out


def _ordered_unique(values: pd.Series) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _empty_provider_tables() -> dict[str, pd.DataFrame]:
    return {
        "provider_comparison": pd.DataFrame(),
        "provider_by_strategy": pd.DataFrame(),
        "provider_by_task_strategy": pd.DataFrame(),
        "provider_delta_by_strategy": pd.DataFrame(),
        "provider_delta_by_task_strategy": pd.DataFrame(),
    }


def _empty_solo_tables() -> dict[str, pd.DataFrame]:
    return {
        "solo_vs_parallel": pd.DataFrame(),
        "solo_vs_parallel_by_strategy": pd.DataFrame(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-runs", nargs="+", type=Path, default=[])
    parser.add_argument("--solo-run", type=Path, default=None)
    parser.add_argument(
        "--parallel-run",
        type=Path,
        default=None,
        help="parallel run for solo comparison; defaults to first provider run",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    wrote: list[Path] = []
    dashboard_tables: dict[str, pd.DataFrame] = {}
    if args.provider_runs:
        provider_tables = build_provider_tables(args.provider_runs)
        dashboard_tables.update(provider_tables)
        for stem, table in provider_tables.items():
            wrote.append(write_table(table, args.out, stem))

    if args.solo_run:
        parallel_run = args.parallel_run or (
            args.provider_runs[0] if args.provider_runs else None)
        if parallel_run is None:
            print("--solo-run requires --parallel-run or --provider-runs",
                  file=sys.stderr)
            return 2
        solo_tables = build_solo_tables(args.solo_run, parallel_run)
        dashboard_tables.update(solo_tables)
        for stem, table in solo_tables.items():
            wrote.append(write_table(table, args.out, stem))

    if not wrote:
        print("nothing to compare: pass --provider-runs and/or --solo-run",
              file=sys.stderr)
        return 2

    dashboard = write_cross_run_dashboard(args.out, dashboard_tables)

    print(f"wrote {len(wrote)} tables to {args.out}")
    for path in wrote:
        print(f"table -> {path}")
    print(f"dashboard -> {dashboard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
