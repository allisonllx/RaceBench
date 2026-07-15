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
        f'<div class="metric"><span class="metric-label">{escape(label)}</span>'
        f'<strong class="metric-value">{escape(value)}</strong></div>'
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

    function heatColorForScore(score) {
      const value = Math.max(0, Math.min(1, score));
      if (value >= 0.95) return "#0f766e";
      if (value >= 0.8) return "#2a9d8f";
      if (value >= 0.6) return "#d4a017";
      if (value >= 0.4) return "#e07a2f";
      if (value >= 0.2) return "#d94b3b";
      return "#b42318";
    }
    function heatTextColor(score) {
      return score >= 0.55 && score < 0.85 ? "#1c1917" : "#fff";
    }
    function heatScore(row, metric, values) {
      const value = metricValue(row, metric);
      if (metric === "correct_rate") return toNumber(row.correct_rate);
      const min = Math.min(...values);
      const max = Math.max(...values);
      if (max === min) return 1;
      const normalized = (value - min) / (max - min);
      return metricConfig[metric].higherBetter ? normalized : 1 - normalized;
    }
    function renderHeatmap(rows) {
      const target = document.getElementById("heatmapChart");
      const meta = document.getElementById("heatmapMeta");
      const metric = filters.metric.value;
      const config = metricConfig[metric];
      const agg = summarize(rows, ["task", "strategy", "n_agents"]);
      const tasks = uniq(agg.map(row => row.task));
      const strategies = uniq(agg.map(row => row.strategy));
      if (!agg.length) {
        meta.textContent = "No cells for this view.";
        target.innerHTML = '<div class="empty">No heatmap cells for this view.</div>';
        return;
      }
      const metricValues = agg.map(row => metricValue(row, metric));
      meta.textContent = `${config.label}; ${config.higherBetter ? "higher" : "lower"} is better. Click a cell to filter.`;
      const byCell = new Map(agg.map(row => [`${row.task}|||${row.strategy}`, row]));
      const header = `<tr><th class="task-head">task</th>${strategies.map(strategy => `<th>${esc(strategy)}</th>`).join("")}</tr>`;
      const body = tasks.map((task, rowIndex) => `<tr>
        <th class="task-head">${esc(task)}</th>
        ${strategies.map((strategy, colIndex) => {
          const row = byCell.get(`${task}|||${strategy}`);
          if (!row) return '<td><button type="button" class="heat-button empty" tabindex="-1">n/a</button></td>';
          const score = heatScore(row, metric, metricValues);
          const label = metricLabel(row, metric);
          const title = `${task} / ${strategy}: ${label} ${config.label.toLowerCase()} across ${row.trials} trial(s)`;
          return `<td><button type="button" class="heat-button" data-task="${attr(task)}" data-strategy="${attr(strategy)}"
            title="${attr(title)}" style="background:${heatColorForScore(score)};color:${heatTextColor(score)};--delay:${(rowIndex + colIndex) * 18}ms">${esc(label)}</button></td>`;
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      color-scheme: light;
      --bg: #e8eaef;
      --bg-soft: #f3f4f7;
      --ink: #12151c;
      --ink-soft: #3a4252;
      --muted: #6a7385;
      --line: #d0d5de;
      --line-strong: #b6bdc9;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-ink: #0b5f59;
      --accent-soft: #d9f3ef;
      --good: #047857;
      --warn: #b45309;
      --bad: #be123c;
      --chart: #0f766e;
      --header: #10141b;
      --header-ink: #f4f5f7;
      --header-muted: #9aa3b2;
      --radius: 6px;
      --shadow: 0 1px 0 rgb(16 20 27 / 4%), 0 8px 24px rgb(16 20 27 / 5%);
      --font-sans: "Outfit", "Avenir Next", "Segoe UI", sans-serif;
      --font-mono: "IBM Plex Mono", "SFMono-Regular", ui-monospace, monospace;
      --ease: cubic-bezier(0.22, 1, 0.36, 1);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font: 14.5px/1.5 var(--font-sans);
      color: var(--ink);
      background:
        radial-gradient(circle at 1px 1px, rgb(16 20 27 / 7%) 1px, transparent 0) 0 0 / 22px 22px,
        linear-gradient(180deg, #eceef3 0%, var(--bg) 40%, #e4e7ed 100%);
      min-height: 100vh;
    }}
    code, .mono {{ font-family: var(--font-mono); font-size: 0.92em; }}
    header {{
      position: relative;
      overflow: hidden;
      padding: 36px 32px 30px;
      color: var(--header-ink);
      background:
        linear-gradient(135deg, rgb(15 118 110 / 18%) 0%, transparent 42%),
        linear-gradient(180deg, #161b24 0%, var(--header) 100%);
      border-bottom: 1px solid rgb(255 255 255 / 8%);
      animation: riseIn 700ms var(--ease) both;
    }}
    header::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        repeating-linear-gradient(
          90deg,
          transparent 0,
          transparent 47px,
          rgb(255 255 255 / 3.5%) 47px,
          rgb(255 255 255 / 3.5%) 48px
        );
      pointer-events: none;
      mask-image: linear-gradient(90deg, transparent, #000 18%, #000 82%, transparent);
    }}
    .header-inner {{
      position: relative;
      max-width: 1180px;
      margin: 0 auto;
    }}
    .brand-row {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 18px;
    }}
    .mark {{
      width: 28px;
      height: 28px;
      border-radius: 5px;
      background: linear-gradient(145deg, #14b8a6, #0f766e 55%, #115e59);
      box-shadow: inset 0 0 0 1px rgb(255 255 255 / 18%);
      position: relative;
    }}
    .mark::after {{
      content: "";
      position: absolute;
      left: 6px;
      right: 6px;
      top: 12px;
      height: 2px;
      background: rgb(255 255 255 / 85%);
      box-shadow: 0 -4px 0 rgb(255 255 255 / 55%), 0 4px 0 rgb(255 255 255 / 55%);
    }}
    .brand {{
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #5eead4;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(28px, 4vw, 40px);
      line-height: 1.08;
      letter-spacing: -0.035em;
      font-weight: 700;
    }}
    .lede {{
      margin: 0;
      max-width: 52rem;
      color: var(--header-muted);
      font-size: 15px;
    }}
    .lede code {{
      color: #d1d5db;
      background: rgb(255 255 255 / 6%);
      border: 1px solid rgb(255 255 255 / 8%);
      border-radius: 4px;
      padding: 1px 6px;
    }}
    .tags {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 18px;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid rgb(255 255 255 / 12%);
      border-radius: 4px;
      padding: 5px 10px;
      background: rgb(255 255 255 / 4%);
      color: #c5ccd8;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.02em;
    }}
    .tag::before {{
      content: "";
      width: 6px;
      height: 6px;
      border-radius: 1px;
      background: currentColor;
      opacity: 0.85;
    }}
    .tag.good {{ color: #5eead4; }}
    .tag.warn {{ color: #fbbf24; }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 24px 64px;
      animation: riseIn 800ms var(--ease) both;
      animation-delay: 80ms;
    }}
    .section-label {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin: 34px 0 12px;
    }}
    .section-label:first-of-type {{ margin-top: 8px; }}
    h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: -0.02em;
      font-weight: 600;
    }}
    .section-kicker {{
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 0;
      margin: 0 0 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .metric {{
      padding: 16px 18px;
      border-right: 1px solid var(--line);
      animation: fadeUp 620ms var(--ease) both;
    }}
    .metric:last-child {{ border-right: 0; }}
    .metric:nth-child(1) {{ animation-delay: 40ms; }}
    .metric:nth-child(2) {{ animation-delay: 90ms; }}
    .metric:nth-child(3) {{ animation-delay: 140ms; }}
    .metric:nth-child(4) {{ animation-delay: 190ms; }}
    .metric:nth-child(5) {{ animation-delay: 240ms; }}
    .metric:nth-child(6) {{ animation-delay: 290ms; }}
    .metric-label {{
      display: block;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .metric-value {{
      display: block;
      margin-top: 8px;
      font-size: 26px;
      line-height: 1;
      letter-spacing: -0.03em;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }}
    .note {{
      margin: 0 0 18px;
      padding: 14px 16px;
      border-left: 3px solid var(--accent);
      background: var(--bg-soft);
      color: var(--ink-soft);
      border-radius: 0 var(--radius) var(--radius) 0;
    }}
    .note strong {{ color: var(--ink); }}
    .filters {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      align-items: end;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 14px;
      margin: 0 0 8px;
      box-shadow: var(--shadow);
    }}
    label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    select, input {{
      border: 1px solid var(--line);
      border-radius: 5px;
      padding: 9px 10px;
      font: 500 13px/1.3 var(--font-sans);
      background: var(--bg-soft);
      color: var(--ink);
      min-width: 0;
      transition: border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
    }}
    select:hover, input:hover {{ border-color: var(--line-strong); }}
    select:focus, input:focus {{
      outline: none;
      border-color: var(--accent);
      background: #fff;
      box-shadow: 0 0 0 3px rgb(15 118 110 / 16%);
    }}
    button {{
      border: 1px solid var(--line);
      border-radius: 5px;
      padding: 9px 12px;
      font: 600 13px/1.2 var(--font-sans);
      color: var(--ink);
      background: #fff;
      cursor: pointer;
      transition: border-color 160ms ease, color 160ms ease, background 160ms ease, transform 160ms ease;
    }}
    button:hover {{
      border-color: var(--accent);
      color: var(--accent-ink);
      background: var(--accent-soft);
    }}
    button:active {{ transform: translateY(1px); }}
    .clear-btn {{
      min-height: 38px;
      background: var(--ink);
      color: #fff;
      border-color: var(--ink);
    }}
    .clear-btn:hover {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    .dashboard {{
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(250px, 0.7fr);
      gap: 14px;
      margin: 0 0 10px;
    }}
    .chart-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      min-width: 0;
      box-shadow: var(--shadow);
      animation: fadeUp 700ms var(--ease) both;
    }}
    .chart-card.wide {{ grid-column: 1 / -1; animation-delay: 120ms; }}
    .chart-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }}
    .chart-title {{
      font-weight: 600;
      letter-spacing: -0.02em;
    }}
    .chart-meta {{
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
    }}
    .bar-list {{ display: grid; gap: 10px; }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(90px, 150px) minmax(140px, 1fr) 72px;
      gap: 10px;
      align-items: center;
      width: 100%;
      border: 0;
      padding: 4px 0;
      text-align: left;
      background: transparent;
      color: var(--ink);
      font-weight: 550;
      border-radius: 4px;
    }}
    .bar-row:hover {{ color: var(--accent-ink); background: transparent; }}
    .bar-label {{
      font-family: var(--font-mono);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .bar-track {{
      height: 8px;
      border-radius: 2px;
      overflow: hidden;
      background: #e4e7ee;
    }}
    .bar-fill {{
      display: block;
      height: 100%;
      border-radius: inherit;
      background: var(--chart);
      transform-origin: left center;
      animation: growBar 700ms var(--ease) both;
      animation-delay: var(--delay, 0ms);
    }}
    @keyframes growBar {{
      from {{ transform: scaleX(0); }}
      to {{ transform: scaleX(1); }}
    }}
    .bar-value {{
      color: var(--muted);
      text-align: right;
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      font-weight: 500;
    }}
    .donut-layout {{
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 16px;
      align-items: center;
    }}
    .donut-wrap {{ position: relative; width: 150px; height: 150px; }}
    .donut {{ width: 150px; height: 150px; overflow: visible; }}
    .donut circle {{
      fill: none;
      stroke-width: 3.4;
      transform: rotate(-90deg);
      transform-origin: 18px 18px;
    }}
    .donut-bg {{ stroke: #e7d4d8; }}
    .donut-slice {{
      stroke: var(--accent);
      stroke-linecap: butt;
      animation: drawDonut 900ms var(--ease) both;
    }}
    @keyframes drawDonut {{
      from {{ stroke-dashoffset: 100; }}
      to {{ stroke-dashoffset: 0; }}
    }}
    .donut-hole {{
      position: absolute;
      inset: 34px;
      display: grid;
      place-content: center;
      text-align: center;
      border-radius: 999px;
      background: var(--panel);
      border: 1px solid var(--line);
    }}
    .donut-hole strong {{
      display: block;
      font-size: 26px;
      letter-spacing: -0.03em;
      font-variant-numeric: tabular-nums;
    }}
    .donut-hole span {{
      display: block;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .legend {{ display: grid; gap: 10px; color: var(--ink-soft); }}
    .legend-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
    }}
    .swatch {{
      width: 10px;
      height: 10px;
      border-radius: 2px;
      background: var(--accent);
    }}
    .swatch.bad {{ background: #e7d4d8; }}
    .heatmap-wrap {{ overflow-x: auto; }}
    .heatmap {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 5px;
      min-width: 760px;
    }}
    .heatmap th, .heatmap td {{ border: 0; padding: 0; text-align: center; }}
    .heatmap th {{
      background: transparent;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 500;
    }}
    .heatmap .task-head {{
      width: 190px;
      text-align: left;
      padding-right: 8px;
      font-size: 12px;
      color: var(--ink-soft);
    }}
    .heat-button {{
      width: 100%;
      min-width: 74px;
      height: 36px;
      border: 0;
      border-radius: 4px;
      color: #fff;
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
      box-shadow: inset 0 0 0 1px rgb(255 255 255 / 22%);
      animation: fadeCell 520ms var(--ease) both;
      animation-delay: var(--delay, 0ms);
    }}
    .heat-button:hover:not(.empty) {{
      filter: brightness(1.06);
      transform: translateY(-1px);
    }}
    .heat-button.empty {{
      color: var(--muted);
      background: #e8ebf1;
      cursor: default;
      box-shadow: none;
    }}
    @keyframes fadeCell {{
      from {{ opacity: 0; transform: scale(0.96); }}
      to {{ opacity: 1; transform: scale(1); }}
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes riseIn {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
    }}
    th {{
      background: var(--bg-soft);
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 500;
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    td {{ font-size: 13.5px; }}
    td.num {{
      text-align: right;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      font-size: 12.5px;
    }}
    tbody tr {{ transition: background 140ms ease; }}
    tbody tr:hover {{ background: #f7faf9; }}
    tr:last-child td {{ border-bottom: 0; }}
    a {{
      color: var(--accent-ink);
      text-decoration: none;
      border-bottom: 1px solid transparent;
      transition: border-color 140ms ease, color 140ms ease;
    }}
    a:hover {{
      color: var(--accent);
      border-bottom-color: rgb(15 118 110 / 35%);
    }}
    .empty {{
      padding: 22px 16px;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 12px;
      text-align: center;
    }}
    @media (max-width: 980px) {{
      .metrics {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .metric:nth-child(3) {{ border-right: 0; }}
      .metric:nth-child(n+4) {{ border-top: 1px solid var(--line); }}
      .filters {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    }}
    @media (max-width: 820px) {{
      header {{ padding: 28px 20px 24px; }}
      main {{ padding: 20px 16px 48px; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric:nth-child(2n) {{ border-right: 0; }}
      .metric:nth-child(n+3) {{ border-top: 1px solid var(--line); }}
      .filters {{ grid-template-columns: 1fr 1fr; }}
      .clear-btn {{ grid-column: 1 / -1; }}
      .dashboard {{ grid-template-columns: 1fr; }}
      .donut-layout {{ grid-template-columns: 1fr; justify-items: center; }}
      .bar-row {{ grid-template-columns: 92px minmax(90px, 1fr) 58px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        animation: none !important;
        transition: none !important;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="brand-row">
        <div class="mark" aria-hidden="true"></div>
        <div class="brand">RaceBench</div>
      </div>
      <h1>Results Explorer</h1>
      <p class="lede">Static report generated from replayable JSONL event logs in <code>{escape(out_dir.name)}</code>.</p>
      <div class="tags">
        <span class="tag good">Level A strategy benchmark</span>
        <span class="tag warn">Level C black-box runtime checks</span>
        <span class="tag">Static HTML explorer</span>
      </div>
    </div>
  </header>
  <main>
    <section class="metrics" aria-label="summary metrics">{card_html}</section>
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

    <div class="section-label">
      <h2>Interactive Comparison</h2>
      <span class="section-kicker">Live filters</span>
    </div>
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
          <span class="chart-meta" id="heatmapMeta">Click a cell to filter.</span>
        </div>
        <div id="heatmapChart"></div>
      </article>
    </section>

    <div class="section-label">
      <h2>Strategy Rollup</h2>
      <span class="section-kicker">Aggregates</span>
    </div>
    <div class="table-wrap" id="strategyTable"></div>

    <div class="section-label">
      <h2>Task x Strategy Grid</h2>
      <span class="section-kicker">Per-cell detail</span>
    </div>
    <div class="table-wrap" id="aggregateTable"></div>

    <div class="section-label">
      <h2>Trial Logs</h2>
      <span class="section-kicker">Level A</span>
    </div>
    <div class="table-wrap" id="trialTable"></div>

    <div class="section-label">
      <h2>Level C Black-Box Runtime Checks</h2>
      <span class="section-kicker">External</span>
    </div>
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
