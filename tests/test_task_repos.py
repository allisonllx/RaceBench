"""Sanity: every task's visible tests pass on the initial repo, and the oracle
FAILS on the initial repo (otherwise the task measures nothing)."""
import subprocess
import sys
from pathlib import Path

import pytest

from harness.task import TASKS_DIR, list_tasks, load_task


def _pytest(cwd: Path, target: str) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
        cwd=cwd, capture_output=True, text=True,
    )
    return proc.returncode


@pytest.mark.parametrize("task_name", list_tasks())
def test_visible_tests_pass_initially(task_name, tmp_path):
    task = load_task(task_name)
    import shutil
    dst = tmp_path / "repo"
    shutil.copytree(task.repo, dst)
    assert _pytest(dst, "tests") == 0, f"{task_name}: visible tests fail on initial repo"


@pytest.mark.parametrize("task_name", list_tasks())
def test_oracle_fails_initially(task_name, tmp_path):
    task = load_task(task_name)
    import shutil
    dst = tmp_path / "repo"
    shutil.copytree(task.repo, dst)
    shutil.copytree(task.oracle_tests, dst / "oracle_tests")
    assert _pytest(dst, "oracle_tests") != 0, \
        f"{task_name}: oracle passes before any agent work — task is vacuous"


@pytest.mark.parametrize("task_name", list_tasks())
def test_task_spec_loads(task_name):
    task = load_task(task_name)
    assert task.agents, "task defines no agents"
    assert 1 <= task.min_agents <= len(task.agents)
    assert (task.path / "collision_map.yaml").is_file()


def test_rw_e_cascade_requires_full_agent_chain():
    """n=2 would drop agent-feed and make the feed oracle unreachable."""
    task = load_task("rw_e_cascade")
    assert task.min_agents == 3
    assert len(task.agents) == 3
    with pytest.raises(ValueError, match="at least 3"):
        task.agent_subset(2)
    ids = [a.id for a in task.agent_subset(3)]
    assert ids == ["agent-schema", "agent-comments", "agent-feed"]


def test_collect_pending_skips_truncated_cascade_cells(tmp_path):
    from runner.run_grid import collect_pending

    cfg = {
        "tasks": ["rw_e_cascade", "t01_stale_clobber"],
        "strategies": ["naive"],
        "agent_counts": [2, 3, 4],
        "reps": 1,
        "max_turns": 5,
        "lock_timeout_s": 1,
        "trial_timeout_s": 10,
        "mode": "scripted",
        "script_variant": "edit",
        "model": "scripted",
    }
    pending = collect_pending(cfg, tmp_path, calibrate=False)
    cells = {(j.task_name, j.n) for j in pending}
    assert ("rw_e_cascade", 3) in cells
    assert ("rw_e_cascade", 2) not in cells
    assert ("rw_e_cascade", 4) not in cells
    assert ("t01_stale_clobber", 2) in cells
    assert ("t01_stale_clobber", 3) not in cells


def test_calibration_allows_solo_despite_min_agents():
    from runner.run_grid import calibration_task

    task = calibration_task(load_task("rw_e_cascade"))
    assert task.min_agents == 1
    assert [a.id for a in task.agent_subset(1)] == ["solo"]
    assert "feed_summary" in task.agents[0].prompt or "feed" in task.agents[0].prompt.lower()
