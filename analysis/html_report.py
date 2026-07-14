"""Static HTML report for RaceBench result directories."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd


def _records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _fmt_num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def _metric_cards(df: pd.DataFrame) -> dict[str, str]:
    if df.empty:
        return {
            "Trials": "0",
            "Correct": "n/a",
            "Tokens": "0",
            "Cost": "$0.00",
            "Tasks": "0",
            "Strategies": "0",
        }
    return {
        "Trials": str(len(df)),
        "Correct": f"{df['correct'].mean() * 100:.1f}%",
        "Tokens": f"{int(df['total_tokens'].sum()):,}",
        "Cost": f"${df['estimated_usd'].sum():.2f}",
        "Tasks": str(df["task"].nunique()),
        "Strategies": str(df["strategy"].nunique()),
    }


def write_html_report(
    *,
    out_dir: Path,
    trials: pd.DataFrame,
    level_a_trials: pd.DataFrame,
    external_trials: pd.DataFrame,
    aggregate: pd.DataFrame,
    overall: pd.DataFrame,
    by_strategy: pd.DataFrame,
    by_strategy_ci: pd.DataFrame | None = None,
) -> Path:
    """Write a dependency-free HTML report next to the CSV/Markdown tables."""
    out_dir = Path(out_dir)
    cards = _metric_cards(level_a_trials)
    all_data = {
        "trials": _records(trials),
        "levelATrials": _records(level_a_trials),
        "externalTrials": _records(external_trials),
        "aggregate": _records(aggregate),
        "overall": _records(overall),
        "byStrategy": _records(by_strategy),
        "byStrategyCi": _records(
            by_strategy_ci if by_strategy_ci is not None else pd.DataFrame()),
    }
    payload = json.dumps(all_data, ensure_ascii=False)

    card_html = "\n".join(
        f'<div class="card"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
        for label, value in cards.items()
    )
    external_note = (
        f"{len(external_trials)} Level C black-box runtime trial(s) found."
        if not external_trials.empty
        else "No Level C black-box runtime trials in this report directory."
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RaceBench Results Explorer</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --ink: #172033;
      --muted: #5e6a7d;
      --line: #d8dee9;
      --panel: #ffffff;
      --accent: #2864d8;
      --good: #0f7b4f;
      --warn: #9a5b00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    header {{
      padding: 28px 32px 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 24px 24px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 28px 0 12px; font-size: 18px; letter-spacing: 0; }}
    p {{ margin: 0; color: var(--muted); }}
    .pills {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      background: #f9fafc;
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
    }}
    .pill.good {{ color: var(--good); border-color: #b7dccd; background: #eefaf5; }}
    .pill.warn {{ color: var(--warn); border-color: #ead09b; background: #fff8e8; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin: 20px 0;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .card span {{ display: block; color: var(--muted); font-size: 12px; }}
    .card strong {{ display: block; margin-top: 4px; font-size: 22px; }}
    .filters {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      margin: 18px 0;
    }}
    label {{ display: grid; gap: 5px; color: var(--muted); font-size: 12px; font-weight: 700; }}
    select, input {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 9px;
      font: inherit;
      background: #fff;
      color: var(--ink);
      min-width: 0;
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{ background: #f3f5f9; font-size: 12px; color: var(--muted); white-space: nowrap; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tr:last-child td {{ border-bottom: 0; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .note {{
      margin: 10px 0 14px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--muted);
    }}
    .empty {{ padding: 16px; color: var(--muted); }}
  </style>
</head>
<body>
  <header>
    <h1>RaceBench Results Explorer</h1>
    <p>Static report generated from replayable JSONL event logs in <code>{escape(out_dir.name)}</code>.</p>
    <div class="pills">
      <span class="pill good">Level A strategy benchmark</span>
      <span class="pill warn">Level C black-box runtime checks</span>
      <span class="pill">No external dependencies</span>
    </div>
  </header>
  <main>
    <section class="cards">{card_html}</section>
    <section class="note">
      <strong>Level A</strong> rows compare instrumented coordination strategies under the same agent loop.
      <strong>Level C</strong> rows score external runtimes as black boxes; they are not strategy columns unless
      the runtime emits RaceBench-compatible read/write/coordination events. {escape(external_note)}
    </section>

    <section class="filters" aria-label="filters">
      <label>Task <select id="taskFilter"><option value="">All tasks</option></select></label>
      <label>Strategy <select id="strategyFilter"><option value="">All strategies</option></select></label>
      <label>Failure mode <select id="modeFilter"><option value="">All modes</option></select></label>
      <label>Search <input id="searchFilter" type="search" placeholder="task, strategy, log"></label>
    </section>

    <h2>Strategy Rollup</h2>
    <div class="table-wrap" id="strategyTable"></div>

    <h2>Task x Strategy Grid</h2>
    <div class="table-wrap" id="aggregateTable"></div>

    <h2>Trial Logs</h2>
    <div class="table-wrap" id="trialTable"></div>

    <h2>Level C Black-Box Runtime Checks</h2>
    <div class="table-wrap" id="externalTable"></div>
  </main>
  <script id="racebench-data" type="application/json">{payload}</script>
  <script>
    const data = JSON.parse(document.getElementById("racebench-data").textContent);
    const filters = {{
      task: document.getElementById("taskFilter"),
      strategy: document.getElementById("strategyFilter"),
      mode: document.getElementById("modeFilter"),
      search: document.getElementById("searchFilter"),
    }};

    function uniq(values) {{
      return [...new Set(values.filter(v => v !== undefined && v !== null && String(v).length))].sort();
    }}
    function addOptions(select, values) {{
      for (const value of values) {{
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = value;
        select.appendChild(opt);
      }}
    }}
    addOptions(filters.task, uniq(data.levelATrials.map(r => r.task)));
    addOptions(filters.strategy, uniq(data.levelATrials.map(r => r.strategy)));
    addOptions(filters.mode, uniq(data.levelATrials.map(r => r.failure_mode)));

    function matches(row) {{
      const haystack = JSON.stringify(row).toLowerCase();
      return (!filters.task.value || row.task === filters.task.value)
        && (!filters.strategy.value || row.strategy === filters.strategy.value)
        && (!filters.mode.value || row.failure_mode === filters.mode.value)
        && (!filters.search.value || haystack.includes(filters.search.value.toLowerCase()));
    }}
    function fmt(value, digits = 3) {{
      if (value === null || value === undefined || Number.isNaN(value)) return "";
      if (typeof value === "number") return value.toFixed(digits).replace(/\\.0+$/, "");
      return String(value);
    }}
    function table(targetId, columns, rows) {{
      const target = document.getElementById(targetId);
      if (!rows.length) {{
        target.innerHTML = '<div class="empty">No rows for this view.</div>';
        return;
      }}
      const head = columns.map(c => `<th>${{c.label}}</th>`).join("");
      const body = rows.map(row => "<tr>" + columns.map(c => {{
        const raw = c.render ? c.render(row) : row[c.key];
        const cls = c.num ? ' class="num"' : "";
        return `<td${{cls}}>${{raw ?? ""}}</td>`;
      }}).join("") + "</tr>").join("");
      target.innerHTML = `<table><thead><tr>${{head}}</tr></thead><tbody>${{body}}</tbody></table>`;
    }}
    function filteredAggregate() {{
      return data.aggregate.filter(matches);
    }}
    function filteredTrials() {{
      return data.levelATrials.filter(matches);
    }}
    function render() {{
      const agg = filteredAggregate();
      const trials = filteredTrials();
      const strategies = filters.strategy.value
        ? data.byStrategy.filter(r => r.strategy === filters.strategy.value)
        : data.byStrategy;
      table("strategyTable", [
        {{key: "strategy", label: "strategy"}},
        {{key: "trials", label: "trials", num: true}},
        {{key: "correct_rate", label: "correct", num: true, render: r => fmt(r.correct_rate)}},
        {{key: "mean_wall_s", label: "wall s", num: true, render: r => fmt(r.mean_wall_s, 1)}},
        {{key: "mean_tokens", label: "tokens", num: true, render: r => fmt(r.mean_tokens, 0)}},
        {{key: "fp_stalls_per_trial", label: "FP stalls", num: true, render: r => fmt(r.fp_stalls_per_trial)}},
      ], strategies);
      table("aggregateTable", [
        {{key: "task", label: "task"}},
        {{key: "strategy", label: "strategy"}},
        {{key: "n_agents", label: "agents", num: true}},
        {{key: "trials", label: "trials", num: true}},
        {{key: "correct_rate", label: "correct", num: true, render: r => fmt(r.correct_rate)}},
        {{key: "mean_wall_s", label: "wall s", num: true, render: r => fmt(r.mean_wall_s, 1)}},
        {{key: "mean_tokens", label: "tokens", num: true, render: r => fmt(r.mean_tokens, 0)}},
        {{key: "fp_stalls_per_trial", label: "FP stalls", num: true, render: r => fmt(r.fp_stalls_per_trial)}},
      ], agg);
      table("trialTable", [
        {{key: "task", label: "task"}},
        {{key: "strategy", label: "strategy"}},
        {{key: "failure_mode", label: "mode"}},
        {{key: "rep", label: "rep", num: true}},
        {{key: "correct", label: "correct", render: r => r.correct ? "yes" : "no"}},
        {{key: "total_tokens", label: "tokens", num: true, render: r => fmt(r.total_tokens, 0)}},
        {{key: "wall_clock_s", label: "wall s", num: true, render: r => fmt(r.wall_clock_s, 1)}},
        {{key: "log", label: "log", render: r => `<a href="${{r.log}}">${{r.log}}</a>`}},
      ], trials);
      table("externalTable", [
        {{key: "task", label: "task"}},
        {{key: "strategy", label: "synthetic id"}},
        {{key: "adapter", label: "adapter"}},
        {{key: "correct", label: "correct", render: r => r.correct ? "yes" : "no"}},
        {{key: "wall_clock_s", label: "wall s", num: true, render: r => fmt(r.wall_clock_s, 1)}},
        {{key: "log", label: "log", render: r => `<a href="${{r.log}}">${{r.log}}</a>`}},
      ], data.externalTrials);
    }}
    for (const el of Object.values(filters)) el.addEventListener("input", render);
    render();
  </script>
</body>
</html>
"""
    path = out_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
