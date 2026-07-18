"""Turn per-trial JSONL event logs into the benchmark's metric table.

Definitions (also quoted in the write-up):

- correct: every hidden-oracle test passed.
- wasted_tokens: tokens of every agent turn whose tool results included a
  refused write (edit_failed / conflict / lock_timeout). Those turns produced
  work the coordination layer discarded.
- estimated_usd: list-price USD from prompt/completion counts and the price
  table (run_meta.json, --prices-config, or harness.pricing defaults). Prefer
  trial_end totals; if those are 0 (legacy trial_timeout bug), fall back to
  summing llm_usage events.
- stall_events: coordination events that delayed or refused an agent action
  (blocked, lock_timeout, merge_conflict).
- false-positive stall: a stall between two agents whose applied writes to the
  contested file changed DISJOINT symbol sets (or any stall at all on a task
  flagged benign). This is the number no existing paper reports.
- read_set_visibility: fraction of agent file reads the coordination layer
  observed. 1.0 by construction in this harness (all reads flow through the
  strategy); reported to make the comparison with HTTP-sniffing approaches
  explicit.

Level C external-runtime trials (`mode: external` on trial_start) bypass the
Strategy layer. Do not mix them into strategy comparison tables without
filtering: stalls / read-set are not comparable; use correctness and wall
clock only unless the adapter emits compatible events.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

import pandas as pd
import yaml

from harness.events import read_events
from harness.pricing import estimate_usd, load_prices
from harness.task import TASKS_DIR

STALL_ACTIONS = {"blocked", "lock_timeout", "merge_conflict"}
REFUSED_WRITE_STATUSES = {"edit_failed", "conflict", "lock_timeout"}

EVENT_PROFILE_SPECS = dict(
    trials=("correct", "size"),
    mean_agent_turns=("agent_turns", "mean"),
    mean_llm_calls=("llm_calls", "mean"),
    mean_tool_calls=("tool_calls", "mean"),
    mean_file_reads=("file_read_events", "mean"),
    mean_write_attempts=("write_events", "mean"),
    mean_write_applied=("write_applied_events", "mean"),
    mean_write_refused=("write_refused_events", "mean"),
    mean_search_events=("search_events", "mean"),
    mean_coord_events=("coord_events", "mean"),
    mean_test_runs=("run_tests_events", "mean"),
    mean_notifications_delivered=("notification_delivered_events", "mean"),
    mean_tokens_per_agent_turn=("tokens_per_agent_turn", "mean"),
)


def _critical_paths(task_name: str) -> list[str]:
    path = TASKS_DIR / task_name / "collision_map.yaml"
    if not path.is_file():
        return []
    spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(spec.get("critical_paths") or [])


def trial_metrics(log_path: Path, prices: dict | None = None) -> dict | None:
    log_path = Path(log_path)
    if prices is None:
        prices = load_prices(log_path.parent)
    events = read_events(log_path)
    start = next((e for e in events if e["event"] == "trial_start"), None)
    end = next((e for e in events if e["event"] == "trial_end"), None)
    if start is None or end is None:
        return None

    # --- token accounting per (agent, turn), to attribute waste
    turn_tokens: dict[tuple[str, int], int] = {}
    usage_prompt = usage_completion = 0
    for e in events:
        if e["event"] == "llm_usage":
            turn_tokens[(e["agent"], e["turn"])] = (
                e["prompt_tokens"] + e["completion_tokens"])
            usage_prompt += int(e.get("prompt_tokens") or 0)
            usage_completion += int(e.get("completion_tokens") or 0)

    # tool_call events carry (agent, turn); write events follow their tool_call.
    # Walk in order, remembering the current turn per agent.
    current_turn: dict[str, int] = {}
    refused_turns: set[tuple[str, int]] = set()
    writes_by_agent_path: dict[tuple[str, str], set[str]] = defaultdict(set)
    stalls: list[dict] = []
    notifications: list[dict] = []
    reads = 0
    llm_calls = 0
    tool_calls = 0
    search_events = 0
    run_tests_events = 0
    write_events = 0
    write_applied_events = 0
    write_refused_events = 0
    coord_events = 0
    notification_delivered_events = 0
    agent_done_turns: list[int] = []
    read_paths: set[str] = set()
    stall_wait_s = 0.0

    for e in events:
        event = e["event"]
        if event == "llm_usage":
            llm_calls += 1
        elif event == "tool_call":
            tool_calls += 1
            current_turn[e["agent"]] = e["turn"]
        elif event == "read":
            reads += 1
            if e.get("path"):
                read_paths.add(e["path"])
        elif event == "write":
            write_events += 1
            agent = e["agent"]
            if e["status"] in REFUSED_WRITE_STATUSES:
                write_refused_events += 1
                refused_turns.add((agent, current_turn.get(agent, -1)))
            if e["status"] in ("applied", "merged"):
                write_applied_events += 1
                writes_by_agent_path[(agent, e["path"])].update(
                    e.get("changed_symbols") or [])
            stall_wait_s += float(e.get("waited_s") or 0.0)
        elif event == "coord":
            coord_events += 1
            if e.get("action") in STALL_ACTIONS:
                stalls.append(e)
            elif e.get("action") == "notified":
                notifications.append(e)
        elif event == "search":
            search_events += 1
        elif event == "run_tests":
            run_tests_events += 1
        elif event == "notification_delivered":
            notification_delivered_events += 1
        elif event == "agent_done":
            agent_done_turns.append(int(e.get("turns") or 0))

    turn_total = sum(turn_tokens.values())
    wasted_tokens = sum(turn_tokens.get(key, 0) for key in refused_turns)

    # --- false-positive classification
    benign = bool(start.get("benign", False))
    fp_stalls = 0
    for s in stalls:
        if benign:
            fp_stalls += 1
            continue
        agent = s.get("agent") or s.get("writer") or ""
        others = s.get("holders") or ([s["holder"]] if s.get("holder") else [])
        path = s.get("path", "")
        mine = writes_by_agent_path.get((agent, path), set())
        if mine and others and all(
            writes_by_agent_path.get((other, path), set()).isdisjoint(mine) and
            writes_by_agent_path.get((other, path), set())
            for other in others
        ):
            fp_stalls += 1

    statuses = dict(end.get("agent_statuses", {}) or {})
    timed_out = any(e["event"] == "trial_timeout" for e in events)
    if not statuses and timed_out:
        for aid in start.get("agent_ids") or []:
            statuses[aid] = "timeout"

    critical = _critical_paths(start["task"])
    if critical:
        hit = sum(1 for p in critical if p in read_paths)
        critical_frac = hit / len(critical)
    else:
        critical_frac = None

    # Prefer trial_end totals; fall back to llm_usage when timeout wiped them.
    prompt_tokens = int(end.get("prompt_tokens", 0))
    completion_tokens = int(end.get("completion_tokens", 0))
    if prompt_tokens + completion_tokens == 0 and usage_prompt + usage_completion > 0:
        prompt_tokens, completion_tokens = usage_prompt, usage_completion

    model = start.get("model", "")
    mode = start.get("mode", "strategy")
    agent_turns = sum(agent_done_turns) if agent_done_turns else llm_calls
    mean_agent_turns = (
        agent_turns / len(start.get("agent_ids") or [])
        if start.get("agent_ids") else 0.0
    )
    total_tokens = prompt_tokens + completion_tokens
    return {
        "task": start["task"],
        "failure_mode": start.get("failure_mode", ""),
        "benign": benign,
        "strategy": start["strategy"],
        "mode": mode,
        "adapter": start.get("adapter", ""),
        "n_agents": start["n_agents"],
        "rep": start.get("rep", 0),
        "model": model,
        "correct": bool(end.get("correct", False)),
        "oracle_passed": end.get("oracle_passed", 0),
        "oracle_total": end.get("oracle_total", 0),
        "wall_clock_s": float(end.get("wall_clock_s", 0.0)),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_usd": round(
            estimate_usd(prices, model, prompt_tokens, completion_tokens), 6),
        "wasted_tokens": wasted_tokens,
        "wasted_token_rate": (wasted_tokens / turn_total) if turn_total else 0.0,
        "stall_events": len(stalls),
        "fp_stall_events": fp_stalls,
        "notify_events": len(notifications),
        # on a benign task every notification is unnecessary coordination
        "fp_notify_events": len(notifications) if benign else 0,
        "stall_wait_s": round(stall_wait_s, 3),
        "reads_observed": reads,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "file_read_events": reads,
        "write_events": write_events,
        "write_applied_events": write_applied_events,
        "write_refused_events": write_refused_events,
        "search_events": search_events,
        "coord_events": coord_events,
        "run_tests_events": run_tests_events,
        "notification_delivered_events": notification_delivered_events,
        "agent_turns": agent_turns,
        "mean_agent_turns": mean_agent_turns,
        "tokens_per_agent_turn": (
            total_tokens / agent_turns if agent_turns else 0.0
        ),
        "read_set_visibility": 1.0,
        "critical_paths_read_fraction": critical_frac,
        "timed_out": timed_out,
        "agents_done": sum(1 for v in statuses.values() if v == "done"),
        "agents_errored": sum(1 for v in statuses.values() if v == "error"),
        "agents_timeout": sum(1 for v in statuses.values() if v == "timeout"),
    }


def run_dataframe(run_dir: Path, prices: dict | None = None) -> pd.DataFrame:
    run_dir = Path(run_dir)
    if prices is None:
        prices = load_prices(run_dir)
    meta = _run_meta(run_dir)
    run_id = str(meta.get("run_id") or run_dir.name)
    provider = str(meta.get("provider") or _infer_provider(meta.get("model", "")))
    rows = []
    for log in sorted(run_dir.glob("*.jsonl")):
        row = trial_metrics(log, prices=prices)
        if row is not None:
            row["log"] = log.name
            row["run_id"] = run_id
            row["provider"] = provider
            row["run_dir"] = str(run_dir)
            rows.append(row)
    return pd.DataFrame(rows)


def agent_activity_dataframe(run_dir: Path) -> pd.DataFrame:
    """Return one row per agent per trial with event counts from JSONL logs."""
    run_dir = Path(run_dir)
    meta = _run_meta(run_dir)
    run_id = str(meta.get("run_id") or run_dir.name)
    provider = str(meta.get("provider") or _infer_provider(meta.get("model", "")))
    rows = []
    for log in sorted(run_dir.glob("*.jsonl")):
        rows.extend(_agent_activity_rows(log, run_id=run_id, provider=provider,
                                         run_dir=run_dir))
    return pd.DataFrame(rows)


def _agent_activity_rows(
    log_path: Path,
    *,
    run_id: str,
    provider: str,
    run_dir: Path,
) -> list[dict]:
    try:
        events = read_events(log_path)
    except (OSError, json.JSONDecodeError):
        return []

    start = next((e for e in events if e.get("event") == "trial_start"), None)
    end = next((e for e in events if e.get("event") == "trial_end"), None)
    if start is None or end is None:
        return []

    agent_ids = list(start.get("agent_ids") or [])
    if not agent_ids:
        agent_ids = sorted({
            str(e.get("agent"))
            for e in events
            if e.get("agent")
        })

    statuses = dict(end.get("agent_statuses", {}) or {})
    by_agent = {
        agent: {
            "run_id": run_id,
            "provider": provider,
            "run_dir": str(run_dir),
            "log": log_path.name,
            "task": start.get("task", ""),
            "failure_mode": start.get("failure_mode", ""),
            "benign": bool(start.get("benign", False)),
            "strategy": start.get("strategy", ""),
            "mode": start.get("mode", "strategy"),
            "adapter": start.get("adapter", ""),
            "n_agents": start.get("n_agents", len(agent_ids)),
            "rep": start.get("rep", 0),
            "model": start.get("model", ""),
            "agent": agent,
            "status": statuses.get(agent, ""),
            "turns": 0,
            "llm_calls": 0,
            "tool_calls": 0,
            "file_reads": 0,
            "write_attempts": 0,
            "write_applied": 0,
            "write_refused": 0,
            "search_events": 0,
            "run_tests": 0,
            "notifications_delivered": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for agent in agent_ids
    }

    def row_for(event: dict) -> dict | None:
        agent = event.get("agent")
        if not agent:
            return None
        return by_agent.setdefault(str(agent), {
            "run_id": run_id,
            "provider": provider,
            "run_dir": str(run_dir),
            "log": log_path.name,
            "task": start.get("task", ""),
            "failure_mode": start.get("failure_mode", ""),
            "benign": bool(start.get("benign", False)),
            "strategy": start.get("strategy", ""),
            "mode": start.get("mode", "strategy"),
            "adapter": start.get("adapter", ""),
            "n_agents": start.get("n_agents", len(agent_ids)),
            "rep": start.get("rep", 0),
            "model": start.get("model", ""),
            "agent": str(agent),
            "status": statuses.get(str(agent), ""),
            "turns": 0,
            "llm_calls": 0,
            "tool_calls": 0,
            "file_reads": 0,
            "write_attempts": 0,
            "write_applied": 0,
            "write_refused": 0,
            "search_events": 0,
            "run_tests": 0,
            "notifications_delivered": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        })

    for event in events:
        row = row_for(event)
        if row is None:
            continue
        kind = event.get("event")
        if kind == "llm_usage":
            row["llm_calls"] += 1
            prompt = int(event.get("prompt_tokens") or 0)
            completion = int(event.get("completion_tokens") or 0)
            row["prompt_tokens"] += prompt
            row["completion_tokens"] += completion
            row["total_tokens"] += prompt + completion
        elif kind == "tool_call":
            row["tool_calls"] += 1
        elif kind == "read":
            row["file_reads"] += 1
        elif kind == "write":
            row["write_attempts"] += 1
            status = event.get("status")
            if status in ("applied", "merged"):
                row["write_applied"] += 1
            elif status in REFUSED_WRITE_STATUSES:
                row["write_refused"] += 1
        elif kind == "search":
            row["search_events"] += 1
        elif kind == "run_tests":
            row["run_tests"] += 1
        elif kind == "notification_delivered":
            row["notifications_delivered"] += 1
        elif kind == "agent_done":
            row["status"] = event.get("status") or row["status"]
            row["turns"] = int(event.get("turns") or row["turns"] or 0)

    for row in by_agent.values():
        if not row["turns"]:
            row["turns"] = row["llm_calls"]
        if not row["status"]:
            row["status"] = statuses.get(row["agent"], "unknown")

    return list(by_agent.values())


def _run_meta(run_dir: Path) -> dict:
    path = Path(run_dir) / "run_meta.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _infer_provider(model: object) -> str:
    name = str(model or "").lower()
    if name.startswith("external:"):
        return "external"
    if name.startswith("agnes-"):
        return "agnes"
    if name.startswith("gpt-") or name.startswith("o"):
        return "openai"
    if name.startswith("scripted"):
        return "scripted"
    return "unknown"


def level_a_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return instrumented strategy trials, excluding Level C external runs."""
    if df.empty or "mode" not in df.columns:
        return df.copy()
    return df[df["mode"] != "external"].copy()


def _round_agg(agg: pd.DataFrame) -> pd.DataFrame:
    for col in ("correct_rate", "wasted_rate", "stalls_per_trial",
                "fp_stalls_per_trial", "notifies_per_trial"):
        if col in agg.columns:
            agg[col] = agg[col].round(3)
    if "mean_wall_s" in agg.columns:
        agg["mean_wall_s"] = agg["mean_wall_s"].round(1)
    if "mean_tokens" in agg.columns:
        agg["mean_tokens"] = agg["mean_tokens"].round(0)
    if "mean_usd" in agg.columns:
        agg["mean_usd"] = agg["mean_usd"].round(4)
    if "mean_stall_wait_s" in agg.columns:
        agg["mean_stall_wait_s"] = agg["mean_stall_wait_s"].round(2)
    return agg


def _round_event_profile(table: pd.DataFrame) -> pd.DataFrame:
    for col in table.columns:
        if col.startswith("mean_"):
            table[col] = table[col].round(2)
    return table


_AGG_SPECS = dict(
    trials=("correct", "size"),
    correct_rate=("correct", "mean"),
    mean_wall_s=("wall_clock_s", "mean"),
    mean_tokens=("total_tokens", "mean"),
    mean_usd=("estimated_usd", "mean"),
    wasted_rate=("wasted_token_rate", "mean"),
    stalls_per_trial=("stall_events", "mean"),
    fp_stalls_per_trial=("fp_stall_events", "mean"),
    notifies_per_trial=("notify_events", "mean"),
    mean_stall_wait_s=("stall_wait_s", "mean"),
)


def _groupby_metrics(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    specs = dict(_AGG_SPECS)
    if "task" not in keys and "task" in df.columns:
        specs = {"n_tasks": ("task", "nunique"), **specs}
    return df.groupby(keys, dropna=False).agg(**specs).reset_index()


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Per-task comparison table: one row per (task, strategy, n_agents)."""
    if df.empty:
        return df
    return _round_agg(_groupby_metrics(df, ["task", "strategy", "n_agents"]))


def aggregate_overall(df: pd.DataFrame) -> pd.DataFrame:
    """Across-task rollup: one row per (strategy, n_agents).

    Pools every trial for that strategy/n cell (micro-average). ``n_tasks``
    is how many distinct tasks contributed.
    """
    if df.empty:
        return df
    return _round_agg(_groupby_metrics(df, ["strategy", "n_agents"]))


def aggregate_by_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """Across-task rollup pooling all n_agents: one row per strategy."""
    if df.empty:
        return df
    return _round_agg(_groupby_metrics(df, ["strategy"]))


def event_profile_by_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """Event and turn rollup: one row per strategy."""
    if df.empty:
        return df
    specs = {"n_tasks": ("task", "nunique"), **EVENT_PROFILE_SPECS}
    return _round_event_profile(
        df.groupby(["strategy"], dropna=False).agg(**specs).reset_index()
    )


def event_profile_by_task_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """Event and turn rollup: one row per task/strategy/n_agents cell."""
    if df.empty:
        return df
    return _round_event_profile(
        df.groupby(["task", "strategy", "n_agents"], dropna=False)
        .agg(**EVENT_PROFILE_SPECS)
        .reset_index()
    )
