"""Generate the comparison table (CSV + markdown) and plots for a run.

Usage:
    python -m analysis.make_report results/<run_id>
    python -m analysis.make_report results/<run_id> --prices-config runner/config.example.yaml

USD is derived from prompt/completion token counts on each trial_end event and
the price table (run_meta.json in the run dir, --prices-config, or defaults).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from analysis.metrics import aggregate, run_dataframe
from analysis.plots import make_all_plots
from harness.pricing import load_prices, load_prices_from_config, write_run_meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", help="results/<run_id> directories")
    parser.add_argument(
        "--prices-config",
        type=Path,
        default=None,
        help="runner YAML with a prices: block (overrides run_meta.json)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.run_dirs[0])
    if args.prices_config is not None:
        prices = load_prices_from_config(args.prices_config)
    else:
        prices = load_prices(out_dir)

    frames = [run_dataframe(Path(d), prices=prices) for d in args.run_dirs]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) \
        if any(not f.empty for f in frames) else pd.DataFrame()
    if df.empty:
        print("no trial logs found", file=sys.stderr)
        return 1

    # Persist prices used for this report (backfills runs started before meta).
    if args.run_dirs:
        write_run_meta(
            out_dir,
            run_id=out_dir.name,
            model=str(df["model"].mode().iloc[0]) if "model" in df else "",
            mode="openai",
            prices=prices,
        )

    df.to_csv(out_dir / "trials.csv", index=False)
    agg = aggregate(df)
    agg.to_csv(out_dir / "comparison_table.csv", index=False)

    md = agg.to_markdown(index=False)
    (out_dir / "comparison_table.md").write_text(md + "\n", encoding="utf-8")
    print(md)

    total_usd = df["estimated_usd"].sum()
    total_tokens = df["total_tokens"].sum()
    figures = make_all_plots(agg)
    print(f"\nper-trial rows: {len(df)}  ->  {out_dir}/trials.csv")
    print(f"aggregate table -> {out_dir}/comparison_table.csv|.md")
    print(f"run cost (priced trials): ${total_usd:.2f}  ({int(total_tokens):,} tokens)")
    for f in figures:
        print(f"figure -> {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
