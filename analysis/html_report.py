"""Static HTML report for RaceBench result directories."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd

from analysis.replay import build_replay_payload


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
    event_by_strategy: pd.DataFrame | None = None,
    event_by_task_strategy: pd.DataFrame | None = None,
    agent_activity: pd.DataFrame | None = None,
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
        "eventByStrategy": _records(
            event_by_strategy if event_by_strategy is not None else pd.DataFrame()),
        "eventByTaskStrategy": _records(
            event_by_task_strategy
            if event_by_task_strategy is not None else pd.DataFrame()),
        "agentActivity": _records(
            agent_activity if agent_activity is not None else pd.DataFrame()),
        "replays": build_replay_payload(trials, default_run_dir=out_dir),
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
    function replayButton(row) {
      const log = String(row.log ?? "");
      if (!data.replays || !data.replays[log]) return "";
      return `<button type="button" class="replay-btn" data-log="${attr(log)}">Replay</button>`;
    }

    const replayEls = {
      section: document.getElementById("trialReplaySection"),
      picker: document.getElementById("replaySelect"),
      search: document.getElementById("replaySearch"),
      count: document.getElementById("replayPickCount"),
      summary: document.getElementById("replaySummary"),
      play: document.getElementById("replayPlay"),
      scrubber: document.getElementById("replayScrubber"),
      speed: document.getElementById("replaySpeed"),
      zoom: document.getElementById("replayZoom"),
      zoomLabel: document.getElementById("replayZoomLabel"),
      clock: document.getElementById("replayClock"),
      timeline: document.getElementById("replayTimeline"),
      feed: document.getElementById("replayFeed"),
      toggles: document.getElementById("replayToggles"),
    };
    const replayTypes = [
      {event: "llm_usage", label: "LLM"},
      {event: "tool_call", label: "tool"},
      {event: "read", label: "read"},
      {event: "write", label: "write"},
      {event: "search", label: "search"},
      {event: "coord", label: "coord"},
      {event: "notification_delivered", label: "notice"},
      {event: "run_tests", label: "tests"},
      {event: "agent_done", label: "done"},
      {event: "agent_done_coord", label: "done coord"},
      {event: "trial_end", label: "outcome"},
    ];
    const replayState = {
      log: "",
      time: 0,
      timer: null,
      zoom: 1,
      pinch: null,
      enabled: new Set(replayTypes.map(t => t.event)),
    };

    function selectedReplay() {
      return data.replays ? data.replays[replayState.log] : null;
    }
    function replayDuration(replay) {
      return Math.max(0.1, toNumber(replay?.duration_s));
    }
    function stopReplay() {
      if (replayState.timer) {
        window.clearInterval(replayState.timer);
        replayState.timer = null;
      }
      replayEls.play.textContent = "Play";
    }
    function replayZoomLabel() {
      return `${Math.round(replayState.zoom * 100)}%`;
    }
    function replayTrackWidth() {
      const base = Math.max(720, replayEls.timeline.clientWidth - 190);
      return Math.round(base * replayState.zoom);
    }
    function replayPlayheadPx(duration, trackWidth) {
      const currentPct = Math.max(0, Math.min(1, replayState.time / Math.max(0.1, duration)));
      return 170 + currentPct * trackWidth;
    }
    function followReplayPlayhead(duration, trackWidth) {
      if (!replayState.timer) return;
      const viewport = replayEls.timeline.clientWidth;
      const maxScroll = Math.max(0, replayEls.timeline.scrollWidth - viewport);
      const playhead = replayPlayheadPx(duration, trackWidth);
      const visibleLeft = replayEls.timeline.scrollLeft;
      const visibleRight = visibleLeft + viewport;
      let next = visibleLeft;
      if (playhead > visibleRight - viewport * 0.22) {
        next = playhead - viewport * 0.58;
      } else if (playhead < visibleLeft + viewport * 0.18) {
        next = playhead - viewport * 0.32;
      }
      replayEls.timeline.scrollLeft = Math.max(0, Math.min(maxScroll, next));
    }
    function setReplayZoom(value) {
      const maxScroll = Math.max(1, replayEls.timeline.scrollWidth - replayEls.timeline.clientWidth);
      const scrollRatio = replayEls.timeline.scrollLeft / maxScroll;
      replayState.zoom = Math.max(1, Math.min(8, toNumber(value) || 1));
      replayEls.zoom.value = String(replayState.zoom);
      replayEls.zoomLabel.textContent = replayZoomLabel();
      renderReplay();
      window.requestAnimationFrame(() => {
        const nextMaxScroll = Math.max(0, replayEls.timeline.scrollWidth - replayEls.timeline.clientWidth);
        replayEls.timeline.scrollLeft = scrollRatio * nextMaxScroll;
      });
    }
    function replayPinchDistance(event) {
      if (!event.touches || event.touches.length < 2) return 0;
      const [first, second] = event.touches;
      return Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
    }
    function replayLabel(row) {
      const status = row.correct ? "pass" : "fail";
      return `${row.task} | ${row.strategy} | n${row.n_agents} r${row.rep} | ${status} | ${row.log}`;
    }
    function replaySearchText(row) {
      return [
        row.task, row.strategy, row.failure_mode, row.log, row.model,
        row.n_agents, row.rep, row.correct ? "pass" : "fail",
      ].map(value => String(value ?? "")).join(" ").toLowerCase();
    }
    function updateReplayPicker(rows) {
      const allPlayable = rows.filter(row => data.replays && data.replays[row.log]);
      const term = replayEls.search.value.trim().toLowerCase();
      const playable = term
        ? allPlayable.filter(row => replaySearchText(row).includes(term))
        : allPlayable;
      replayEls.count.textContent = term
        ? `${playable.length} of ${allPlayable.length} replays`
        : `${allPlayable.length} replays`;
      if (!allPlayable.length) {
        replayState.log = "";
        stopReplay();
        renderReplay();
        replayEls.picker.innerHTML = '<option value="">No replays for current filters</option>';
        replayEls.picker.disabled = true;
        return;
      }
      if (!playable.length) {
        replayEls.picker.innerHTML = '<option value="">No matching replays</option>';
        replayEls.picker.disabled = true;
        return;
      }
      if (!playable.some(row => row.log === replayState.log)) {
        selectReplay(playable[0].log, {scroll: false});
      }
      replayEls.picker.disabled = false;
      replayEls.picker.innerHTML = playable.map(row => `
        <option value="${attr(row.log)}"${row.log === replayState.log ? " selected" : ""}>
          ${esc(replayLabel(row))}
        </option>
      `).join("");
      replayEls.picker.value = replayState.log;
    }
    function eventDetail(event) {
      const bits = [];
      if (event.tool) bits.push(event.tool);
      if (event.path) bits.push(event.path);
      if (event.pattern) bits.push(`pattern=${event.pattern}`);
      if (event.status) bits.push(`status=${event.status}`);
      if (event.action) bits.push(`action=${event.action}`);
      if (event.reader) bits.push(`reader=${event.reader}`);
      if (event.writer) bits.push(`writer=${event.writer}`);
      if (event.holder) bits.push(`holder=${event.holder}`);
      if (event.holders && event.holders.length) bits.push(`holders=${event.holders.join(",")}`);
      if (event.symbols && event.symbols.length) bits.push(`symbols=${event.symbols.join(",")}`);
      if (event.total_tokens) bits.push(`${fmt(event.total_tokens, 0)} tokens`);
      if (event.passed !== undefined || event.failed !== undefined || event.errored !== undefined) {
        bits.push(`tests ${event.passed ?? 0}/${event.failed ?? 0}/${event.errored ?? 0}`);
      }
      if (event.message) bits.push(event.message);
      return bits.join(" | ");
    }
    function eventLabel(event) {
      if (event.event === "llm_usage") return `LLM t${event.turn ?? ""}`.trim();
      if (event.event === "tool_call") return event.tool || "tool";
      if (event.event === "read") return "read";
      if (event.event === "write") return event.status || "write";
      if (event.event === "coord") return event.action || "coord";
      if (event.event === "notification_delivered") return "notice";
      if (event.event === "run_tests") return "tests";
      if (event.event === "search") return event.kind || "search";
      if (event.event === "agent_done") return "done";
      if (event.event === "agent_done_coord") return "done coord";
      if (event.event === "trial_end") return event.correct ? "pass" : "fail";
      return event.event;
    }
    function eventClass(event) {
      const classes = [`replay-${String(event.event).replace(/_/g, "-")}`];
      const badWrite = event.event === "write"
        && !["applied", "merged"].includes(String(event.status || ""));
      const badCoord = event.event === "coord"
        && ["blocked", "lock_timeout", "merge_conflict"].includes(String(event.action || ""));
      const badTests = event.event === "run_tests"
        && (toNumber(event.failed) > 0 || toNumber(event.errored) > 0);
      const badEnd = event.event === "trial_end" && event.correct === false;
      if (badWrite || badCoord || badTests || badEnd) classes.push("is-important");
      if (event.event === "write" && ["applied", "merged"].includes(String(event.status || ""))) {
        classes.push("is-good");
      }
      return classes.join(" ");
    }
    function visibleReplayEvents(replay) {
      return (replay?.events || []).filter(event => replayState.enabled.has(event.event));
    }
    function eventLaneAgents(event, replay) {
      const agents = new Set(replay?.agents || []);
      const laneAgents = [];
      [event.agent, event.writer, event.reader, event.holder].forEach(agent => {
        if (agent && agents.has(agent) && !laneAgents.includes(agent)) {
          laneAgents.push(agent);
        }
      });
      (event.holders || []).forEach(agent => {
        if (agent && agents.has(agent) && !laneAgents.includes(agent)) {
          laneAgents.push(agent);
        }
      });
      return laneAgents;
    }
    function laneEventLevels(laneEvents, duration, trackWidth) {
      const lastByLevel = [-9999, -9999, -9999];
      const levels = new Map();
      laneEvents
        .slice()
        .sort((a, b) => toNumber(a.t) - toNumber(b.t))
        .forEach(event => {
          const leftPx = toNumber(event.t) / Math.max(0.1, duration) * trackWidth;
          let level = lastByLevel.findIndex(last => leftPx - last >= 78);
          if (level < 0) {
            level = lastByLevel.indexOf(Math.min(...lastByLevel));
          }
          lastByLevel[level] = leftPx;
          levels.set(event, level);
      });
      return levels;
    }
    function replayTickStep(duration, trackWidth) {
      const pxPerSecond = trackWidth / Math.max(0.1, duration);
      const targetSeconds = 72 / Math.max(0.01, pxPerSecond);
      const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
      return steps.find(step => step >= targetSeconds) || steps[steps.length - 1];
    }
    function replayTickLabel(value, step) {
      const digits = step < 0.5 ? 2 : step < 1 ? 1 : 0;
      return `${fmt(value, digits)}s`;
    }
    function replayTicks(duration, trackWidth) {
      const step = replayTickStep(duration, trackWidth);
      const maxTicks = Math.min(700, Math.floor(duration / step) + 1);
      const ticks = [];
      for (let index = 0; index < maxTicks; index++) {
        const time = Math.min(duration, index * step);
        ticks.push({
          time,
          left: Math.max(0, Math.min(100, time / Math.max(0.1, duration) * 100)),
          label: replayTickLabel(time, step),
        });
      }
      if (duration > 0 && Math.abs(duration - ticks[ticks.length - 1]?.time) > step * 0.35) {
        ticks.push({time: duration, left: 100, label: replayTickLabel(duration, step)});
      }
      return ticks;
    }
    function replayRuler(ticks) {
      return `<div class="replay-ruler">
        <div class="replay-ruler-label">time</div>
        <div class="replay-ruler-track">
          ${ticks.map(tick => `
            <span class="replay-tick" style="left:${tick.left}%"></span>
            <span class="replay-tick-label" style="left:${tick.left}%">${esc(tick.label)}</span>
          `).join("")}
        </div>
      </div>`;
    }
    function replayTickLines(ticks) {
      return ticks.map(tick =>
        `<span class="replay-grid-line" style="left:${tick.left}%"></span>`
      ).join("");
    }
    function renderReplayToggles() {
      replayEls.toggles.innerHTML = replayTypes.map(item => `
        <label class="replay-toggle">
          <input type="checkbox" value="${attr(item.event)}" checked>
          <span>${esc(item.label)}</span>
        </label>
      `).join("");
      replayEls.toggles.querySelectorAll("input").forEach(input => {
        input.addEventListener("change", () => {
          if (input.checked) replayState.enabled.add(input.value);
          else replayState.enabled.delete(input.value);
          renderReplay();
        });
      });
    }
    function selectReplay(log, {scroll = true} = {}) {
      if (!data.replays || !data.replays[log]) return;
      stopReplay();
      replayState.log = log;
      replayState.time = 0;
      renderReplay();
      if (replayEls.picker && [...replayEls.picker.options].some(option => option.value === log)) {
        replayEls.picker.value = log;
      }
      if (scroll) replayEls.section.scrollIntoView({behavior: "smooth", block: "start"});
    }
    function ensureReplaySelection(rows) {
      const playable = rows.filter(row => data.replays && data.replays[row.log]);
      if (!playable.length) {
        replayState.log = "";
        stopReplay();
        renderReplay();
        return;
      }
      if (!replayState.log || !playable.some(row => row.log === replayState.log)) {
        selectReplay(playable[0].log, {scroll: false});
      }
    }
    function setReplayTime(value) {
      const replay = selectedReplay();
      replayState.time = Math.max(0, Math.min(replayDuration(replay), toNumber(value)));
      renderReplay();
    }
    function playReplay() {
      const replay = selectedReplay();
      if (!replay) return;
      if (replayState.timer) {
        stopReplay();
        return;
      }
      if (replayState.time >= replayDuration(replay)) replayState.time = 0;
      replayEls.play.textContent = "Pause";
      replayState.timer = window.setInterval(() => {
        const step = 0.08 * toNumber(replayEls.speed.value || 20);
        replayState.time += step;
        if (replayState.time >= replayDuration(replay)) {
          replayState.time = replayDuration(replay);
          stopReplay();
        }
        renderReplay();
      }, 80);
    }
    function renderReplay() {
      const replay = selectedReplay();
      if (!replay) {
        replayEls.summary.innerHTML = '<div class="empty">Select a trial row to replay its observable events.</div>';
        replayEls.timeline.innerHTML = "";
        replayEls.feed.innerHTML = '<div class="empty">No trial selected.</div>';
        replayEls.scrubber.value = 0;
        replayEls.scrubber.max = 1;
        replayEls.clock.textContent = "0.0s / 0.0s";
        replayEls.zoomLabel.textContent = replayZoomLabel();
        replayEls.play.disabled = true;
        replayEls.scrubber.disabled = true;
        replayEls.zoom.disabled = true;
        return;
      }
      replayEls.play.disabled = false;
      replayEls.scrubber.disabled = false;
      replayEls.zoom.disabled = false;
      const duration = replayDuration(replay);
      const trackWidth = replayTrackWidth();
      const previousScrollLeft = replayEls.timeline.scrollLeft;
      const ticks = replayTicks(duration, trackWidth);
      replayEls.scrubber.max = String(duration);
      replayEls.scrubber.value = String(replayState.time);
      replayEls.zoom.value = String(replayState.zoom);
      replayEls.zoomLabel.textContent = replayZoomLabel();
      replayEls.clock.textContent = `${fmt(replayState.time, 1)}s / ${fmt(duration, 1)}s`;
      const status = replay.correct ? "passed" : "failed";
      replayEls.summary.innerHTML = `
        <div class="replay-title">
          <strong>${esc(replay.task)} / ${esc(replay.strategy)}</strong>
          <span class="${replay.correct ? "ok" : "bad"}">${esc(status)}</span>
        </div>
        <div class="replay-meta">
          <span>${esc(replay.log)}</span>
          <span>rep ${esc(replay.rep)}</span>
          <span>${esc(replay.agents.length)} agent(s)</span>
          <span>${esc(fmt(replay.wall_clock_s ?? replay.duration_s, 1))}s wall</span>
          <span>oracle ${esc(replay.oracle_passed ?? "")}/${esc(replay.oracle_total ?? "")}</span>
        </div>
        <p>Observable event replay from logged timestamps. Hidden model planning and exact generation intervals are not reconstructed.</p>
      `;
      const currentPct = Math.max(0, Math.min(100, replayState.time / duration * 100));
      const events = visibleReplayEvents(replay);
      const laneMap = new Map(replay.agents.map(agent => [agent, []]));
      laneMap.set("run", []);
      events.forEach(event => {
        const laneAgents = eventLaneAgents(event, replay);
        if (!laneAgents.length) laneAgents.push("run");
        laneAgents.forEach(agent => laneMap.get(agent)?.push(event));
      });
      if (!laneMap.get("run").length) laneMap.delete("run");
      const tickLines = replayTickLines(ticks);
      replayEls.timeline.innerHTML = `<div class="replay-lanes" style="--replay-track-width:${trackWidth}px">${replayRuler(ticks)}${[...laneMap.entries()].map(([agent, laneEvents]) => {
        const laneLabel = agent === "run" ? "run outcome" : agent;
        const levels = laneEventLevels(laneEvents, duration, trackWidth);
        return `<div class="replay-lane">
          <div class="replay-agent" title="${attr(laneLabel)}">${esc(laneLabel)}</div>
          <div class="replay-track">
            ${tickLines}
            <span class="replay-now" style="left:${currentPct}%"></span>
            ${laneEvents.map(event => {
              const left = Math.max(0, Math.min(100, toNumber(event.t) / duration * 100));
              const top = [21, 50, 79][levels.get(event) || 0];
              const seen = toNumber(event.t) <= replayState.time ? "is-seen" : "";
              const title = `${fmt(event.t, 1)}s ${event.event} ${eventDetail(event)}`;
              return `<button type="button" class="replay-marker ${eventClass(event)} ${seen}"
                title="${attr(title)}" style="left:${left}%; top:${top}%">${esc(eventLabel(event))}</button>`;
            }).join("")}
          </div>
        </div>`;
      }).join("")}</div>`;
      if (replayState.timer) {
        followReplayPlayhead(duration, trackWidth);
      } else {
        replayEls.timeline.scrollLeft = Math.min(
          previousScrollLeft,
          Math.max(0, replayEls.timeline.scrollWidth - replayEls.timeline.clientWidth),
        );
      }
      const seen = events
        .filter(event => toNumber(event.t) <= replayState.time)
        .sort((a, b) => toNumber(b.t) - toNumber(a.t))
        .slice(0, 40);
      replayEls.feed.innerHTML = seen.length ? seen.map(event => `
        <div class="replay-feed-row ${eventClass(event)}">
          <span>${esc(fmt(event.t, 1))}s</span>
          <strong>${esc(event.agent || "run")}</strong>
          <em>${esc(eventLabel(event))}</em>
          <p>${esc(eventDetail(event) || event.event)}</p>
        </div>
      `).join("") : '<div class="empty">Move the scrubber or press Play to reveal events.</div>';
    }

    addOptions(filters.task, uniq(data.levelATrials.map(r => r.task)));
    addOptions(filters.strategy, uniq(data.levelATrials.map(r => r.strategy)));
    addOptions(filters.mode, uniq(data.levelATrials.map(r => r.failure_mode)));

    function matches(row) {
      const haystack = [
        row.task, row.strategy, row.failure_mode, row.log, row.model, row.mode,
        row.adapter, row.n_agents, row.agent, row.status
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
    function filteredAgentActivity() {
      return data.agentActivity.filter(matches);
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
        mean_agent_turns: avg(rows, "agent_turns"),
        mean_llm_calls: avg(rows, "llm_calls"),
        mean_tool_calls: avg(rows, "tool_calls"),
        mean_file_reads: avg(rows, "file_read_events"),
        mean_write_attempts: avg(rows, "write_events"),
        mean_write_applied: avg(rows, "write_applied_events"),
        mean_write_refused: avg(rows, "write_refused_events"),
        mean_search_events: avg(rows, "search_events"),
        mean_coord_events: avg(rows, "coord_events"),
        mean_test_runs: avg(rows, "run_tests_events"),
        mean_notifications_delivered: avg(rows, "notification_delivered_events"),
        mean_tokens_per_agent_turn: avg(rows, "tokens_per_agent_turn"),
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

    const eventMixKeys = [
      {key: "mean_llm_calls", label: "LLM", color: "#0f766e"},
      {key: "mean_tool_calls", label: "tool", color: "#42526e"},
      {key: "mean_file_reads", label: "read", color: "#2f80ed"},
      {key: "mean_write_attempts", label: "write", color: "#d25b3d"},
      {key: "mean_search_events", label: "search", color: "#c98a00"},
      {key: "mean_coord_events", label: "coord", color: "#9f2d55"},
    ];
    function renderEventMix(rollup, rows) {
      const target = document.getElementById("eventMixChart");
      const meta = document.getElementById("eventMixMeta");
      if (!rollup.length) {
        meta.textContent = "0 trials";
        target.innerHTML = '<div class="empty">No event data for this view.</div>';
        return;
      }
      const sorted = [...rollup].sort((a, b) => String(a.strategy).localeCompare(String(b.strategy)));
      const totals = sorted.map(row => eventMixKeys.reduce(
        (acc, item) => acc + toNumber(row[item.key]), 0));
      const maxTotal = Math.max(...totals, 0.001);
      meta.textContent = `${rows.length} trials; mean event records per trial`;
      const legend = `<div class="event-legend">${eventMixKeys.map(item =>
        `<span><i style="background:${item.color}"></i>${esc(item.label)}</span>`
      ).join("")}</div>`;
      target.innerHTML = `<div class="stack-list">${sorted.map((row, index) => {
        const total = eventMixKeys.reduce((acc, item) => acc + toNumber(row[item.key]), 0);
        const barWidth = Math.max(2, Math.min(100, (total / maxTotal) * 100));
        const segments = eventMixKeys.map(item => {
          const value = toNumber(row[item.key]);
          const width = total ? Math.max(0, (value / total) * 100) : 0;
          const title = `${row.strategy}: ${fmt(value, 2)} ${item.label} event(s) per trial`;
          return `<span class="stack-segment" title="${attr(title)}" style="width:${width}%;background:${item.color}"></span>`;
        }).join("");
        return `<button type="button" class="stack-row" data-strategy="${attr(row.strategy)}">
          <span class="stack-label">${esc(row.strategy)}</span>
          <span class="stack-track"><span class="stack-fill" style="width:${barWidth}%;--delay:${index * 55}ms">${segments}</span></span>
          <span class="stack-value">${esc(fmt(total, 1))}</span>
        </button>`;
      }).join("")}</div>${legend}`;
      target.querySelectorAll("[data-strategy]").forEach(button => {
        button.addEventListener("click", () => {
          filters.strategy.value = button.dataset.strategy;
          render();
        });
      });
    }

    function renderTurnChart(rollup, rows) {
      const target = document.getElementById("turnChart");
      const meta = document.getElementById("turnChartMeta");
      if (!rollup.length) {
        meta.textContent = "0 trials";
        target.innerHTML = '<div class="empty">No turn data for this view.</div>';
        return;
      }
      const sorted = [...rollup].sort(
        (a, b) => toNumber(b.mean_agent_turns) - toNumber(a.mean_agent_turns));
      const max = Math.max(...sorted.map(row => toNumber(row.mean_agent_turns)), 0.001);
      meta.textContent = `${rows.length} trials; mean total turns across agents`;
      target.innerHTML = `<div class="bar-list compact">${sorted.map((row, index) => {
        const value = toNumber(row.mean_agent_turns);
        const width = Math.max(2, Math.min(100, (value / max) * 100));
        return `<button type="button" class="bar-row" data-strategy="${attr(row.strategy)}">
          <span class="bar-label">${esc(row.strategy)}</span>
          <span class="bar-track"><span class="bar-fill amber" style="width:${width}%;--delay:${index * 45}ms"></span></span>
          <span class="bar-value">${esc(fmt(value, 1))}</span>
        </button>`;
      }).join("")}</div>`;
      target.querySelectorAll("[data-strategy]").forEach(button => {
        button.addEventListener("click", () => {
          filters.strategy.value = button.dataset.strategy;
          render();
        });
      });
    }

    function render() {
      const trials = filteredTrials();
      const agentRows = filteredAgentActivity();
      const strategyRollup = summarize(trials, ["strategy"]);
      const taskStrategy = summarize(trials, ["task", "strategy", "n_agents"]);
      updateReplayPicker(trials);
      renderStrategyChart(strategyRollup, trials);
      renderDonut(trials);
      renderHeatmap(trials);
      renderEventMix(strategyRollup, trials);
      renderTurnChart(strategyRollup, trials);
      table("strategyTable", [
        {key: "strategy", label: "strategy"},
        {key: "n_tasks", label: "tasks", num: true},
        {key: "trials", label: "trials", num: true},
        {key: "correct_rate", label: "correct", num: true, render: r => esc(fmt(r.correct_rate))},
        {key: "mean_wall_s", label: "wall s", num: true, render: r => esc(fmt(r.mean_wall_s, 1))},
        {key: "mean_tokens", label: "tokens", num: true, render: r => esc(fmt(r.mean_tokens, 0))},
        {key: "fp_stalls_per_trial", label: "FP stalls", num: true, render: r => esc(fmt(r.fp_stalls_per_trial))},
      ], strategyRollup);
      table("eventProfileTable", [
        {key: "strategy", label: "strategy"},
        {key: "trials", label: "trials", num: true},
        {key: "mean_agent_turns", label: "turns", num: true, render: r => esc(fmt(r.mean_agent_turns, 2))},
        {key: "mean_llm_calls", label: "LLM", num: true, render: r => esc(fmt(r.mean_llm_calls, 2))},
        {key: "mean_tool_calls", label: "tools", num: true, render: r => esc(fmt(r.mean_tool_calls, 2))},
        {key: "mean_file_reads", label: "reads", num: true, render: r => esc(fmt(r.mean_file_reads, 2))},
        {key: "mean_write_attempts", label: "writes", num: true, render: r => esc(fmt(r.mean_write_attempts, 2))},
        {key: "mean_search_events", label: "search", num: true, render: r => esc(fmt(r.mean_search_events, 2))},
        {key: "mean_coord_events", label: "coord", num: true, render: r => esc(fmt(r.mean_coord_events, 2))},
        {key: "mean_tokens_per_agent_turn", label: "tokens / turn", num: true, render: r => esc(fmt(r.mean_tokens_per_agent_turn, 0))},
      ], strategyRollup);
      table("agentActivityTable", [
        {key: "task", label: "task"},
        {key: "strategy", label: "strategy"},
        {key: "rep", label: "rep", num: true},
        {key: "agent", label: "agent"},
        {key: "status", label: "status"},
        {key: "turns", label: "turns", num: true},
        {key: "llm_calls", label: "LLM", num: true},
        {key: "tool_calls", label: "tools", num: true},
        {key: "file_reads", label: "reads", num: true},
        {key: "write_attempts", label: "writes", num: true},
        {key: "search_events", label: "search", num: true},
        {key: "total_tokens", label: "tokens", num: true, render: r => esc(fmt(r.total_tokens, 0))},
        {key: "log", label: "log", render: logLink},
      ], agentRows);
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
        {key: "replay", label: "replay", render: replayButton},
      ], trials);
      document.querySelectorAll(".replay-btn[data-log]").forEach(button => {
        button.addEventListener("click", () => selectReplay(button.dataset.log));
      });
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
    replayEls.play.addEventListener("click", playReplay);
    replayEls.scrubber.addEventListener("input", () => setReplayTime(replayEls.scrubber.value));
    replayEls.speed.addEventListener("change", () => {
      if (replayState.timer) {
        stopReplay();
        playReplay();
      }
    });
    replayEls.zoom.addEventListener("input", () => setReplayZoom(replayEls.zoom.value));
    replayEls.picker.addEventListener("change", () => selectReplay(replayEls.picker.value, {scroll: false}));
    replayEls.search.addEventListener("input", () => updateReplayPicker(filteredTrials()));
    replayEls.timeline.addEventListener("wheel", event => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const delta = event.deltaY < 0 ? 0.35 : -0.35;
      setReplayZoom(replayState.zoom + delta);
    }, {passive: false});
    replayEls.timeline.addEventListener("touchstart", event => {
      const distance = replayPinchDistance(event);
      replayState.pinch = distance ? {distance, zoom: replayState.zoom} : null;
    }, {passive: true});
    replayEls.timeline.addEventListener("touchmove", event => {
      const distance = replayPinchDistance(event);
      if (!distance || !replayState.pinch) return;
      event.preventDefault();
      setReplayZoom(replayState.pinch.zoom * distance / replayState.pinch.distance);
    }, {passive: false});
    replayEls.timeline.addEventListener("touchend", () => {
      replayState.pinch = null;
    });
    replayEls.timeline.addEventListener("gesturestart", event => {
      event.preventDefault();
      replayState.pinch = {distance: 1, zoom: replayState.zoom};
    }, {passive: false});
    replayEls.timeline.addEventListener("gesturechange", event => {
      event.preventDefault();
      setReplayZoom((replayState.pinch?.zoom || replayState.zoom) * event.scale);
    }, {passive: false});
    replayEls.timeline.addEventListener("gestureend", () => {
      replayState.pinch = null;
    });
    clearFilters.addEventListener("click", () => {
      filters.task.value = "";
      filters.strategy.value = "";
      filters.mode.value = "";
      filters.metric.value = "correct_rate";
      filters.search.value = "";
      render();
    });
    renderReplayToggles();
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
    .bar-fill.amber {{ background: #c98a00; }}
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
    .stack-list {{ display: grid; gap: 10px; }}
    .stack-row {{
      display: grid;
      grid-template-columns: minmax(90px, 150px) minmax(160px, 1fr) 58px;
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
    .stack-row:hover {{ color: var(--accent-ink); background: transparent; }}
    .stack-label {{
      font-family: var(--font-mono);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .stack-track {{
      height: 12px;
      border-radius: 2px;
      overflow: hidden;
      background: #e4e7ee;
    }}
    .stack-fill {{
      display: flex;
      height: 100%;
      min-width: 2px;
      overflow: hidden;
      border-radius: inherit;
      transform-origin: left center;
      animation: growBar 760ms var(--ease) both;
      animation-delay: var(--delay, 0ms);
    }}
    .stack-segment {{
      display: block;
      height: 100%;
      min-width: 1px;
    }}
    .stack-value {{
      color: var(--muted);
      text-align: right;
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      font-weight: 500;
    }}
    .event-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      margin-top: 14px;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
    }}
    .event-legend span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .event-legend i {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 2px;
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
    .replay-card {{
      display: grid;
      gap: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      box-shadow: var(--shadow);
    }}
    .replay-picker {{
      display: grid;
      grid-template-columns: minmax(180px, 0.8fr) minmax(260px, 1.6fr) auto;
      gap: 10px;
      align-items: end;
    }}
    .replay-picker-count {{
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      text-align: right;
      white-space: nowrap;
      padding: 10px 0;
    }}
    .replay-toolbar {{
      display: grid;
      grid-template-columns: auto minmax(180px, 1fr) auto 110px minmax(150px, 210px) 54px;
      gap: 10px;
      align-items: center;
    }}
    .replay-toolbar input[type="range"] {{
      width: 100%;
      padding: 0;
      accent-color: var(--accent);
    }}
    .replay-clock {{
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      text-align: right;
      white-space: nowrap;
    }}
    .replay-zoom-label {{
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      text-align: right;
      white-space: nowrap;
    }}
    .replay-title {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 6px;
    }}
    .replay-title strong {{
      font-size: 16px;
      letter-spacing: -0.02em;
    }}
    .replay-title span {{
      border-radius: 999px;
      padding: 2px 8px;
      color: #fff;
      background: var(--bad);
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .replay-title span.ok {{ background: var(--good); }}
    .replay-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
    }}
    .replay-summary p {{
      margin: 8px 0 0;
      color: var(--ink-soft);
      font-size: 13px;
    }}
    .replay-toggles {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--bg-soft);
    }}
    .replay-toggle {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 0;
      color: var(--ink-soft);
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: 0;
      text-transform: none;
    }}
    .replay-toggle input {{ accent-color: var(--accent); }}
    .replay-timeline {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #f8fafc;
      touch-action: pan-x pan-y;
    }}
    .replay-lanes {{
      display: grid;
      gap: 0;
      width: max-content;
      min-width: 100%;
      padding: 10px;
    }}
    .replay-ruler {{
      display: grid;
      grid-template-columns: 150px var(--replay-track-width, 760px);
      gap: 10px;
      min-height: 38px;
      align-items: end;
      border-bottom: 1px solid var(--line);
    }}
    .replay-ruler-label {{
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      padding-bottom: 8px;
    }}
    .replay-ruler-track {{
      position: relative;
      width: var(--replay-track-width, 760px);
      height: 32px;
    }}
    .replay-tick {{
      position: absolute;
      bottom: 0;
      width: 1px;
      height: 16px;
      background: rgb(71 85 105 / 35%);
      transform: translateX(-0.5px);
    }}
    .replay-tick-label {{
      position: absolute;
      top: 2px;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 10px;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      transform: translateX(-50%);
    }}
    .replay-lane {{
      display: grid;
      grid-template-columns: 150px var(--replay-track-width, 760px);
      gap: 10px;
      min-height: 86px;
      align-items: center;
      border-bottom: 1px solid var(--line);
    }}
    .replay-lane:last-child {{ border-bottom: 0; }}
    .replay-agent {{
      overflow: hidden;
      color: var(--ink-soft);
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 600;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .replay-track {{
      position: relative;
      width: var(--replay-track-width, 760px);
      height: 76px;
      border-radius: 4px;
      background:
        repeating-linear-gradient(
          90deg,
          transparent 0,
          transparent calc(10% - 1px),
          rgb(18 21 28 / 8%) calc(10% - 1px),
          rgb(18 21 28 / 8%) 10%
        ),
        #eef2f7;
    }}
    .replay-now {{
      position: absolute;
      top: -4px;
      bottom: -4px;
      width: 2px;
      z-index: 5;
      background: var(--ink);
      box-shadow: 0 0 0 1px rgb(255 255 255 / 80%);
    }}
    .replay-grid-line {{
      position: absolute;
      top: 0;
      bottom: 0;
      width: 1px;
      background: rgb(71 85 105 / 12%);
      transform: translateX(-0.5px);
    }}
    .replay-marker {{
      position: absolute;
      min-width: 22px;
      max-width: 112px;
      height: 24px;
      overflow: hidden;
      padding: 2px 7px;
      border: 1px solid #cbd5e1;
      border-radius: 3px;
      color: #1f2937;
      background: #fff;
      box-shadow: 0 3px 8px rgb(15 23 42 / 10%);
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      line-height: 1;
      text-overflow: ellipsis;
      white-space: nowrap;
      transform: translate(-50%, -50%) scale(0.92);
      opacity: 0.46;
    }}
    .replay-marker.is-seen {{
      transform: translate(-50%, -50%) scale(1);
      opacity: 1;
    }}
    .replay-llm-usage {{ color: #115e59; background: #ccfbf1; border-color: #5eead4; }}
    .replay-tool-call {{ color: #334155; background: #e2e8f0; border-color: #94a3b8; }}
    .replay-read {{ color: #1d4ed8; background: #dbeafe; border-color: #93c5fd; }}
    .replay-write {{ color: #9a3412; background: #ffedd5; border-color: #fdba74; }}
    .replay-search {{ color: #854d0e; background: #fef3c7; border-color: #fcd34d; }}
    .replay-coord {{ color: #9d174d; background: #fce7f3; border-color: #f9a8d4; }}
    .replay-notification-delivered {{ color: #6d28d9; background: #ede9fe; border-color: #c4b5fd; }}
    .replay-run-tests {{ color: #155e75; background: #cffafe; border-color: #67e8f9; }}
    .replay-agent-done, .replay-agent-done-coord, .replay-trial-end {{
      color: #334155;
      background: #f1f5f9;
      border-color: #94a3b8;
    }}
    .replay-marker.is-good {{
      color: #065f46;
      background: #d1fae5;
      border-color: #34d399;
    }}
    .replay-marker.is-important {{
      color: #9f1239;
      background: #ffe4e6;
      border-color: #fb7185;
      box-shadow: 0 0 0 2px rgb(190 18 60 / 14%), 0 4px 11px rgb(190 18 60 / 16%);
    }}
    .replay-feed {{
      display: grid;
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
    }}
    .replay-feed-row {{
      display: grid;
      grid-template-columns: 62px minmax(110px, 150px) 88px minmax(180px, 1fr);
      gap: 8px;
      align-items: baseline;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
    }}
    .replay-feed-row:last-child {{ border-bottom: 0; }}
    .replay-feed-row span,
    .replay-feed-row strong,
    .replay-feed-row em {{
      overflow: hidden;
      font-family: var(--font-mono);
      font-size: 11px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .replay-feed-row span {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
    .replay-feed-row em {{ color: var(--accent-ink); font-style: normal; }}
    .replay-feed-row p {{
      min-width: 0;
      margin: 0;
      overflow: hidden;
      color: var(--ink-soft);
      font-size: 12px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .replay-feed-row.is-important {{ background: #fff1f2; }}
    .replay-btn {{
      min-height: 30px;
      padding: 6px 9px;
      color: var(--accent-ink);
      background: var(--accent-soft);
      border-color: rgb(15 118 110 / 22%);
    }}
    .replay-btn:hover {{
      color: #fff;
      background: var(--accent);
      border-color: var(--accent);
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
      .stack-row {{ grid-template-columns: 92px minmax(90px, 1fr) 50px; }}
      .replay-picker {{ grid-template-columns: 1fr; }}
      .replay-picker-count {{ text-align: left; padding: 0; }}
      .replay-toolbar {{ grid-template-columns: 1fr; }}
      .replay-clock {{ text-align: left; }}
      .replay-feed-row {{ grid-template-columns: 58px minmax(90px, 1fr); }}
      .replay-feed-row em, .replay-feed-row p {{ grid-column: 2; }}
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
      <label>Search <input id="searchFilter" type="search" placeholder="task, strategy, agent, log"></label>
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
      <h2>Event Profile</h2>
      <span class="section-kicker">Level A diagnostics</span>
    </div>
    <section class="dashboard" aria-label="event profile dashboard">
      <article class="chart-card">
        <div class="chart-head">
          <span class="chart-title">Event Mix by Strategy</span>
          <span class="chart-meta" id="eventMixMeta"></span>
        </div>
        <div id="eventMixChart"></div>
      </article>
      <article class="chart-card">
        <div class="chart-head">
          <span class="chart-title">Turns by Strategy</span>
          <span class="chart-meta" id="turnChartMeta"></span>
        </div>
        <div id="turnChart"></div>
      </article>
    </section>
    <div class="table-wrap" id="eventProfileTable"></div>

    <div class="section-label" id="trialReplaySection">
      <h2>Observable Event Replay</h2>
      <span class="section-kicker">Selected trial</span>
    </div>
    <section class="replay-card" aria-label="observable event replay">
      <div class="replay-picker">
        <label>Find replay
          <input id="replaySearch" type="search" placeholder="task, strategy, rep, log">
        </label>
        <label>Selected trial
          <select id="replaySelect" aria-label="Select replay trial">
            <option value="">Loading replays</option>
          </select>
        </label>
        <span class="replay-picker-count" id="replayPickCount">0 replays</span>
      </div>
      <div class="replay-summary" id="replaySummary"></div>
      <div class="replay-toolbar">
        <button id="replayPlay" type="button">Play</button>
        <input id="replayScrubber" type="range" min="0" max="1" step="0.1" value="0" aria-label="Replay time">
        <span class="replay-clock" id="replayClock">0.0s / 0.0s</span>
        <label>Speed
          <select id="replaySpeed">
            <option value="5">5x</option>
            <option value="20" selected>20x</option>
            <option value="60">60x</option>
            <option value="120">120x</option>
          </select>
        </label>
        <label>Zoom
          <input id="replayZoom" type="range" min="1" max="8" step="0.25" value="1" aria-label="Replay zoom">
        </label>
        <span class="replay-zoom-label" id="replayZoomLabel">100%</span>
      </div>
      <div class="replay-toggles" id="replayToggles" aria-label="replay event filters"></div>
      <div class="replay-timeline" id="replayTimeline"></div>
      <div class="replay-feed" id="replayFeed"></div>
    </section>

    <div class="section-label">
      <h2>Agent Activity</h2>
      <span class="section-kicker">Who did what</span>
    </div>
    <div class="table-wrap" id="agentActivityTable"></div>

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
