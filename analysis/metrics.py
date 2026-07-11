"""Turn per-trial JSONL event logs into the benchmark's metric table.

Definitions (also quoted in the write-up):

- correct: every hidden-oracle test passed.
- wasted_tokens: tokens of every agent turn whose tool results included a
  refused write (edit_failed / conflict / lock_timeout). Those turns produced
  work the coordination layer discarded.
- estimated_usd: list-price USD from trial_end prompt/completion counts and
  the price table (run_meta.json, --prices-config, or harness.pricing defaults).
- stall_events: coordination events that delayed or refused an agent action
  (blocked, lock_timeout, merge_conflict).
- false-positive stall: a stall between two agents whose applied writes to the
  contested file changed DISJOINT symbol sets (or any stall at all on a task
  flagged benign). This is the number no existing paper reports.
- read_set_visibility: fraction of agent file reads the coordination layer
  observed. 1.0 by construction in this harness (all reads flow through the
  strategy); reported to make the comparison with HTTP-sniffing approaches
  explicit.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd
import yaml

from harness.events import read_events
from harness.pricing import estimate_usd, load_prices
from harness.task import TASKS_DIR

STALL_ACTIONS = {"blocked", "lock_timeout", "merge_conflict"}
REFUSED_WRITE_STATUSES = {"edit_failed", "conflict", "lock_timeout"}


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
    for e in events:
        if e["event"] == "llm_usage":
            turn_tokens[(e["agent"], e["turn"])] = (
                e["prompt_tokens"] + e["completion_tokens"])

    # tool_call events carry (agent, turn); write events follow their tool_call.
    # Walk in order, remembering the current turn per agent.
    current_turn: dict[str, int] = {}
    refused_turns: set[tuple[str, int]] = set()
    writes_by_agent_path: dict[tuple[str, str], set[str]] = defaultdict(set)
    stalls: list[dict] = []
    notifications: list[dict] = []
    reads = 0
    read_paths: set[str] = set()
    stall_wait_s = 0.0

    for e in events:
        if e["event"] == "tool_call":
            current_turn[e["agent"]] = e["turn"]
        elif e["event"] == "read":
            reads += 1
            if e.get("path"):
                read_paths.add(e["path"])
        elif e["event"] == "write":
            agent = e["agent"]
            if e["status"] in REFUSED_WRITE_STATUSES:
                refused_turns.add((agent, current_turn.get(agent, -1)))
            if e["status"] in ("applied", "merged"):
                writes_by_agent_path[(agent, e["path"])].update(
                    e.get("changed_symbols") or [])
            stall_wait_s += float(e.get("waited_s") or 0.0)
        elif e["event"] == "coord" and e.get("action") in STALL_ACTIONS:
            stalls.append(e)
        elif e["event"] == "coord" and e.get("action") == "notified":
            notifications.append(e)

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

    statuses = end.get("agent_statuses", {}) or {}
    critical = _critical_paths(start["task"])
    if critical:
        hit = sum(1 for p in critical if p in read_paths)
        critical_frac = hit / len(critical)
    else:
        critical_frac = None
    prompt_tokens = int(end.get("prompt_tokens", 0))
    completion_tokens = int(end.get("completion_tokens", 0))
    model = start.get("model", "")
    return {
        "task": start["task"],
        "failure_mode": start.get("failure_mode", ""),
        "benign": benign,
        "strategy": start["strategy"],
        "n_agents": start["n_agents"],
        "rep": start.get("rep", 0),
        "model": model,
        "correct": bool(end.get("correct", False)),
        "oracle_passed": end.get("oracle_passed", 0),
        "oracle_total": end.get("oracle_total", 0),
        "wall_clock_s": float(end.get("wall_clock_s", 0.0)),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
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
        "read_set_visibility": 1.0,
        "critical_paths_read_fraction": critical_frac,
        "agents_done": sum(1 for v in statuses.values() if v == "done"),
        "agents_errored": sum(1 for v in statuses.values() if v == "error"),
    }


def run_dataframe(run_dir: Path, prices: dict | None = None) -> pd.DataFrame:
    run_dir = Path(run_dir)
    if prices is None:
        prices = load_prices(run_dir)
    rows = []
    for log in sorted(run_dir.glob("*.jsonl")):
        row = trial_metrics(log, prices=prices)
        if row is not None:
            row["log"] = log.name
            rows.append(row)
    return pd.DataFrame(rows)


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """The comparison table: one row per (task, strategy, n_agents)."""
    if df.empty:
        return df
    agg = (
        df.groupby(["task", "strategy", "n_agents"])
        .agg(
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
        .reset_index()
    )
    for col in ("correct_rate", "wasted_rate", "stalls_per_trial",
                "fp_stalls_per_trial", "notifies_per_trial"):
        agg[col] = agg[col].round(3)
    agg["mean_wall_s"] = agg["mean_wall_s"].round(1)
    agg["mean_tokens"] = agg["mean_tokens"].round(0)
    agg["mean_usd"] = agg["mean_usd"].round(4)
    agg["mean_stall_wait_s"] = agg["mean_stall_wait_s"].round(2)
    return agg
