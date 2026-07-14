"""Deterministic bootstrap confidence intervals for RaceBench reports."""
from __future__ import annotations

import random
from collections.abc import Iterable
from typing import Any

import pandas as pd

CI_METRICS = {
    "correct_rate": "correct",
    "mean_wall_s": "wall_clock_s",
    "mean_tokens": "total_tokens",
    "wasted_rate": "wasted_token_rate",
    "fp_stalls_per_trial": "fp_stall_events",
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _bootstrap_mean_ci(
    values: Iterable[Any],
    *,
    seed: str,
    n_boot: int,
    alpha: float,
) -> tuple[float, float, float]:
    nums = [float(v) for v in values]
    if not nums:
        return 0.0, 0.0, 0.0
    point = _mean(nums)
    if len(nums) == 1 or n_boot <= 0:
        return point, point, point

    rng = random.Random(seed)
    n = len(nums)
    boots = []
    for _ in range(n_boot):
        boots.append(_mean([nums[rng.randrange(n)] for _ in range(n)]))
    boots.sort()
    lo = _percentile(boots, alpha / 2)
    hi = _percentile(boots, 1 - alpha / 2)
    return point, lo, hi


def bootstrap_ci(
    df: pd.DataFrame,
    keys: list[str],
    *,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> pd.DataFrame:
    """Return point estimates and bootstrap CIs for a grouping.

    The seed is expanded with the group key and metric name, so results are
    stable across Python hash-randomization and independent of row ordering.
    """
    if df.empty:
        return pd.DataFrame()

    rows = []
    for group_key, group in df.groupby(keys, dropna=False, sort=True):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        row = {k: v for k, v in zip(keys, group_key)}
        if "task" not in keys and "task" in group.columns:
            row["n_tasks"] = int(group["task"].nunique())
        row["trials"] = int(len(group))

        key_seed = "|".join(str(v) for v in group_key)
        for out_name, source_col in CI_METRICS.items():
            point, lo, hi = _bootstrap_mean_ci(
                group[source_col],
                seed=f"{seed}:{key_seed}:{out_name}",
                n_boot=n_boot,
                alpha=alpha,
            )
            row[out_name] = point
            row[f"{out_name}_lo"] = lo
            row[f"{out_name}_hi"] = hi
        rows.append(row)

    return _round_ci(pd.DataFrame(rows))


def _round_ci(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    for col in df.columns:
        if col in {"correct_rate", "correct_rate_lo", "correct_rate_hi",
                   "wasted_rate", "wasted_rate_lo", "wasted_rate_hi",
                   "fp_stalls_per_trial", "fp_stalls_per_trial_lo",
                   "fp_stalls_per_trial_hi"}:
            df[col] = df[col].round(3)
        elif col in {"mean_wall_s", "mean_wall_s_lo", "mean_wall_s_hi"}:
            df[col] = df[col].round(1)
        elif col in {"mean_tokens", "mean_tokens_lo", "mean_tokens_hi"}:
            df[col] = df[col].round(0)
    return df


def confidence_tables(
    df: pd.DataFrame,
    *,
    n_boot: int = 1000,
    seed: int = 0,
) -> dict[str, pd.DataFrame]:
    """Build CI tables matching the standard report aggregations."""
    if df.empty:
        return {
            "comparison_table_ci": pd.DataFrame(),
            "comparison_table_overall_ci": pd.DataFrame(),
            "comparison_table_by_strategy_ci": pd.DataFrame(),
        }
    return {
        "comparison_table_ci": bootstrap_ci(
            df, ["task", "strategy", "n_agents"], n_boot=n_boot, seed=seed),
        "comparison_table_overall_ci": bootstrap_ci(
            df, ["strategy", "n_agents"], n_boot=n_boot, seed=seed),
        "comparison_table_by_strategy_ci": bootstrap_ci(
            df, ["strategy"], n_boot=n_boot, seed=seed),
    }
