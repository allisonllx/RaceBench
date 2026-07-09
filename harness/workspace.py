"""Per-trial sandbox workspace: a git-initialised copy of a task repo."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    passed: int
    failed: int
    errored: int
    output: str

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errored

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errored == 0


class Workspace:
    """A throwaway git working directory for one trial."""

    def __init__(self, root: Path):
        self.root = Path(root)

    @classmethod
    def create(cls, task_repo: Path, dest: Path) -> "Workspace":
        dest = Path(dest)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(task_repo, dest)
        ws = cls(dest)
        init = ws.git("init", "-q", "-b", "main")
        # A failed init must be LOUD: with a silently missing .git, later git
        # commands would resolve against an enclosing repository (e.g. the
        # benchmark repo itself) and pollute its history.
        toplevel = ws.git("rev-parse", "--show-toplevel").stdout.strip()
        if init.returncode != 0 or Path(toplevel or "/nonexistent").resolve() != dest.resolve():
            raise RuntimeError(
                f"git init failed in trial workspace {dest} "
                f"(stderr: {init.stderr.strip()!r}); refusing to run a trial "
                "without an isolated repository")
        ws.git("config", "user.email", "bench@racebench.local")
        ws.git("config", "user.name", "racebench")
        ws.git("add", "-A")
        ws.git("commit", "-q", "-m", "initial task state")
        return ws

    # -- file primitives (strategies call these; agents never touch disk directly)

    def read_file(self, relpath: str) -> str:
        return (self.root / relpath).read_text(encoding="utf-8")

    def write_file(self, relpath: str, content: str) -> None:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def exists(self, relpath: str) -> bool:
        return (self.root / relpath).is_file()

    def list_files(self) -> list[str]:
        files = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
                files.append(str(p.relative_to(self.root)))
        return files

    # -- git

    def git(self, *args: str) -> subprocess.CompletedProcess:
        # GIT_CEILING_DIRECTORIES stops repository discovery from walking above
        # the trial workspace, so trial git operations can never touch an
        # enclosing repo even if this workspace's .git is missing or broken.
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(self.root.parent))
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True,
            check=False, env=env,
        )

    def commit_all(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        head = self.git("rev-parse", "HEAD").stdout.strip()
        return head

    # -- test execution

    async def run_pytest(self, target: str, timeout_s: float = 120.0) -> TestResult:
        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                ["python", "-m", "pytest", target, "-q", "--tb=line",
                 "-p", "no:cacheprovider"],
                cwd=self.root, capture_output=True, text=True, timeout=timeout_s,
            )

        try:
            proc = await asyncio.to_thread(_run)
            output = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            return TestResult(0, 0, 1, "TIMEOUT")
        return _parse_pytest_summary(output)

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _parse_pytest_summary(output: str) -> TestResult:
    """Parse counts out of pytest's final summary line."""
    passed = failed = errored = 0
    for kind, pattern in (
        ("passed", r"(\d+) passed"),
        ("failed", r"(\d+) failed"),
        ("errored", r"(\d+) error"),
    ):
        m = re.search(pattern, output)
        if m:
            if kind == "passed":
                passed = int(m.group(1))
            elif kind == "failed":
                failed = int(m.group(1))
            else:
                errored = int(m.group(1))
    # collection errors produce "N errors" with zero passed/failed
    if passed == failed == errored == 0 and "error" in output.lower():
        errored = 1
    return TestResult(passed, failed, errored, output[-4000:])
