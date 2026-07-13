"""Tests for resume helpers and run_external skip-if-complete behavior."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from harness.events import has_trial_end, read_trial_end


def test_has_trial_end_false_when_missing(tmp_path):
    assert has_trial_end(tmp_path / "nope.jsonl") is False


def test_has_trial_end_false_when_incomplete(tmp_path):
    path = tmp_path / "partial.jsonl"
    path.write_text(
        json.dumps({"event": "trial_start", "task": "t02"}) + "\n",
        encoding="utf-8",
    )
    assert has_trial_end(path) is False
    assert read_trial_end(path) is None


def test_has_trial_end_true_when_complete(tmp_path):
    path = tmp_path / "done.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"event": "trial_start"}),
                json.dumps(
                    {
                        "event": "trial_end",
                        "correct": True,
                        "oracle_passed": 6,
                        "oracle_total": 6,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert has_trial_end(path) is True
    end = read_trial_end(path)
    assert end is not None
    assert end["correct"] is True
    assert end["oracle_passed"] == 6


def test_run_external_skips_completed_log(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    log = out / "t02_benign_overlap__ext_scripted-n2-r0.jsonl"
    log.write_text(
        json.dumps(
            {
                "event": "trial_end",
                "correct": True,
                "oracle_passed": 6,
                "oracle_total": 6,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = log.read_text(encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.run_external",
            "--task",
            "t02_benign_overlap",
            "--adapter",
            "scripted",
            "--out",
            str(out),
            "--workdir",
            str(tmp_path / "ws"),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "skipped" in proc.stdout.lower()
    assert log.read_text(encoding="utf-8") == before


def test_run_external_reruns_incomplete_log(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    log = out / "t02_benign_overlap__ext_scripted-n2-r0.jsonl"
    log.write_text(
        json.dumps({"event": "trial_start", "task": "t02_benign_overlap"}) + "\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.run_external",
            "--task",
            "t02_benign_overlap",
            "--adapter",
            "scripted",
            "--out",
            str(out),
            "--workdir",
            str(tmp_path / "ws"),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "skipped" not in proc.stdout.lower()
    assert has_trial_end(log)
    # Fresh log should not keep the orphan trial_start-only prefix as sole content
    events = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert events[0]["event"] == "trial_start"
    assert any(e["event"] == "trial_end" for e in events)
