"""Static HTML dashboard for RaceBench cross-run comparisons."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd


def _records(df: pd.DataFrame | None) -> list[dict]:
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _card_html(tables: dict[str, pd.DataFrame]) -> str:
    provider = tables.get("provider_comparison", pd.DataFrame())
    solo = tables.get("solo_vs_parallel_by_strategy", pd.DataFrame())
    cards = {
        "Provider Runs": str(provider["run_id"].nunique()) if not provider.empty else "0",
        "Shared Cells": (
            str(int(provider["n_cells"].max())) if not provider.empty else "0"
        ),
        "Provider Trials": (
            f"{int(provider['trials'].sum()):,}" if not provider.empty else "0"
        ),
        "Solo Strategies": (
            str(solo["strategy"].nunique()) if not solo.empty else "0"
        ),
        "Solo Tasks": (
            str(int(solo["n_tasks"].max())) if not solo.empty else "0"
        ),
        "Dashboard": "static",
    }
    return "\n".join(
        f'<div class="metric"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
        for label, value in cards.items()
    )


def write_cross_run_dashboard(
    out_dir: Path,
    tables: dict[str, pd.DataFrame],
) -> Path:
    """Write a dependency-free cross-run dashboard next to comparison tables."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {name: _records(table) for name, table in tables.items()},
        ensure_ascii=False,
    )
    cards = _card_html(tables)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RaceBench Cross-Run Dashboard</title>
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
      --panel: #fff;
      --accent: #0f766e;
      --accent-soft: #d9f3ef;
      --good: #0f766e;
      --bad: #be123c;
      --warn: #c98a00;
      --header: #10141b;
      --header-ink: #f4f5f7;
      --radius: 6px;
      --shadow: 0 1px 0 rgb(16 20 27 / 4%), 0 8px 24px rgb(16 20 27 / 5%);
      --font-sans: "Avenir Next", "Segoe UI", system-ui, sans-serif;
      --font-mono: "SFMono-Regular", ui-monospace, monospace;
      --ease: cubic-bezier(0.22, 1, 0.36, 1);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14.5px/1.5 var(--font-sans);
      color: var(--ink);
      background:
        radial-gradient(circle at 1px 1px, rgb(16 20 27 / 7%) 1px, transparent 0) 0 0 / 22px 22px,
        linear-gradient(180deg, #eceef3 0%, var(--bg) 42%, #e4e7ed 100%);
      min-height: 100vh;
    }}
    header {{
      padding: 36px 32px 30px;
      color: var(--header-ink);
      background:
        linear-gradient(135deg, rgb(15 118 110 / 18%) 0%, transparent 42%),
        linear-gradient(180deg, #161b24 0%, var(--header) 100%);
      animation: riseIn 700ms var(--ease) both;
    }}
    .inner {{ max-width: 1180px; margin: 0 auto; }}
    .brand {{
      margin-bottom: 14px;
      color: #5eead4;
      font: 700 12px/1.2 var(--font-mono);
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(28px, 4vw, 40px);
      line-height: 1.08;
      letter-spacing: -0.03em;
    }}
    .lede {{ max-width: 58rem; margin: 0; color: #a9b2c0; }}
    .tags {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }}
    .tag {{
      border: 1px solid rgb(255 255 255 / 12%);
      border-radius: 4px;
      padding: 5px 10px;
      color: #c5ccd8;
      background: rgb(255 255 255 / 4%);
      font: 500 11px/1.2 var(--font-mono);
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 24px 64px;
      animation: riseIn 800ms var(--ease) both;
      animation-delay: 80ms;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      overflow: hidden;
      margin-bottom: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    .metric {{ padding: 16px 18px; border-right: 1px solid var(--line); }}
    .metric:last-child {{ border-right: 0; }}
    .metric span {{
      display: block;
      color: var(--muted);
      font: 600 11px/1.2 var(--font-mono);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .metric strong {{
      display: block;
      margin-top: 8px;
      font-size: 25px;
      line-height: 1;
      letter-spacing: -0.03em;
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
    .filters {{
      display: grid;
      grid-template-columns: 1.1fr 1.1fr 1fr auto;
      gap: 12px;
      align-items: end;
      padding: 14px;
      margin-bottom: 12px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font: 600 11px/1.2 var(--font-mono);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    select, input, button {{
      border: 1px solid var(--line);
      border-radius: 5px;
      padding: 9px 10px;
      font: 600 13px/1.3 var(--font-sans);
      color: var(--ink);
      background: #fff;
    }}
    select:focus, input:focus {{
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgb(15 118 110 / 16%);
    }}
    button {{
      min-height: 38px;
      color: #fff;
      background: var(--ink);
      border-color: var(--ink);
      cursor: pointer;
    }}
    button:hover {{ background: var(--accent); border-color: var(--accent); }}
    .section-label {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin: 34px 0 12px;
    }}
    h2 {{ margin: 0; font-size: 18px; letter-spacing: -0.02em; }}
    .kicker {{
      color: var(--muted);
      font: 600 11px/1.2 var(--font-mono);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .dashboard {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
      margin-bottom: 12px;
    }}
    .provider-dashboard {{
      grid-template-columns: minmax(260px, 0.72fr) minmax(0, 1.28fr);
    }}
    .chart-card {{
      min-width: 0;
      padding: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      animation: fadeUp 700ms var(--ease) both;
    }}
    .chart-card.wide {{ grid-column: 1 / -1; }}
    .provider-overview-card .bar-list {{ padding-right: 8px; }}
    .provider-overview-card .bar-row {{
      grid-template-columns: minmax(58px, 84px) minmax(80px, 1fr) minmax(58px, 72px);
    }}
    .chart-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }}
    .chart-title {{ font-weight: 700; }}
    .chart-meta {{ color: var(--muted); font: 500 11px/1.2 var(--font-mono); }}
    .delta-list, .bar-list {{ display: grid; gap: 10px; }}
    .delta-row, .bar-row {{
      display: grid;
      grid-template-columns: minmax(105px, 160px) minmax(170px, 1fr) 88px;
      gap: 10px;
      align-items: center;
    }}
    .label {{
      min-width: 0;
      overflow: hidden;
      color: var(--ink);
      font: 600 12px/1.2 var(--font-mono);
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .delta-track, .bar-track {{
      position: relative;
      height: 12px;
      overflow: hidden;
      background: #e4e7ee;
      border-radius: 2px;
    }}
    .bar-track {{ height: 8px; }}
    .zero {{
      position: absolute;
      left: 50%;
      top: 0;
      bottom: 0;
      width: 1px;
      background: rgb(18 21 28 / 40%);
      z-index: 2;
    }}
    .delta-fill, .bar-fill {{
      position: absolute;
      top: 0;
      bottom: 0;
      border-radius: inherit;
      animation: growBar 720ms var(--ease) both;
      animation-delay: var(--delay, 0ms);
      transform-origin: left center;
    }}
    .delta-fill.pos {{ background: var(--good); }}
    .delta-fill.neg {{ background: var(--bad); }}
    .bar-fill {{ left: 0; background: var(--accent); }}
    .bar-fill.warn {{ background: var(--warn); }}
    .value {{
      color: var(--muted);
      text-align: right;
      font: 500 12px/1.2 var(--font-mono);
      font-variant-numeric: tabular-nums;
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    table {{ width: 100%; min-width: 920px; border-collapse: collapse; }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{
      background: var(--bg-soft);
      color: var(--muted);
      font: 600 11px/1.2 var(--font-mono);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    td {{ font-size: 13.5px; }}
    td.num {{
      text-align: right;
      font: 500 12.5px/1.2 var(--font-mono);
      font-variant-numeric: tabular-nums;
    }}
    tbody tr:hover {{ background: #f7faf9; }}
    .empty {{
      padding: 22px 16px;
      color: var(--muted);
      font: 500 12px/1.4 var(--font-mono);
      text-align: center;
    }}
    @keyframes growBar {{
      from {{ transform: scaleX(0); }}
      to {{ transform: scaleX(1); }}
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes riseIn {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @media (max-width: 920px) {{
      .metrics {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .metric:nth-child(3) {{ border-right: 0; }}
      .metric:nth-child(n+4) {{ border-top: 1px solid var(--line); }}
      .filters, .dashboard {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="inner">
      <div class="brand">RaceBench</div>
      <h1>Cross-Run Dashboard</h1>
      <p class="lede">Provider sensitivity and solo-versus-parallel comparisons from overlapping Level A cells. Each advantage score names its direction: provider uses comparison run versus baseline run; solo calibration uses parallel run versus solo run.</p>
      <div class="tags">
        <span class="tag">Provider sensitivity</span>
        <span class="tag">Solo calibration</span>
        <span class="tag">Turn and event diagnostics</span>
      </div>
    </div>
  </header>
  <main>
    <section class="metrics" aria-label="summary metrics">{cards}</section>
    <p class="note">
      <strong>Provider advantage</strong> means comparison run versus baseline run.
      With the README command, that is <code>results/grid-v1-agnes-sensitivity</code>
      versus <code>results/grid-v1</code>. <strong>Parallel advantage</strong>
      means parallel run versus solo run. With the README command, that is
      <code>results/grid-v1</code> versus <code>results/grid-v1-calibration</code>.
      For correctness the formula is first named run minus second named run. For
      lower-is-better metrics such as wall time, tokens, turns, and tool calls,
      the sign is flipped before coloring. Green means the first named run has
      the advantage; red means the second named run has the advantage.
    </p>

    <section class="filters" aria-label="filters">
      <label>Metric
        <select id="metricSelect">
          <option value="correct_rate">Correctness</option>
          <option value="mean_wall_s">Wall time</option>
          <option value="mean_tokens">Tokens</option>
          <option value="mean_estimated_usd">Estimated USD</option>
          <option value="fp_stalls_per_trial">False-positive stalls</option>
          <option value="mean_agent_turns">Turns per trial</option>
          <option value="mean_llm_calls">LLM calls</option>
          <option value="mean_tool_calls">Tool calls</option>
          <option value="mean_file_reads">File reads</option>
          <option value="mean_write_attempts">Write attempts</option>
          <option value="mean_search_events">Search events</option>
          <option value="mean_coord_events">Coordination events</option>
          <option value="mean_tokens_per_agent_turn">Tokens per turn</option>
        </select>
      </label>
      <label>Strategy <select id="strategyFilter"><option value="">All strategies</option></select></label>
      <label>Search <input id="searchFilter" type="search" placeholder="provider, model, task"></label>
      <button id="clearFilters" type="button">Clear filters</button>
    </section>

    <div class="section-label">
      <h2>Provider Sensitivity</h2>
      <span class="kicker">OpenAI vs Agnes</span>
    </div>
    <section class="dashboard provider-dashboard" aria-label="provider dashboard">
      <article class="chart-card provider-overview-card">
        <div class="chart-head">
          <span class="chart-title">Provider Overview</span>
          <span class="chart-meta" id="providerOverviewMeta"></span>
        </div>
        <div id="providerOverviewChart"></div>
      </article>
      <article class="chart-card">
        <div class="chart-head">
          <span class="chart-title">Provider Advantage by Strategy</span>
          <span class="chart-meta" id="providerDeltaMeta"></span>
        </div>
        <div id="providerDeltaChart"></div>
      </article>
    </section>
    <div class="table-wrap" id="providerTable"></div>

    <div class="section-label">
      <h2>Solo vs Parallel</h2>
      <span class="kicker">Calibration</span>
    </div>
    <section class="dashboard" aria-label="solo dashboard">
      <article class="chart-card">
        <div class="chart-head">
          <span class="chart-title">Parallel Advantage by Strategy</span>
          <span class="chart-meta" id="soloDeltaMeta"></span>
        </div>
        <div id="soloDeltaChart"></div>
      </article>
      <article class="chart-card">
        <div class="chart-head">
          <span class="chart-title">Parallel Event Overhead</span>
          <span class="chart-meta" id="soloTurnsMeta"></span>
        </div>
        <div id="soloTurnsChart"></div>
      </article>
    </section>
    <div class="table-wrap" id="soloTable"></div>

    <div class="section-label">
      <h2>Task x Strategy Provider Advantage</h2>
      <span class="kicker">Cell detail</span>
    </div>
    <div class="table-wrap" id="providerCellTable"></div>
  </main>
  <script id="racebench-data" type="application/json">{payload}</script>
  <script>
    const data = JSON.parse(document.getElementById("racebench-data").textContent);
    const filters = {{
      metric: document.getElementById("metricSelect"),
      strategy: document.getElementById("strategyFilter"),
      search: document.getElementById("searchFilter"),
    }};
    const metricConfig = {{
      correct_rate: {{label: "Correctness", higherBetter: true, kind: "percent", digits: 1}},
      mean_wall_s: {{label: "Wall time", higherBetter: false, suffix: "s", digits: 1}},
      mean_tokens: {{label: "Tokens", higherBetter: false, digits: 0}},
      mean_estimated_usd: {{label: "Estimated USD", higherBetter: false, kind: "currency", digits: 4}},
      fp_stalls_per_trial: {{label: "False-positive stalls", higherBetter: false, digits: 2}},
      mean_agent_turns: {{label: "Turns per trial", higherBetter: false, digits: 1}},
      mean_llm_calls: {{label: "LLM calls", higherBetter: false, digits: 1}},
      mean_tool_calls: {{label: "Tool calls", higherBetter: false, digits: 1}},
      mean_file_reads: {{label: "File reads", higherBetter: false, digits: 1}},
      mean_write_attempts: {{label: "Write attempts", higherBetter: false, digits: 1}},
      mean_search_events: {{label: "Search events", higherBetter: false, digits: 1}},
      mean_coord_events: {{label: "Coordination events", higherBetter: false, digits: 1}},
      mean_tokens_per_agent_turn: {{label: "Tokens per turn", higherBetter: false, digits: 0}},
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
    function esc(value) {{
      return String(value ?? "").replace(/[&<>"']/g, ch => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }}[ch]));
    }}
    function attr(value) {{
      return esc(value).replace(/`/g, "&#96;");
    }}
    function num(value) {{
      const n = Number(value);
      return Number.isFinite(n) ? n : 0;
    }}
    function metricSpec(metric) {{
      const base = String(metric || "")
        .replace(/^(solo|parallel|baseline|compare|delta)_/, "");
      return metricConfig[base] || {{label: base || "Metric", digits: 2}};
    }}
    function fmt(value, metric = filters.metric.value, signed = false) {{
      const cfg = metricSpec(metric);
      const n = num(value);
      const sign = signed && n > 0 ? "+" : "";
      if (cfg.kind === "percent") return `${{sign}}${{(n * 100).toFixed(cfg.digits)}}%`;
      if (cfg.kind === "currency") {{
        const currencySign = signed ? (n > 0 ? "+" : (n < 0 ? "-" : "")) : "";
        return `${{currencySign}}${{new Intl.NumberFormat("en-US", {{
          style: "currency",
          currency: "USD",
          minimumFractionDigits: cfg.digits,
          maximumFractionDigits: cfg.digits
        }}).format(Math.abs(n))}}`;
      }}
      return `${{sign}}${{n.toFixed(cfg.digits)}}${{cfg.suffix || ""}}`;
    }}
    function advantageLabel(value, metric = filters.metric.value) {{
      const cfg = metricSpec(metric);
      const n = num(value);
      if (Math.abs(n) < 1e-9) return "even";
      if (cfg.higherBetter) return fmt(n, metric, true);
      const magnitude = fmt(Math.abs(n), metric);
      return n > 0 ? `saves ${{magnitude}}` : `costs ${{magnitude}}`;
    }}
    function matches(row) {{
      const haystack = [
        row.run_id, row.provider, row.model, row.strategy, row.task,
        row.baseline_run_id, row.compare_run_id, row.solo_run_id,
        row.parallel_run_id
      ].map(v => String(v ?? "")).join(" ").toLowerCase();
      return (!filters.strategy.value || !("strategy" in row) || row.strategy === filters.strategy.value)
        && (!filters.search.value || haystack.includes(filters.search.value.toLowerCase()));
    }}
    function filtered(rows) {{
      return (rows || []).filter(matches);
    }}
    function providerDirection(rows) {{
      const row = (rows || [])[0] || {{}};
      if (row.direction) return row.direction;
      if (row.compare_run_id && row.baseline_run_id) {{
        return `${{row.compare_run_id}} vs ${{row.baseline_run_id}}`;
      }}
      return "comparison run vs baseline run";
    }}
    function soloDirection(rows) {{
      const row = (rows || [])[0] || {{}};
      if (row.direction) return row.direction;
      if (row.parallel_run_id && row.solo_run_id) {{
        return `${{row.parallel_run_id}} vs ${{row.solo_run_id}}`;
      }}
      return "parallel run vs solo run";
    }}
    function table(targetId, columns, rows) {{
      const target = document.getElementById(targetId);
      if (!rows.length) {{
        target.innerHTML = '<div class="empty">No rows for this view.</div>';
        return;
      }}
      const head = columns.map(c => `<th>${{esc(c.label)}}</th>`).join("");
      const body = rows.map(row => "<tr>" + columns.map(c => {{
        const raw = c.render ? c.render(row) : esc(row[c.key]);
        return `<td${{c.num ? ' class="num"' : ""}}>${{raw ?? ""}}</td>`;
      }}).join("") + "</tr>").join("");
      target.innerHTML = `<table><thead><tr>${{head}}</tr></thead><tbody>${{body}}</tbody></table>`;
    }}
    function renderBarChart(targetId, metaId, rows, labelKey, metric, colorClass = "") {{
      const target = document.getElementById(targetId);
      const meta = document.getElementById(metaId);
      if (!rows.length) {{
        meta.textContent = "0 rows";
        target.innerHTML = '<div class="empty">No data for this view.</div>';
        return;
      }}
      const values = rows.map(row => num(row[metric]));
      const max = Math.max(...values, 0.001);
      const cfg = metricSpec(metric);
      meta.textContent = `${{cfg.label}}; ${{cfg.higherBetter ? "higher" : "lower"}} is better`;
      target.innerHTML = `<div class="bar-list">${{rows.map((row, index) => {{
        const value = num(row[metric]);
        const width = Math.max(2, Math.min(100, (value / max) * 100));
        return `<div class="bar-row">
          <span class="label" title="${{attr(row[labelKey])}}">${{esc(row[labelKey])}}</span>
          <span class="bar-track"><span class="bar-fill ${{colorClass}}" style="width:${{width}}%;--delay:${{index * 45}}ms"></span></span>
          <span class="value">${{esc(fmt(value, metric))}}</span>
        </div>`;
      }}).join("")}}</div>`;
    }}
    function renderDeltaChart(targetId, metaId, rows, labelKey, metric, direction) {{
      const target = document.getElementById(targetId);
      const meta = document.getElementById(metaId);
      const key = `delta_${{metric}}`;
      if (!rows.length) {{
        meta.textContent = "0 rows";
        target.innerHTML = '<div class="empty">No delta data for this view.</div>';
        return;
      }}
      const maxAbs = Math.max(...rows.map(row => Math.abs(num(row[key]))), 0.001);
      meta.textContent = `${{metricSpec(metric).label}} advantage: ${{direction}}; green favors the first run, red favors the second`;
      target.innerHTML = `<div class="delta-list">${{rows.map((row, index) => {{
        const value = num(row[key]);
        const width = Math.min(50, Math.abs(value) / maxAbs * 50);
        const left = value >= 0 ? 50 : 50 - width;
        const cls = value >= 0 ? "pos" : "neg";
        return `<div class="delta-row">
          <span class="label" title="${{attr(row[labelKey])}}">${{esc(row[labelKey])}}</span>
          <span class="delta-track"><span class="zero"></span><span class="delta-fill ${{cls}}" style="left:${{left}}%;width:${{width}}%;--delay:${{index * 45}}ms"></span></span>
          <span class="value">${{esc(advantageLabel(value, metric))}}</span>
        </div>`;
      }}).join("")}}</div>`;
    }}
    const strategyValues = uniq([
      ...(data.provider_by_strategy || []).map(row => row.strategy),
      ...(data.solo_vs_parallel_by_strategy || []).map(row => row.strategy),
    ]);
    addOptions(filters.strategy, strategyValues);
    function render() {{
      const metric = filters.metric.value;
      const providerOverview = filtered(data.provider_comparison || []);
      const providerDelta = filtered(data.provider_delta_by_strategy || []);
      const soloDelta = filtered(data.solo_vs_parallel_by_strategy || []);
      const providerCells = filtered(data.provider_delta_by_task_strategy || []);
      renderBarChart("providerOverviewChart", "providerOverviewMeta",
        providerOverview, "provider", metric);
      renderDeltaChart("providerDeltaChart", "providerDeltaMeta",
        providerDelta, "strategy", metric, providerDirection(providerDelta));
      renderDeltaChart("soloDeltaChart", "soloDeltaMeta",
        soloDelta, "strategy", metric, soloDirection(soloDelta));
      renderBarChart("soloTurnsChart", "soloTurnsMeta",
        soloDelta, "strategy", "parallel_mean_agent_turns", "warn");
      table("providerTable", [
        {{key: "run_id", label: "run"}},
        {{key: "provider", label: "provider"}},
        {{key: "model", label: "model"}},
        {{key: "n_cells", label: "cells", num: true}},
        {{key: "trials", label: "trials", num: true}},
        {{key: "correct_rate", label: "correct", num: true, render: r => esc(fmt(r.correct_rate, "correct_rate"))}},
        {{key: "mean_wall_s", label: "wall", num: true, render: r => esc(fmt(r.mean_wall_s, "mean_wall_s"))}},
        {{key: "mean_tokens", label: "tokens", num: true, render: r => esc(fmt(r.mean_tokens, "mean_tokens"))}},
        {{key: "mean_estimated_usd", label: "est. USD", num: true, render: r => esc(fmt(r.mean_estimated_usd, "mean_estimated_usd"))}},
        {{key: "mean_agent_turns", label: "turns", num: true, render: r => esc(fmt(r.mean_agent_turns, "mean_agent_turns"))}},
        {{key: "mean_tool_calls", label: "tools", num: true, render: r => esc(fmt(r.mean_tool_calls, "mean_tool_calls"))}},
        {{key: "mean_coord_events", label: "coord", num: true, render: r => esc(fmt(r.mean_coord_events, "mean_coord_events"))}},
      ], providerOverview);
      table("soloTable", [
        {{key: "strategy", label: "strategy"}},
        {{key: "direction", label: "direction"}},
        {{key: "n_tasks", label: "tasks", num: true}},
        {{key: "solo_correct_rate", label: "solo correct", num: true, render: r => esc(fmt(r.solo_correct_rate, "correct_rate"))}},
        {{key: "parallel_correct_rate", label: "parallel correct", num: true, render: r => esc(fmt(r.parallel_correct_rate, "correct_rate"))}},
        {{key: "delta_correct_rate", label: "parallel advantage", num: true, render: r => esc(advantageLabel(r.delta_correct_rate, "correct_rate"))}},
        {{key: "parallel_mean_wall_s", label: "parallel wall", num: true, render: r => esc(fmt(r.parallel_mean_wall_s, "mean_wall_s"))}},
        {{key: "parallel_mean_tokens", label: "parallel tokens", num: true, render: r => esc(fmt(r.parallel_mean_tokens, "mean_tokens"))}},
        {{key: "parallel_mean_estimated_usd", label: "parallel est. USD", num: true, render: r => esc(fmt(r.parallel_mean_estimated_usd, "mean_estimated_usd"))}},
        {{key: "parallel_mean_agent_turns", label: "parallel turns", num: true, render: r => esc(fmt(r.parallel_mean_agent_turns, "mean_agent_turns"))}},
        {{key: "parallel_mean_tool_calls", label: "parallel tools", num: true, render: r => esc(fmt(r.parallel_mean_tool_calls, "mean_tool_calls"))}},
      ], soloDelta);
      table("providerCellTable", [
        {{key: "task", label: "task"}},
        {{key: "strategy", label: "strategy"}},
        {{key: "direction", label: "direction"}},
        {{key: "n_agents", label: "agents", num: true}},
        {{key: "compare_run_id", label: "comparison run"}},
        {{key: "baseline_run_id", label: "baseline run"}},
        {{key: "compare_correct_rate", label: "comparison correct", num: true, render: r => esc(fmt(r.compare_correct_rate, "correct_rate"))}},
        {{key: "baseline_correct_rate", label: "baseline correct", num: true, render: r => esc(fmt(r.baseline_correct_rate, "correct_rate"))}},
        {{key: "delta_correct_rate", label: "provider advantage", num: true, render: r => esc(advantageLabel(r.delta_correct_rate, "correct_rate"))}},
        {{key: "delta_mean_wall_s", label: "wall advantage", num: true, render: r => esc(advantageLabel(r.delta_mean_wall_s, "mean_wall_s"))}},
        {{key: "delta_mean_tokens", label: "token advantage", num: true, render: r => esc(advantageLabel(r.delta_mean_tokens, "mean_tokens"))}},
        {{key: "delta_mean_estimated_usd", label: "cost advantage", num: true, render: r => esc(advantageLabel(r.delta_mean_estimated_usd, "mean_estimated_usd"))}},
        {{key: "delta_mean_agent_turns", label: "turn advantage", num: true, render: r => esc(advantageLabel(r.delta_mean_agent_turns, "mean_agent_turns"))}},
        {{key: "delta_mean_tool_calls", label: "tool-call advantage", num: true, render: r => esc(advantageLabel(r.delta_mean_tool_calls, "mean_tool_calls"))}},
      ], providerCells);
    }}
    for (const el of Object.values(filters)) {{
      el.addEventListener("input", render);
      el.addEventListener("change", render);
    }}
    document.getElementById("clearFilters").addEventListener("click", () => {{
      filters.metric.value = "correct_rate";
      filters.strategy.value = "";
      filters.search.value = "";
      render();
    }});
    render();
  </script>
</body>
</html>
"""
    path = out_dir / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    return path
