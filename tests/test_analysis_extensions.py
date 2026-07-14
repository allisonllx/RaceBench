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
    assert "Task x Strategy Grid" in html
    assert "Trial Logs" in html
    assert "racebench-data" in html
