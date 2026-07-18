from __future__ import annotations

import json
from pathlib import Path

from analysis.compare_runs import (
    build_provider_tables,
    build_solo_tables,
    main as compare_main,
)


def _write_run_meta(run_dir: Path, *, run_id: str, provider: str, model: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_meta.json").write_text(
        json.dumps({
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "mode": "openai",
            "prices": {model: {"input": 0.0, "output": 0.0}},
        }) + "\n",
        encoding="utf-8",
    )


def _write_log(
    run_dir: Path,
    name: str,
    *,
    task: str = "t01_stale_clobber",
    strategy: str = "naive",
    n_agents: int = 2,
    rep: int = 0,
    model: str = "gpt-5-mini",
    correct: bool = True,
    wall_clock_s: float = 10.0,
    prompt_tokens: int = 100,
    completion_tokens: int = 10,
) -> None:
    events = [
        {
            "ts": 0,
            "event": "trial_start",
            "task": task,
            "failure_mode": "stale_read_lost_update",
            "benign": False,
            "strategy": strategy,
            "n_agents": n_agents,
            "rep": rep,
            "model": model,
            "agent_ids": [f"agent-{i}" for i in range(n_agents)],
        },
        {
            "ts": 1,
            "event": "trial_end",
            "correct": correct,
            "oracle_passed": 1 if correct else 0,
            "oracle_total": 1,
            "wall_clock_s": wall_clock_s,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "agent_statuses": {
                f"agent-{i}": "done" for i in range(n_agents)
            },
        },
    ]
    (run_dir / name).write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def test_provider_tables_use_shared_cells_only(tmp_path):
    openai = tmp_path / "grid-v1"
    agnes = tmp_path / "grid-v1-agnes-sensitivity"
    _write_run_meta(openai, run_id="grid-v1", provider="openai",
                    model="gpt-5-mini")
    _write_run_meta(agnes, run_id="grid-v1-agnes-sensitivity",
                    provider="agnes", model="agnes-2.0-flash")
    _write_log(openai, "t01__naive-r0.jsonl", correct=True,
               wall_clock_s=10.0, prompt_tokens=100, completion_tokens=10)
    _write_log(openai, "t02__naive-r0.jsonl", task="t02_benign_overlap",
               correct=True, wall_clock_s=8.0)
    _write_log(agnes, "t01__naive-r0.jsonl", model="agnes-2.0-flash",
               correct=False, wall_clock_s=20.0,
               prompt_tokens=200, completion_tokens=20)

    tables = build_provider_tables([openai, agnes])

    summary = tables["provider_comparison"]
    assert set(summary["run_id"]) == {"grid-v1", "grid-v1-agnes-sensitivity"}
    assert set(summary["n_cells"]) == {1}

    delta = tables["provider_delta_by_strategy"]
    assert len(delta) == 1
    row = delta.iloc[0]
    assert row["strategy"] == "naive"
    assert row["compare_provider"] == "agnes"
    assert row["delta_correct_rate"] == -1.0
    assert row["delta_mean_wall_s"] == -10.0


def test_solo_tables_compare_calibration_against_parallel(tmp_path):
    solo = tmp_path / "grid-v1-calibration"
    parallel = tmp_path / "grid-v1"
    _write_run_meta(solo, run_id="grid-v1-calibration", provider="openai",
                    model="gpt-5-mini")
    _write_run_meta(parallel, run_id="grid-v1", provider="openai",
                    model="gpt-5-mini")
    _write_log(solo, "t01__solo-r0.jsonl", n_agents=1, correct=True,
               wall_clock_s=30.0, prompt_tokens=300, completion_tokens=30)
    _write_log(parallel, "t01__naive-r0.jsonl", strategy="naive",
               n_agents=2, correct=False, wall_clock_s=20.0)
    _write_log(parallel, "t01__file_lock-r0.jsonl", strategy="file_lock",
               n_agents=2, correct=True, wall_clock_s=40.0)

    tables = build_solo_tables(solo, parallel)

    by_cell = tables["solo_vs_parallel"]
    assert set(by_cell["strategy"]) == {"naive", "file_lock"}
    naive = by_cell[by_cell["strategy"] == "naive"].iloc[0]
    assert naive["delta_correct_rate"] == -1.0
    assert naive["delta_mean_wall_s"] == 10.0

    by_strategy = tables["solo_vs_parallel_by_strategy"]
    assert set(by_strategy["strategy"]) == {"naive", "file_lock"}


def test_compare_runs_cli_writes_tables(tmp_path):
    openai = tmp_path / "grid-v1"
    agnes = tmp_path / "grid-v1-agnes-sensitivity"
    solo = tmp_path / "grid-v1-calibration"
    out = tmp_path / "cross-run-analysis"
    _write_run_meta(openai, run_id="grid-v1", provider="openai",
                    model="gpt-5-mini")
    _write_run_meta(agnes, run_id="grid-v1-agnes-sensitivity",
                    provider="agnes", model="agnes-2.0-flash")
    _write_run_meta(solo, run_id="grid-v1-calibration", provider="openai",
                    model="gpt-5-mini")
    _write_log(openai, "t01__naive-r0.jsonl")
    _write_log(agnes, "t01__naive-r0.jsonl", model="agnes-2.0-flash")
    _write_log(solo, "t01__solo-r0.jsonl", n_agents=1)

    rc = compare_main([
        "--provider-runs", str(openai), str(agnes),
        "--solo-run", str(solo),
        "--out", str(out),
    ])

    assert rc == 0
    assert (out / "provider_comparison.csv").is_file()
    assert (out / "provider_delta_by_strategy.md").is_file()
    assert (out / "solo_vs_parallel.csv").is_file()
