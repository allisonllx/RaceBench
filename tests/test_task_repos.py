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
    assert (task.path / "collision_map.yaml").is_file()
