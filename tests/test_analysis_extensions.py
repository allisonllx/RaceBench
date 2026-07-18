"""Tests for report validation, confidence intervals, and static HTML output."""
from __future__ import annotations

import json
from pathlib import Path

from analysis.confidence import bootstrap_ci
from analysis.html_report import write_html_report
from analysis.metrics import (
    aggregate,
    aggregate_by_strategy,
    aggregate_overall,
    agent_activity_dataframe,
    event_profile_by_strategy,
    level_a_dataframe,
    run_dataframe,
)
from analysis.validate_logs import validate_run_dir
from harness.pricing import DEFAULT_PRICES


def _write_log(path: Path, events: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )
    return path


def _start(**overrides) -> dict:
    rec = {
        "ts": 0,
        "event": "trial_start",
        "task": "t02_benign_overlap",
        "failure_mode": "benign_overlap",
        "benign": True,
        "strategy": "naive",
        "n_agents": 2,
        "rep": 0,
        "model": "gpt-5-mini",
        "agent_ids": ["agent-slugify", "agent-truncate"],
    }
    rec.update(overrides)
    return rec


def _end(**overrides) -> dict:
    rec = {
        "ts": 2,
        "event": "trial_end",
        "correct": True,
        "oracle_passed": 5,
        "oracle_total": 5,
        "wall_clock_s": 12.0,
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "agent_statuses": {
            "agent-slugify": "done",
            "agent-truncate": "done",
        },
    }
    rec.update(overrides)
    return rec


def test_validate_logs_accepts_valid_dir(tmp_path):
    _write_log(tmp_path / "ok.jsonl", [_start(), _end()])
    result = validate_run_dir(tmp_path, expect_trials=1)
    assert result.ok, result.errors
    assert result.valid_trials == 1


def test_validate_logs_rejects_malformed_jsonl(tmp_path):
    (tmp_path / "bad.jsonl").write_text('{"event": "trial_start"}\nnope\n')
    result = validate_run_dir(tmp_path)
    assert not result.ok
    assert any("invalid JSON" in e for e in result.errors)


def test_validate_logs_rejects_missing_trial_end(tmp_path):
    _write_log(tmp_path / "missing_end.jsonl", [_start()])
    result = validate_run_dir(tmp_path)
    assert not result.ok
    assert any("trial_end" in e for e in result.errors)


def test_validate_logs_allows_token_fallback(tmp_path):
    _write_log(tmp_path / "fallback.jsonl", [
        _start(strategy="file_lock"),
        {"ts": 1, "event": "llm_usage", "agent": "agent-slugify", "turn": 1,
         "prompt_tokens": 250, "completion_tokens": 25},
        _end(prompt_tokens=0, completion_tokens=0),
    ])
    result = validate_run_dir(tmp_path)
    assert result.ok, result.errors
    assert any("llm_usage fallback" in w for w in result.warnings)


def test_external_logs_tagged_and_excluded_from_level_a_rollups(tmp_path):
    _write_log(tmp_path / "level_a.jsonl", [_start(strategy="naive"), _end()])
    _write_log(tmp_path / "external.jsonl", [
        _start(strategy="ext_cursor", model="external:cursor",
               mode="external", adapter="cursor"),
        _end(prompt_tokens=0, completion_tokens=0),
    ])

    result = validate_run_dir(tmp_path, expect_trials=2)
    assert result.ok, result.errors

    df = run_dataframe(tmp_path, prices=DEFAULT_PRICES)
    level_a = level_a_dataframe(df)
    by_strategy = aggregate_by_strategy(level_a)
    assert set(level_a["strategy"]) == {"naive"}
    assert set(by_strategy["strategy"]) == {"naive"}


def test_bootstrap_ci_is_deterministic(tmp_path):
    _write_log(tmp_path / "r0.jsonl", [_start(rep=0), _end(correct=True)])
    _write_log(tmp_path / "r1.jsonl", [_start(rep=1), _end(correct=False)])
    df = run_dataframe(tmp_path, prices=DEFAULT_PRICES)
    first = bootstrap_ci(df, ["strategy"], n_boot=50, seed=7)
    second = bootstrap_ci(df, ["strategy"], n_boot=50, seed=7)
    assert first.equals(second)
    assert {"correct_rate_lo", "correct_rate_hi"}.issubset(first.columns)


def test_run_dataframe_adds_run_metadata(tmp_path):
    (tmp_path / "run_meta.json").write_text(
        json.dumps({
            "run_id": "example-run",
            "provider": "agnes",
            "model": "agnes-2.0-flash",
            "prices": {"agnes-2.0-flash": {"input": 0.0, "output": 0.0}},
        }) + "\n",
        encoding="utf-8",
    )
    _write_log(tmp_path / "r0.jsonl", [
        _start(model="agnes-2.0-flash"),
        _end(correct=True),
    ])

    df = run_dataframe(tmp_path)

    assert df["run_id"].tolist() == ["example-run"]
    assert df["provider"].tolist() == ["agnes"]
    assert df["run_dir"].tolist() == [str(tmp_path)]


def test_trial_metrics_include_event_profile_counts(tmp_path):
    _write_log(tmp_path / "events.jsonl", [
        _start(strategy="file_lock"),
        {"ts": 1, "event": "llm_usage", "agent": "agent-slugify", "turn": 1,
         "prompt_tokens": 100, "completion_tokens": 20},
        {"ts": 1.1, "event": "tool_call", "agent": "agent-slugify",
         "turn": 1, "tool": "grep", "args": {"pattern": "slug"}},
        {"ts": 1.2, "event": "search", "agent": "agent-slugify",
         "kind": "grep", "pattern": "slug", "n": 2},
        {"ts": 1.3, "event": "tool_call", "agent": "agent-slugify",
         "turn": 1, "tool": "read_file", "args": {"path": "x.py"}},
        {"ts": 1.4, "event": "read", "agent": "agent-slugify",
         "path": "x.py", "found": True, "size": 10},
        {"ts": 1.5, "event": "tool_call", "agent": "agent-slugify",
         "turn": 1, "tool": "edit_file", "args": {"path": "x.py"}},
        {"ts": 1.6, "event": "coord", "strategy": "file_lock",
         "action": "blocked", "agent": "agent-slugify", "path": "x.py",
         "holder": "agent-truncate"},
        {"ts": 1.7, "event": "write", "agent": "agent-slugify",
         "path": "x.py", "kind": "replace", "status": "lock_timeout",
         "waited_s": 1.0, "changed_symbols": []},
        {"ts": 1.8, "event": "agent_done", "agent": "agent-slugify",
         "status": "done", "turns": 1, "prompt_tokens": 100,
         "completion_tokens": 20},
        {"ts": 1.9, "event": "agent_done", "agent": "agent-truncate",
         "status": "done", "turns": 0, "prompt_tokens": 0,
         "completion_tokens": 0},
        _end(prompt_tokens=100, completion_tokens=20),
    ])

    df = run_dataframe(tmp_path, prices=DEFAULT_PRICES)
    row = df.iloc[0]
    assert row["llm_calls"] == 1
    assert row["tool_calls"] == 3
    assert row["file_read_events"] == 1
    assert row["write_events"] == 1
    assert row["write_refused_events"] == 1
    assert row["search_events"] == 1
    assert row["coord_events"] == 1
    assert row["agent_turns"] == 1
    assert row["tokens_per_agent_turn"] == 120

    profile = event_profile_by_strategy(df)
    assert profile.iloc[0]["mean_tool_calls"] == 3
    assert profile.iloc[0]["mean_write_refused"] == 1


def test_agent_activity_dataframe_attributes_events_to_agents(tmp_path):
    _write_log(tmp_path / "agents.jsonl", [
        _start(strategy="notify"),
        {"ts": 1, "event": "llm_usage", "agent": "agent-slugify", "turn": 1,
         "prompt_tokens": 100, "completion_tokens": 20},
        {"ts": 1.1, "event": "tool_call", "agent": "agent-slugify",
         "turn": 1, "tool": "read_file", "args": {"path": "x.py"}},
        {"ts": 1.2, "event": "read", "agent": "agent-slugify",
         "path": "x.py", "found": True, "size": 10},
        {"ts": 1.3, "event": "llm_usage", "agent": "agent-truncate",
         "turn": 1, "prompt_tokens": 50, "completion_tokens": 10},
        {"ts": 1.4, "event": "tool_call", "agent": "agent-truncate",
         "turn": 1, "tool": "write_file", "args": {"path": "x.py"}},
        {"ts": 1.5, "event": "write", "agent": "agent-truncate",
         "path": "x.py", "kind": "overwrite", "status": "applied",
         "waited_s": 0, "changed_symbols": ["helper"]},
        {"ts": 1.6, "event": "notification_delivered",
         "agent": "agent-slugify", "turn": 2, "note": "x.py changed"},
        {"ts": 1.7, "event": "agent_done", "agent": "agent-slugify",
         "status": "done", "turns": 2, "prompt_tokens": 100,
         "completion_tokens": 20},
        {"ts": 1.8, "event": "agent_done", "agent": "agent-truncate",
         "status": "done", "turns": 1, "prompt_tokens": 50,
         "completion_tokens": 10},
        _end(prompt_tokens=150, completion_tokens=30),
    ])

    activity = agent_activity_dataframe(tmp_path)

    assert set(activity["agent"]) == {"agent-slugify", "agent-truncate"}
    slugify = activity[activity["agent"] == "agent-slugify"].iloc[0]
    truncate = activity[activity["agent"] == "agent-truncate"].iloc[0]
    assert slugify["file_reads"] == 1
    assert slugify["notifications_delivered"] == 1
    assert slugify["turns"] == 2
    assert truncate["write_attempts"] == 1
    assert truncate["write_applied"] == 1
    assert truncate["total_tokens"] == 60


def test_html_report_contains_labels_and_sections(tmp_path):
    _write_log(tmp_path / "ok.jsonl", [_start(), _end()])
    df = run_dataframe(tmp_path, prices=DEFAULT_PRICES)
    level_a = level_a_dataframe(df)
    path = write_html_report(
        out_dir=tmp_path,
        trials=df,
        level_a_trials=level_a,
        external_trials=df[df["mode"] == "external"],
        aggregate=aggregate(level_a),
        overall=aggregate_overall(level_a),
        by_strategy=aggregate_by_strategy(level_a),
    )
    html = path.read_text(encoding="utf-8")
    assert "Level A strategy benchmark" in html
    assert "Level C black-box runtime checks" in html
    assert "Interactive Comparison" in html
    assert "strategyChart" in html
    assert "donutChart" in html
    assert "heatmapChart" in html
    assert "heatmapMeta" in html
    assert "heatColorForScore" in html
    assert "metricSelect" in html
    assert "Clear filters" in html
    assert "Event Profile" in html
    assert "eventMixChart" in html
    assert "Agent Activity" in html
    assert "agentActivityTable" in html
    assert "Task x Strategy Grid" in html
    assert "Trial Logs" in html
    assert "racebench-data" in html
