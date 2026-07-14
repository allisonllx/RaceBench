"""Validate RaceBench JSONL result logs.

Usage:
    python -m analysis.validate_logs results/grid-v1 --expect-trials 480
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.task import TASKS_DIR

REQUIRED_START = {
    "task", "failure_mode", "benign", "strategy", "n_agents", "rep",
    "model", "agent_ids",
}
REQUIRED_END = {
    "correct", "oracle_passed", "oracle_total", "wall_clock_s",
    "prompt_tokens", "completion_tokens", "agent_statuses",
}


@dataclass
class ValidationResult:
    logs_seen: int
    valid_trials: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path.name}:{lineno}: invalid JSON: {exc.msg}")
                    continue
                if not isinstance(rec, dict):
                    errors.append(f"{path.name}:{lineno}: JSONL record is not an object")
                    continue
                events.append(rec)
    except OSError as exc:
        errors.append(f"{path.name}: cannot read log: {exc}")
    return events, errors


def _missing(record: dict[str, Any] | None, required: set[str]) -> list[str]:
    if record is None:
        return sorted(required)
    return sorted(k for k in required if k not in record)


def validate_log(path: Path) -> tuple[bool, list[str], list[str]]:
    """Validate a single JSONL log. Returns (valid_trial, errors, warnings)."""
    events, errors = _read_jsonl(path)
    warnings: list[str] = []
    if errors:
        return False, errors, warnings

    starts = [e for e in events if e.get("event") == "trial_start"]
    ends = [e for e in events if e.get("event") == "trial_end"]
    if len(starts) != 1:
        errors.append(f"{path.name}: expected exactly one trial_start, found {len(starts)}")
    if len(ends) != 1:
        errors.append(f"{path.name}: expected exactly one trial_end, found {len(ends)}")
    start = starts[0] if starts else None
    end = ends[0] if ends else None

    for field in _missing(start, REQUIRED_START):
        errors.append(f"{path.name}: trial_start missing {field}")
    for field in _missing(end, REQUIRED_END):
        errors.append(f"{path.name}: trial_end missing {field}")
    if errors:
        return False, errors, warnings

    assert start is not None and end is not None
    task_dir = TASKS_DIR / str(start["task"])
    if not task_dir.is_dir():
        errors.append(f"{path.name}: unknown task {start['task']!r}")

    mode = start.get("mode", "strategy")
    strategy = str(start.get("strategy", ""))
    if mode == "external":
        if not strategy.startswith("ext_"):
            errors.append(f"{path.name}: external trial strategy must start with ext_")
        if not start.get("adapter"):
            errors.append(f"{path.name}: external trial_start missing adapter")
    elif strategy.startswith("ext_"):
        errors.append(f"{path.name}: ext_* strategy must be tagged mode=external")

    if int(start.get("n_agents") or 0) != len(start.get("agent_ids") or []):
        errors.append(f"{path.name}: n_agents does not match agent_ids length")

    prompt = int(end.get("prompt_tokens") or 0)
    completion = int(end.get("completion_tokens") or 0)
    usage_events = [e for e in events if e.get("event") == "llm_usage"]
    if mode != "external" and prompt + completion == 0:
        if usage_events:
            warnings.append(
                f"{path.name}: trial_end tokens are zero; metrics will use llm_usage fallback")
        else:
            errors.append(
                f"{path.name}: no token accounting in trial_end or llm_usage events")

    if int(end.get("oracle_total") or 0) <= 0:
        errors.append(f"{path.name}: oracle_total must be positive")
    if float(end.get("wall_clock_s") or 0.0) < 0:
        errors.append(f"{path.name}: wall_clock_s must be non-negative")

    return not errors, errors, warnings


def validate_run_dir(run_dir: Path, expect_trials: int | None = None) -> ValidationResult:
    run_dir = Path(run_dir)
    logs = sorted(run_dir.glob("*.jsonl"))
    errors: list[str] = []
    warnings: list[str] = []
    valid_trials = 0
    if not run_dir.is_dir():
        errors.append(f"{run_dir}: not a directory")
        return ValidationResult(0, 0, errors, warnings)
    if not logs:
        errors.append(f"{run_dir}: no top-level JSONL logs found")
        return ValidationResult(0, 0, errors, warnings)

    for log in logs:
        valid, log_errors, log_warnings = validate_log(log)
        errors.extend(log_errors)
        warnings.extend(log_warnings)
        if valid:
            valid_trials += 1

    if expect_trials is not None and valid_trials != expect_trials:
        errors.append(
            f"{run_dir}: expected {expect_trials} valid trials, found {valid_trials}")
    return ValidationResult(len(logs), valid_trials, errors, warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--expect-trials", type=int, default=None)
    args = parser.parse_args(argv)

    result = validate_run_dir(args.run_dir, expect_trials=args.expect_trials)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    print(
        f"validated {result.valid_trials}/{result.logs_seen} JSONL trial logs "
        f"in {args.run_dir}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
