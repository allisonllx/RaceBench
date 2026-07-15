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
    dashboard_js = r"""
    const data = JSON.parse(document.getElementById("racebench-data").textContent);
    const filters = {
      task: document.getElementById("taskFilter"),
      strategy: document.getElementById("strategyFilter"),
      mode: document.getElementById("modeFilter"),
      metric: document.getElementById("metricSelect"),
      search: document.getElementById("searchFilter"),
    };
    const clearFilters = document.getElementById("clearFilters");
    const metricConfig = {
      correct_rate: {label: "Correctness", higherBetter: true},
      mean_wall_s: {label: "Wall time", higherBetter: false},
      mean_tokens: {label: "Tokens", higherBetter: false},
      fp_stalls_per_trial: {label: "False-positive stalls", higherBetter: false},
    };

    function uniq(values) {
      return [...new Set(values.filter(v => v !== undefined && v !== null && String(v).length))].sort();
    }
    function addOptions(select, values) {
      for (const value of values) {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = value;
        select.appendChild(opt);
      }
    }
    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }
    function attr(value) {
      return esc(value).replace(/`/g, "&#96;");
    }
    function toNumber(value) {
      const n = Number(value);
      return Number.isFinite(n) ? n : 0;
    }
    function avg(rows, key) {
      return rows.length ? rows.reduce((acc, row) => acc + toNumber(row[key]), 0) / rows.length : 0;
    }
    function fmt(value, digits = 3) {
      if (value === null || value === undefined || Number.isNaN(value)) return "";
      if (typeof value === "number") return value.toFixed(digits).replace(/\.0+$/, "");
      return String(value);
    }
    function metricValue(row, key) {
      const value = toNumber(row[key]);
      return key === "correct_rate" ? value * 100 : value;
    }
    function metricLabel(row, key) {
      const value = toNumber(row[key]);
      if (key === "correct_rate") return `${fmt(value * 100, 0)}%`;
      if (key === "mean_wall_s") return `${fmt(value, 1)}s`;
      if (key === "mean_tokens") return fmt(value, 0);
      if (key === "fp_stalls_per_trial") return fmt(value, 2);
      return fmt(value);
    }
    function logLink(row) {
      const log = String(row.log ?? "");
      return `<a href="${attr(log)}">${esc(log)}</a>`;
    }

    addOptions(filters.task, uniq(data.levelATrials.map(r => r.task)));
    addOptions(filters.strategy, uniq(data.levelATrials.map(r => r.strategy)));
    addOptions(filters.mode, uniq(data.levelATrials.map(r => r.failure_mode)));

    function matches(row) {
      const haystack = [
        row.task, row.strategy, row.failure_mode, row.log, row.model, row.mode,
        row.adapter, row.n_agents
      ].map(v => String(v ?? "")).join(" ").toLowerCase();
      return (!filters.task.value || row.task === filters.task.value)
        && (!filters.strategy.value || row.strategy === filters.strategy.value)
        && (!filters.mode.value || row.failure_mode === filters.mode.value)
        && (!filters.search.value || haystack.includes(filters.search.value.toLowerCase()));
    }
    function filteredTrials() {
      return data.levelATrials.filter(matches);
    }
    function filteredExternal() {
      return data.externalTrials.filter(matches);
    }
    function summarizeRows(rows) {
      const correct = rows.filter(row => row.correct).length;
      return {
        n_tasks: uniq(rows.map(row => row.task)).length,
        trials: rows.length,
        correct_rate: rows.length ? correct / rows.length : 0,
        mean_wall_s: avg(rows, "wall_clock_s"),
        mean_tokens: avg(rows, "total_tokens"),
        mean_usd: avg(rows, "estimated_usd"),
        wasted_rate: avg(rows, "wasted_token_rate"),
        stalls_per_trial: avg(rows, "stall_events"),
        fp_stalls_per_trial: avg(rows, "fp_stall_events"),
        notifies_per_trial: avg(rows, "notify_events"),
        mean_stall_wait_s: avg(rows, "stall_wait_s"),
      };
    }
    function summarize(rows, keys) {
      const groups = new Map();
      for (const row of rows) {
        const values = keys.map(key => row[key] ?? "");
        const id = JSON.stringify(values);
        if (!groups.has(id)) groups.set(id, {values, rows: []});
        groups.get(id).rows.push(row);
      }
      return [...groups.values()].map(group => {
        const out = {};
        keys.forEach((key, index) => { out[key] = group.values[index]; });
        return Object.assign(out, summarizeRows(group.rows));
      }).sort((a, b) => {
        const left = keys.map(key => String(a[key])).join("|");
        const right = keys.map(key => String(b[key])).join("|");
        return left.localeCompare(right);
      });
    }

    function table(targetId, columns, rows) {
      const target = document.getElementById(targetId);
      if (!rows.length) {
        target.innerHTML = '<div class="empty">No rows for this view.</div>';
        return;
      }
      const head = columns.map(c => `<th>${esc(c.label)}</th>`).join("");
      const body = rows.map(row => "<tr>" + columns.map(c => {
        const raw = c.render ? c.render(row) : esc(row[c.key]);
        const cls = c.num ? ' class="num"' : "";
        return `<td${cls}>${raw ?? ""}</td>`;
      }).join("") + "</tr>").join("");
      target.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function renderStrategyChart(rollup, rows) {
      const target = document.getElementById("strategyChart");
      const meta = document.getElementById("strategyChartMeta");
      const metric = filters.metric.value;
      const config = metricConfig[metric];
      if (!rollup.length) {
        meta.textContent = "0 trials";
        target.innerHTML = '<div class="empty">No strategy data for this view.</div>';
        return;
      }
      const sorted = [...rollup].sort((a, b) => {
        const delta = metricValue(a, metric) - metricValue(b, metric);
        return config.higherBetter ? -delta : delta;
      });
      const max = Math.max(...sorted.map(row => metricValue(row, metric)), metric === "correct_rate" ? 100 : 0.001);
      meta.textContent = `${rows.length} trials, ${config.higherBetter ? "higher" : "lower"} is better`;
      target.innerHTML = `<div class="bar-list">${sorted.map((row, index) => {
        const value = metricValue(row, metric);
        const width = Math.max(2, Math.min(100, (value / max) * 100));
        return `<button type="button" class="bar-row" data-strategy="${attr(row.strategy)}">
          <span class="bar-label">${esc(row.strategy)}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${width}%;--delay:${index * 45}ms"></span></span>
          <span class="bar-value">${esc(metricLabel(row, metric))}</span>
        </button>`;
      }).join("")}</div>`;
      target.querySelectorAll("[data-strategy]").forEach(button => {
        button.addEventListener("click", () => {
          filters.strategy.value = button.dataset.strategy;
          render();
        });
      });
    }

    function renderDonut(rows) {
      const target = document.getElementById("donutChart");
      const meta = document.getElementById("donutMeta");
      const total = rows.length;
      const passed = rows.filter(row => row.correct).length;
      const pct = total ? passed / total : 0;
      const dash = Math.max(0, Math.min(100, pct * 100));
      meta.textContent = `${total} filtered trials`;
      if (!total) {
        target.innerHTML = '<div class="empty">No trials for this view.</div>';
        return;
      }
      target.innerHTML = `<div class="donut-layout">
        <div class="donut-wrap">
          <svg class="donut" viewBox="0 0 36 36" role="img" aria-label="pass fail mix">
            <circle class="donut-bg" cx="18" cy="18" r="15.9155" pathLength="100"></circle>
            <circle class="donut-slice" cx="18" cy="18" r="15.9155" pathLength="100"
              stroke-dasharray="${dash} ${100 - dash}"></circle>
          </svg>
          <div class="donut-hole"><strong>${fmt(pct * 100, 0)}%</strong><span>pass rate</span></div>
        </div>
        <div class="legend">
          <div class="legend-row"><span class="swatch"></span><span>${passed} passed</span></div>
          <div class="legend-row"><span class="swatch bad"></span><span>${total - passed} failed</span></div>
          <div class="legend-row"><span class="swatch" style="background:var(--accent)"></span><span>${uniq(rows.map(row => row.task)).length} task(s)</span></div>
        </div>
      </div>`;
    }

    function heatColor(rate) {
      const hue = Math.round(10 + Math.max(0, Math.min(1, rate)) * 130);
      return `hsl(${hue} 66% 40%)`;
    }
    function renderHeatmap(rows) {
      const target = document.getElementById("heatmapChart");
      const agg = summarize(rows, ["task", "strategy", "n_agents"]);
      const tasks = uniq(agg.map(row => row.task));
      const strategies = uniq(agg.map(row => row.strategy));
      if (!agg.length) {
        target.innerHTML = '<div class="empty">No heatmap cells for this view.</div>';
        return;
      }
      const byCell = new Map(agg.map(row => [`${row.task}|||${row.strategy}`, row]));
      const header = `<tr><th class="task-head">task</th>${strategies.map(strategy => `<th>${esc(strategy)}</th>`).join("")}</tr>`;
      const body = tasks.map((task, rowIndex) => `<tr>
        <th class="task-head">${esc(task)}</th>
        ${strategies.map((strategy, colIndex) => {
          const row = byCell.get(`${task}|||${strategy}`);
          if (!row) return '<td><button type="button" class="heat-button empty" tabindex="-1">n/a</button></td>';
          const rate = toNumber(row.correct_rate);
          const title = `${task} / ${strategy}: ${fmt(rate * 100, 0)}% correct across ${row.trials} trial(s)`;
          return `<td><button type="button" class="heat-button" data-task="${attr(task)}" data-strategy="${attr(strategy)}"
            title="${attr(title)}" style="background:${heatColor(rate)};--delay:${(rowIndex + colIndex) * 18}ms">${fmt(rate * 100, 0)}%</button></td>`;
        }).join("")}
      </tr>`).join("");
      target.innerHTML = `<div class="heatmap-wrap"><table class="heatmap"><thead>${header}</thead><tbody>${body}</tbody></table></div>`;
      target.querySelectorAll(".heat-button:not(.empty)").forEach(button => {
        button.addEventListener("click", () => {
          filters.task.value = button.dataset.task;
          filters.strategy.value = button.dataset.strategy;
          render();
        });
      });
    }

    function render() {
      const trials = filteredTrials();
      const strategyRollup = summarize(trials, ["strategy"]);
      const taskStrategy = summarize(trials, ["task", "strategy", "n_agents"]);
      renderStrategyChart(strategyRollup, trials);
      renderDonut(trials);
      renderHeatmap(trials);
      table("strategyTable", [
        {key: "strategy", label: "strategy"},
        {key: "n_tasks", label: "tasks", num: true},
        {key: "trials", label: "trials", num: true},
        {key: "correct_rate", label: "correct", num: true, render: r => esc(fmt(r.correct_rate))},
        {key: "mean_wall_s", label: "wall s", num: true, render: r => esc(fmt(r.mean_wall_s, 1))},
        {key: "mean_tokens", label: "tokens", num: true, render: r => esc(fmt(r.mean_tokens, 0))},
        {key: "fp_stalls_per_trial", label: "FP stalls", num: true, render: r => esc(fmt(r.fp_stalls_per_trial))},
      ], strategyRollup);
      table("aggregateTable", [
        {key: "task", label: "task"},
        {key: "strategy", label: "strategy"},
        {key: "n_agents", label: "agents", num: true},
        {key: "trials", label: "trials", num: true},
        {key: "correct_rate", label: "correct", num: true, render: r => esc(fmt(r.correct_rate))},
        {key: "mean_wall_s", label: "wall s", num: true, render: r => esc(fmt(r.mean_wall_s, 1))},
        {key: "mean_tokens", label: "tokens", num: true, render: r => esc(fmt(r.mean_tokens, 0))},
        {key: "fp_stalls_per_trial", label: "FP stalls", num: true, render: r => esc(fmt(r.fp_stalls_per_trial))},
      ], taskStrategy);
      table("trialTable", [
        {key: "task", label: "task"},
        {key: "strategy", label: "strategy"},
        {key: "failure_mode", label: "mode"},
        {key: "rep", label: "rep", num: true},
        {key: "correct", label: "correct", render: r => r.correct ? "yes" : "no"},
        {key: "total_tokens", label: "tokens", num: true, render: r => esc(fmt(r.total_tokens, 0))},
        {key: "wall_clock_s", label: "wall s", num: true, render: r => esc(fmt(r.wall_clock_s, 1))},
        {key: "log", label: "log", render: logLink},
      ], trials);
      table("externalTable", [
        {key: "task", label: "task"},
        {key: "strategy", label: "synthetic id"},
        {key: "adapter", label: "adapter"},
        {key: "correct", label: "correct", render: r => r.correct ? "yes" : "no"},
        {key: "wall_clock_s", label: "wall s", num: true, render: r => esc(fmt(r.wall_clock_s, 1))},
        {key: "log", label: "log", render: logLink},
      ], filteredExternal());
    }

    for (const el of Object.values(filters)) {
      el.addEventListener("input", render);
      el.addEventListener("change", render);
    }
    clearFilters.addEventListener("click", () => {
      filters.task.value = "";
      filters.strategy.value = "";
      filters.mode.value = "";
      filters.metric.value = "correct_rate";
      filters.search.value = "";
      render();
    });
    render();
"""
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
      --bad: #b33939;
      --chart-a: #2864d8;
      --chart-b: #6b5bd6;
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
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
    button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
      font-weight: 700;
      color: var(--ink);
      background: #fff;
      cursor: pointer;
    }}
    button:hover {{ border-color: var(--accent); color: var(--accent); }}
    .clear-btn {{ align-self: end; min-height: 38px; }}
    .dashboard {{
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(260px, 0.75fr);
      gap: 14px;
      margin: 12px 0 22px;
    }}
    .chart-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }}
    .chart-card.wide {{ grid-column: 1 / -1; }}
    .chart-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .chart-title {{ font-weight: 800; }}
    .chart-meta {{ color: var(--muted); font-size: 12px; }}
    .bar-list {{ display: grid; gap: 8px; }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(90px, 150px) minmax(140px, 1fr) 72px;
      gap: 10px;
      align-items: center;
      width: 100%;
      border: 0;
      padding: 0;
      text-align: left;
      background: transparent;
      color: var(--ink);
      font-weight: 600;
    }}
    .bar-row:hover {{ color: var(--accent); }}
    .bar-track {{
      height: 14px;
      border-radius: 999px;
      overflow: hidden;
      background: #edf1f6;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--chart-a), var(--chart-b));
      transform-origin: left center;
      animation: growBar 650ms ease-out both;
      animation-delay: var(--delay, 0ms);
    }}
    @keyframes growBar {{
      from {{ transform: scaleX(0); }}
      to {{ transform: scaleX(1); }}
    }}
    .bar-value {{
      color: var(--muted);
      text-align: right;
      font-variant-numeric: tabular-nums;
      font-weight: 700;
    }}
    .donut-layout {{
      display: grid;
      grid-template-columns: 160px 1fr;
      gap: 14px;
      align-items: center;
    }}
    .donut-wrap {{ position: relative; width: 160px; height: 160px; }}
    .donut {{ width: 160px; height: 160px; overflow: visible; }}
    .donut circle {{
      fill: none;
      stroke-width: 4.2;
      transform: rotate(-90deg);
      transform-origin: 18px 18px;
    }}
    .donut-bg {{ stroke: #ead3d3; }}
    .donut-slice {{
      stroke: var(--good);
      stroke-linecap: round;
      animation: drawDonut 900ms ease-out both;
    }}
    @keyframes drawDonut {{
      from {{ stroke-dashoffset: 100; }}
      to {{ stroke-dashoffset: 0; }}
    }}
    .donut-hole {{
      position: absolute;
      inset: 38px;
      display: grid;
      place-content: center;
      text-align: center;
      border-radius: 999px;
      background: var(--panel);
      border: 1px solid var(--line);
    }}
    .donut-hole strong {{ display: block; font-size: 24px; }}
    .donut-hole span {{ display: block; color: var(--muted); font-size: 12px; }}
    .legend {{ display: grid; gap: 8px; color: var(--muted); }}
    .legend-row {{ display: flex; align-items: center; gap: 8px; }}
    .swatch {{ width: 12px; height: 12px; border-radius: 3px; background: var(--good); }}
    .swatch.bad {{ background: #ead3d3; }}
    .heatmap-wrap {{ overflow-x: auto; }}
    .heatmap {{ width: 100%; border-collapse: separate; border-spacing: 4px; min-width: 760px; }}
    .heatmap th, .heatmap td {{ border: 0; padding: 0; text-align: center; }}
    .heatmap th {{ background: transparent; color: var(--muted); font-size: 11px; }}
    .heatmap .task-head {{
      width: 190px;
      text-align: left;
      padding-right: 8px;
      font-size: 12px;
    }}
    .heat-button {{
      width: 100%;
      min-width: 74px;
      height: 34px;
      border: 0;
      border-radius: 6px;
      color: #fff;
      font-variant-numeric: tabular-nums;
      box-shadow: inset 0 0 0 1px rgb(255 255 255 / 32%);
      animation: fadeCell 520ms ease-out both;
      animation-delay: var(--delay, 0ms);
    }}
    .heat-button.empty {{
      color: var(--muted);
      background: #edf1f6;
      cursor: default;
    }}
    @keyframes fadeCell {{
      from {{ opacity: 0; transform: scale(0.96); }}
      to {{ opacity: 1; transform: scale(1); }}
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
    @media (max-width: 820px) {{
      .dashboard {{ grid-template-columns: 1fr; }}
      .donut-layout {{ grid-template-columns: 1fr; justify-items: center; }}
      .bar-row {{ grid-template-columns: 92px minmax(90px, 1fr) 58px; }}
    }}
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
      <label>Chart metric
        <select id="metricSelect">
          <option value="correct_rate">Correctness</option>
          <option value="mean_wall_s">Wall time</option>
          <option value="mean_tokens">Tokens</option>
          <option value="fp_stalls_per_trial">False-positive stalls</option>
        </select>
      </label>
      <label>Search <input id="searchFilter" type="search" placeholder="task, strategy, log"></label>
      <button class="clear-btn" id="clearFilters" type="button">Clear filters</button>
    </section>

    <h2>Interactive Comparison</h2>
    <section class="dashboard" aria-label="interactive comparison dashboard">
      <article class="chart-card">
        <div class="chart-head">
          <span class="chart-title">Strategy Comparison</span>
          <span class="chart-meta" id="strategyChartMeta"></span>
        </div>
        <div id="strategyChart"></div>
      </article>
      <article class="chart-card">
        <div class="chart-head">
          <span class="chart-title">Pass / Fail Mix</span>
          <span class="chart-meta" id="donutMeta"></span>
        </div>
        <div id="donutChart"></div>
      </article>
      <article class="chart-card wide">
        <div class="chart-head">
          <span class="chart-title">Task x Strategy Heatmap</span>
          <span class="chart-meta">Click a cell to filter.</span>
        </div>
        <div id="heatmapChart"></div>
      </article>
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
  <script>{dashboard_js}</script>
</body>
</html>
"""
    path = out_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
