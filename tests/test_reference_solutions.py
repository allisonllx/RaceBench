"""Every task ships a reference solution in <task>/reference/. Overlaying it on
the initial repo must make BOTH the visible tests and the hidden oracle pass —
proof that each task is satisfiable and the oracle is not over-constrained."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from harness.task import list_tasks, load_task


def _pytest(cwd: Path, target: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
        cwd=cwd, capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _overlay_reference(reference: Path, dst: Path) -> None:
    """Copy reference files/dirs onto dst, preserving package layout."""
    for item in reference.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


@pytest.mark.parametrize("task_name", list_tasks())
def test_reference_solution_passes_oracle(task_name, tmp_path):
    task = load_task(task_name)
    reference = task.path / "reference"
    assert reference.is_dir(), f"{task_name} has no reference solution"

    dst = tmp_path / "repo"
    shutil.copytree(task.repo, dst)
    _overlay_reference(reference, dst)
    shutil.copytree(task.oracle_tests, dst / "oracle_tests")

    code, out = _pytest(dst, "tests")
    assert code == 0, f"{task_name}: visible tests fail on reference:\n{out}"
    code, out = _pytest(dst, "oracle_tests")
    assert code == 0, f"{task_name}: oracle fails on reference solution:\n{out}"
