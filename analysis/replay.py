"""Compact event replay payloads for static RaceBench reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from harness.events import read_events

REPLAY_EVENTS = {
    "llm_usage",
    "tool_call",
    "read",
    "write",
    "search",
    "coord",
    "notification_delivered",
    "run_tests",
    "agent_done",
    "agent_done_coord",
    "trial_end",
}

DIRECT_FIELDS = (
    "agent",
    "turn",
    "tool",
    "path",
    "kind",
    "status",
    "action",
    "reader",
    "writer",
    "holder",
    "strategy",
    "found",
    "size",
    "waited_s",
    "passed",
    "failed",
    "errored",
    "prompt_tokens",
    "completion_tokens",
    "oracle_passed",
    "oracle_total",
    "correct",
    "n",
    "pattern",
)

MAX_MESSAGE_CHARS = 160


def build_replay_payload(
    trials: pd.DataFrame,
    *,
    default_run_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Return compact replay data keyed by each trial log filename."""
    if trials is None or trials.empty:
        return {}

    payload: dict[str, dict[str, Any]] = {}
    for row in trials.to_dict(orient="records"):
        log = str(row.get("log") or "")
        if not log:
            continue
        run_dir = Path(str(row.get("run_dir") or default_run_dir))
        replay = trial_replay(run_dir / log, log_name=log)
        if replay is not None:
            payload[log] = replay
    return payload


def trial_replay(log_path: Path, *, log_name: str | None = None) -> dict[str, Any] | None:
    """Build one compact observable-event replay from a JSONL trial log."""
    try:
        events = read_events(Path(log_path))
    except (OSError, ValueError):
        return None
    if not events:
        return None

    start = next((e for e in events if e.get("event") == "trial_start"), None)
    end = next((e for e in reversed(events) if e.get("event") == "trial_end"), None)
    if start is None:
        return None

    start_ts = _num(start.get("ts"))
    agents = _ordered_unique([
        *(str(a) for a in start.get("agent_ids") or []),
        *(str(e.get("agent")) for e in events if e.get("agent")),
    ])
    compact_events = [
        compact_event(event, start_ts=start_ts)
        for event in events
        if event.get("event") in REPLAY_EVENTS
    ]
    compact_events = [event for event in compact_events if event is not None]

    duration = max([_num(e.get("t")) for e in compact_events] + [0.0])
    if end is not None:
        duration = max(duration, _num(end.get("wall_clock_s")))

    return {
        "log": log_name or Path(log_path).name,
        "task": start.get("task", ""),
        "strategy": start.get("strategy", ""),
        "failure_mode": start.get("failure_mode", ""),
        "rep": start.get("rep", 0),
        "model": start.get("model", ""),
        "mode": start.get("mode", "strategy"),
        "adapter": start.get("adapter", ""),
        "agents": agents,
        "duration_s": round(duration, 3),
        "correct": bool(end.get("correct", False)) if end else None,
        "oracle_passed": end.get("oracle_passed") if end else None,
        "oracle_total": end.get("oracle_total") if end else None,
        "wall_clock_s": end.get("wall_clock_s") if end else None,
        "events": compact_events,
    }


def compact_event(event: dict[str, Any], *, start_ts: float) -> dict[str, Any] | None:
    """Drop bulky fields while preserving enough data for a replay marker."""
    kind = str(event.get("event") or "")
    if not kind:
        return None

    out: dict[str, Any] = {
        "t": round(max(0.0, _num(event.get("ts")) - start_ts), 3),
        "event": kind,
    }
    for field in DIRECT_FIELDS:
        if field in event and event[field] is not None:
            out[field] = event[field]

    args = event.get("args") if isinstance(event.get("args"), dict) else {}
    if args:
        if "path" not in out and args.get("path"):
            out["path"] = args["path"]
        if "pattern" not in out and args.get("pattern"):
            out["pattern"] = args["pattern"]
        if "message" not in out and args.get("summary"):
            out["message"] = _short_text(args["summary"])

    if event.get("changed_symbols") is not None:
        out["symbols"] = list(event.get("changed_symbols") or [])
    elif event.get("symbols") is not None:
        out["symbols"] = list(event.get("symbols") or [])

    if event.get("holders") is not None:
        out["holders"] = list(event.get("holders") or [])

    message = event.get("message") or event.get("note")
    if message:
        out["message"] = _short_text(message)

    if "prompt_tokens" in out or "completion_tokens" in out:
        out["total_tokens"] = int(out.get("prompt_tokens") or 0) + int(
            out.get("completion_tokens") or 0
        )
    return out


def _short_text(value: object) -> str:
    text = " ".join(str(value).split())
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    return text[: MAX_MESSAGE_CHARS - 1].rstrip() + "..."


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _num(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
