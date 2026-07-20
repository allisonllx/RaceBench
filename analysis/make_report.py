"""Generate comparison tables (CSV + markdown) and plots for a run.

Writes:
  - comparison_table: per (task, strategy, n_agents)
  - comparison_table_overall: across tasks, per (strategy, n_agents)
  - comparison_table_by_strategy: across tasks and n, per strategy
  - comparison_table*_ci: bootstrap confidence intervals for key metrics
  - report.html: static results explorer

Usage:
    python -m analysis.make_report results/<run_id>
    python -m analysis.make_report results/<run_id> --prices-config runner/configs/config.example.yaml
    python -m analysis.make_report results/grid-v1 results/grid-v1-extensions --out results/grid-v1-plus-extensions

USD is derived from prompt/completion token counts on each trial_end event and
the price table (run_meta.json in the run dir, --prices-config, or defaults).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from analysis.confidence import confidence_tables
from analysis.html_report import write_html_report
from analysis.metrics import (
    aggregate,
    aggregate_by_strategy,
    aggregate_overall,
    agent_activity_dataframe,
    event_profile_by_strategy,
    event_profile_by_task_strategy,
    level_a_dataframe,
    run_dataframe,
)
from analysis.plots import make_all_plots
from harness.pricing import load_prices, load_prices_from_config, write_run_meta


def _write_table(df: pd.DataFrame, out_dir: Path, stem: str) -> str:
    df.to_csv(out_dir / f"{stem}.csv", index=False)
    md = df.to_markdown(index=False)
    (out_dir / f"{stem}.md").write_text(md + "\n", encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", help="results/<run_id> directories")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory for combined tables/report (default: first run dir)",
    )
    parser.add_argument(
        "--prices-config",
        type=Path,
        default=None,
        help="runner YAML with a prices: block (overrides run_meta.json)",
    )
    args = parser.parse_args(argv)

    source_dirs = [Path(d) for d in args.run_dirs]
    out_dir = args.out or source_dirs[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.prices_config is not None:
        prices = load_prices_from_config(args.prices_config)
    else:
        prices = load_prices(source_dirs[0])

    frames = [run_dataframe(d, prices=prices) for d in source_dirs]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) \
        if any(not f.empty for f in frames) else pd.DataFrame()
    if df.empty:
        print("no trial logs found", file=sys.stderr)
        return 1

    # Persist prices used for this report (backfills runs started before meta).
    if source_dirs:
        meta_path = out_dir / "run_meta.json"
        existing_meta = (
            json.loads(meta_path.read_text(encoding="utf-8"))
            if meta_path.is_file() else {}
        )
        write_run_meta(
            out_dir,
            run_id=out_dir.name,
            model=str(df["model"].mode().iloc[0]) if "model" in df else "",
            mode=str(existing_meta.get("mode", "openai")),
            provider=existing_meta.get("provider"),
            base_url=existing_meta.get("base_url"),
            prices=prices,
            budget=existing_meta.get("budget"),
        )

    df.to_csv(out_dir / "trials.csv", index=False)
    level_a = level_a_dataframe(df)
    external = df[df["mode"] == "external"].copy() if "mode" in df else pd.DataFrame()

    agg = aggregate(level_a)
    overall = aggregate_overall(level_a)
    by_strategy = aggregate_by_strategy(level_a)
    event_by_strategy = event_profile_by_strategy(level_a)
    event_by_task_strategy = event_profile_by_task_strategy(level_a)
    agent_frames = [agent_activity_dataframe(d) for d in source_dirs]
    agent_activity = (
        pd.concat([f for f in agent_frames if not f.empty], ignore_index=True)
        if any(not f.empty for f in agent_frames) else pd.DataFrame()
    )
    ci = confidence_tables(level_a)

    print("=== per task × strategy × n_agents ===")
    print(_write_table(agg, out_dir, "comparison_table"))
    print("\n=== overall (all tasks) × strategy × n_agents ===")
    print(_write_table(overall, out_dir, "comparison_table_overall"))
    print("\n=== overall (all tasks, all n) × strategy ===")
    print(_write_table(by_strategy, out_dir, "comparison_table_by_strategy"))
    print("\n=== event profile × strategy ===")
    print(_write_table(event_by_strategy, out_dir, "event_profile_by_strategy"))
    print("\n=== event profile × task × strategy × n_agents ===")
    print(_write_table(
        event_by_task_strategy, out_dir, "event_profile_by_task_strategy"))
    print("\n=== agent activity ===")
    _write_table(agent_activity, out_dir, "agent_activity")
    print(f"agent_activity -> {out_dir}/agent_activity.csv|.md "
          f"({len(agent_activity)} rows)")
    print("\n=== bootstrap confidence intervals ===")
    for stem, table in ci.items():
        print(f"{stem} -> {out_dir}/{stem}.csv|.md")
        _write_table(table, out_dir, stem)

    total_usd = df["estimated_usd"].sum()
    total_tokens = df["total_tokens"].sum()
    figures = (
        make_all_plots(agg, overall=overall, by_strategy=by_strategy)
        if not agg.empty else []
    )
    html = write_html_report(
        out_dir=out_dir,
        trials=df,
        level_a_trials=level_a,
        external_trials=external,
        aggregate=agg,
        overall=overall,
        by_strategy=by_strategy,
        by_strategy_ci=ci.get("comparison_table_by_strategy_ci"),
        event_by_strategy=event_by_strategy,
        event_by_task_strategy=event_by_task_strategy,
        agent_activity=agent_activity,
    )
    print(f"\nper-trial rows: {len(df)}  ->  {out_dir}/trials.csv")
    print(f"per-task table -> {out_dir}/comparison_table.csv|.md")
    print(f"overall table  -> {out_dir}/comparison_table_overall.csv|.md")
    print(f"by-strategy    -> {out_dir}/comparison_table_by_strategy.csv|.md")
    print(f"event profile  -> {out_dir}/event_profile_by_strategy.csv|.md")
    print(f"agent activity -> {out_dir}/agent_activity.csv|.md")
    print(f"static explorer -> {html}")
    print(f"run cost (priced trials): ${total_usd:.2f}  ({int(total_tokens):,} tokens)")
    for f in figures:
        print(f"figure -> {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
