"""Turn per-trial JSONL event logs into the benchmark's metric table.

Definitions (also quoted in the write-up):

- correct: every hidden-oracle test passed.
- wasted_tokens: tokens of every agent turn whose tool results included a
  refused write (edit_failed / conflict / lock_timeout). Those turns produced
  work the coordination layer discarded.
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

from harness.events import read_events

STALL_ACTIONS = {"blocked", "lock_timeout", "merge_conflict"}
REFUSED_WRITE_STATUSES = {"edit_failed", "conflict", "lock_timeout"}


def trial_metrics(log_path: Path) -> dict | None:
    events = read_events(Path(log_path))
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
    reads = 0
    stall_wait_s = 0.0

    for e in events:
        if e["event"] == "tool_call":
            current_turn[e["agent"]] = e["turn"]
        elif e["event"] == "read":
            reads += 1
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

    total_tokens = sum(turn_tokens.values())
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
    return {
        "task": start["task"],
        "failure_mode": start.get("failure_mode", ""),
        "benign": benign,
        "strategy": start["strategy"],
        "n_agents": start["n_agents"],
        "rep": start.get("rep", 0),
        "model": start.get("model", ""),
        "correct": bool(end.get("correct", False)),
        "oracle_passed": end.get("oracle_passed", 0),
        "oracle_total": end.get("oracle_total", 0),
        "wall_clock_s": float(end.get("wall_clock_s", 0.0)),
        "total_tokens": total_tokens,
        "wasted_tokens": wasted_tokens,
        "wasted_token_rate": (wasted_tokens / total_tokens) if total_tokens else 0.0,
        "stall_events": len(stalls),
        "fp_stall_events": fp_stalls,
        "stall_wait_s": round(stall_wait_s, 3),
        "reads_observed": reads,
        "read_set_visibility": 1.0,
        "agents_done": sum(1 for v in statuses.values() if v == "done"),
        "agents_errored": sum(1 for v in statuses.values() if v == "error"),
    }


def run_dataframe(run_dir: Path) -> pd.DataFrame:
    rows = []
    for log in sorted(Path(run_dir).glob("*.jsonl")):
        row = trial_metrics(log)
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
            wasted_rate=("wasted_token_rate", "mean"),
            stalls_per_trial=("stall_events", "mean"),
            fp_stalls_per_trial=("fp_stall_events", "mean"),
            mean_stall_wait_s=("stall_wait_s", "mean"),
        )
        .reset_index()
    )
    for col in ("correct_rate", "wasted_rate", "stalls_per_trial",
                "fp_stalls_per_trial"):
        agg[col] = agg[col].round(3)
    agg["mean_wall_s"] = agg["mean_wall_s"].round(1)
    agg["mean_tokens"] = agg["mean_tokens"].round(0)
    agg["mean_stall_wait_s"] = agg["mean_stall_wait_s"].round(2)
    return agg
