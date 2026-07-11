"""Timeout token recovery: metrics must not treat timed-out trials as $0."""
from __future__ import annotations

import json
from pathlib import Path

from analysis.metrics import trial_metrics
from harness.pricing import DEFAULT_PRICES


def _write_log(path: Path, events: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return path


def test_metrics_backfills_tokens_when_trial_end_wiped(tmp_path):
    """Legacy bug: trial_timeout left trial_end prompt/completion at 0."""
    log = _write_log(tmp_path / "timeout.jsonl", [
        {"ts": 0, "event": "trial_start", "task": "t1_stale_read",
         "failure_mode": "stale_read", "benign": False, "strategy": "file_lock",
         "n_agents": 2, "rep": 0, "model": "gpt-5-mini",
         "agent_ids": ["a", "b"]},
        {"ts": 1, "event": "llm_usage", "agent": "a", "turn": 1,
         "prompt_tokens": 1000, "completion_tokens": 100},
        {"ts": 2, "event": "llm_usage", "agent": "b", "turn": 1,
         "prompt_tokens": 2000, "completion_tokens": 200},
        {"ts": 900, "event": "trial_timeout"},
        {"ts": 901, "event": "trial_end", "correct": False,
         "oracle_passed": 0, "oracle_total": 6, "wall_clock_s": 900.0,
         "prompt_tokens": 0, "completion_tokens": 0, "agent_statuses": {}},
    ])
    m = trial_metrics(log, prices=DEFAULT_PRICES)
    assert m["timed_out"] is True
    assert m["prompt_tokens"] == 3000
    assert m["completion_tokens"] == 300
    assert m["total_tokens"] == 3300
    assert m["estimated_usd"] > 0
    assert m["agents_timeout"] == 2


def test_metrics_prefers_trial_end_when_present(tmp_path):
    log = _write_log(tmp_path / "ok.jsonl", [
        {"ts": 0, "event": "trial_start", "task": "t1_stale_read",
         "failure_mode": "stale_read", "benign": False, "strategy": "naive",
         "n_agents": 2, "rep": 0, "model": "gpt-5-mini",
         "agent_ids": ["a", "b"]},
        {"ts": 1, "event": "llm_usage", "agent": "a", "turn": 1,
         "prompt_tokens": 100, "completion_tokens": 10},
        {"ts": 2, "event": "trial_end", "correct": True,
         "oracle_passed": 6, "oracle_total": 6, "wall_clock_s": 10.0,
         "prompt_tokens": 500, "completion_tokens": 50,
         "agent_statuses": {"a": "done", "b": "done"}},
    ])
    m = trial_metrics(log, prices=DEFAULT_PRICES)
    assert m["prompt_tokens"] == 500
    assert m["completion_tokens"] == 50
    assert m["timed_out"] is False
    assert m["agents_done"] == 2
