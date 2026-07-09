"""Generate the comparison table (CSV + markdown) and plots for a run.

Usage:
    python -m analysis.make_report results/<run_id> [more run dirs ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from analysis.metrics import aggregate, run_dataframe
from analysis.plots import make_all_plots


def main(run_dirs: list[str]) -> int:
    frames = [run_dataframe(Path(d)) for d in run_dirs]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) \
        if any(not f.empty for f in frames) else pd.DataFrame()
    if df.empty:
        print("no trial logs found", file=sys.stderr)
        return 1

    out_dir = Path(run_dirs[0])
    df.to_csv(out_dir / "trials.csv", index=False)
    agg = aggregate(df)
    agg.to_csv(out_dir / "comparison_table.csv", index=False)

    md = agg.to_markdown(index=False)
    (out_dir / "comparison_table.md").write_text(md + "\n", encoding="utf-8")
    print(md)

    figures = make_all_plots(agg)
    print(f"\nper-trial rows: {len(df)}  ->  {out_dir}/trials.csv")
    print(f"aggregate table -> {out_dir}/comparison_table.csv|.md")
    for f in figures:
        print(f"figure -> {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
