"""Per-trial sandbox workspace: a git-initialised copy of a task repo.

Supports isolation modes:
  shared   — all agents read/write the same tree (default)
  worktree — each agent gets a private copy under .worktrees/<agent_id>/;
             merge_agent_trees() folds them into main before the oracle
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
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


@dataclass
class MergeResult:
    ok: bool
    conflicts: list[str] = field(default_factory=list)
    message: str = ""


GIT_STORE = ".racebench_git"
WORKTREES = ".worktrees"
SKIP_PARTS = {".git", GIT_STORE, WORKTREES, "__pycache__"}


class Workspace:
    """A throwaway git working directory for one trial."""

    def __init__(self, root: Path, isolation: str = "shared"):
        self.root = Path(root).resolve()
        self.isolation = isolation
        self._agent_ids: list[str] = []

    @classmethod
    def create(cls, task_repo: Path, dest: Path,
               isolation: str = "shared",
               agent_ids: list[str] | None = None) -> "Workspace":
        dest = Path(dest)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(task_repo, dest)
        ws = cls(dest, isolation=isolation)
        init = ws.git("init", "-q", "-b", "main")
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
        if isolation == "worktree":
            ws.setup_worktrees(agent_ids or [])
        return ws

    def setup_worktrees(self, agent_ids: list[str]) -> None:
        self._agent_ids = list(agent_ids)
        base = self.root / WORKTREES
        if base.exists():
            shutil.rmtree(base)
        base.mkdir(parents=True)
        for aid in agent_ids:
            dest = base / aid
            dest.mkdir(parents=True)
            for item in self.root.iterdir():
                if item.name in SKIP_PARTS:
                    continue
                target = dest / item.name
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
            # branch tip for this agent (from current HEAD)
            self.git("branch", f"agent/{aid}")

    def agent_root(self, agent_id: str | None = None) -> Path:
        if self.isolation == "worktree" and agent_id:
            return self.root / WORKTREES / agent_id
        return self.root

    # -- file primitives

    def read_file(self, relpath: str, agent_id: str | None = None) -> str:
        return (self.agent_root(agent_id) / relpath).read_text(encoding="utf-8")

    def write_file(self, relpath: str, content: str,
                   agent_id: str | None = None) -> None:
        path = self.agent_root(agent_id) / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def exists(self, relpath: str, agent_id: str | None = None) -> bool:
        return (self.agent_root(agent_id) / relpath).is_file()

    def list_files(self, agent_id: str | None = None) -> list[str]:
        root = self.agent_root(agent_id)
        files = []
        for p in sorted(root.rglob("*")):
            if p.is_file() and not any(part in SKIP_PARTS for part in p.parts):
                files.append(str(p.relative_to(root)))
        return files

    def grep(self, pattern: str, agent_id: str | None = None,
             glob: str = "*") -> list[str]:
        """Return 'path:line:text' hits (capped)."""
        import fnmatch
        root = self.agent_root(agent_id)
        hits: list[str] = []
        for p in sorted(root.rglob(glob)):
            if not p.is_file() or any(part in SKIP_PARTS for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern in line:
                    hits.append(f"{p.relative_to(root)}:{i}:{line}")
                    if len(hits) >= 100:
                        return hits
        return hits

    def glob_files(self, pattern: str, agent_id: str | None = None) -> list[str]:
        import fnmatch
        root = self.agent_root(agent_id)
        out = []
        for p in sorted(root.rglob("*")):
            if not p.is_file() or any(part in SKIP_PARTS for part in p.parts):
                continue
            rel = str(p.relative_to(root))
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
                out.append(rel)
        return out

    # -- git

    def git(self, *args: str, work_tree: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ,
                   GIT_DIR=str(self.root / GIT_STORE),
                   GIT_WORK_TREE=str(work_tree or self.root))
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True,
            check=False, env=env,
        )

    def commit_all(self, message: str, agent_id: str | None = None) -> str:
        wt = self.agent_root(agent_id)
        if self.isolation == "worktree" and agent_id:
            self.git("checkout", f"agent/{agent_id}", work_tree=wt)
        self.git("add", "-A", work_tree=wt)
        self.git("commit", "-q", "--allow-empty", "-m", message, work_tree=wt)
        head = self.git("rev-parse", "HEAD", work_tree=wt).stdout.strip()
        return head

    def merge_agent_trees(self) -> MergeResult:
        """Merge each agent worktree branch into main (shared root)."""
        if self.isolation != "worktree":
            return MergeResult(ok=True, message="shared isolation — nothing to merge")
        conflicts: list[str] = []
        # ensure main is checked out in root
        self.git("checkout", "-q", "main")
        for aid in self._agent_ids:
            wt = self.agent_root(aid)
            # commit any uncommitted agent edits onto their branch
            self.git("checkout", "-q", f"agent/{aid}", work_tree=wt)
            self.git("add", "-A", work_tree=wt)
            self.git("commit", "-q", "--allow-empty", "-m",
                     f"agent {aid} final", work_tree=wt)
            # merge into main at root
            self.git("checkout", "-q", "main")
            proc = self.git("merge", "-q", "--no-edit", f"agent/{aid}")
            if proc.returncode != 0:
                conflicts.append(aid)
                self.git("merge", "--abort")
                # fallback: copy agent files over main (last-resort for oracle)
                for p in wt.rglob("*"):
                    if not p.is_file() or any(part in SKIP_PARTS for part in p.parts):
                        continue
                    rel = p.relative_to(wt)
                    dest = self.root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest)
                self.git("add", "-A")
                self.git("commit", "-q", "--allow-empty", "-m",
                         f"force-integrate agent/{aid} after conflict")
        return MergeResult(
            ok=len(conflicts) == 0,
            conflicts=conflicts,
            message=("clean" if not conflicts
                     else f"conflicts for agents: {conflicts}; force-integrated"),
        )

    async def run_pytest(self, target: str, timeout_s: float = 120.0,
                         agent_id: str | None = None) -> TestResult:
        cwd = self.agent_root(agent_id) if agent_id else self.root

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                ["python", "-m", "pytest", target, "-q", "--tb=line",
                 "-p", "no:cacheprovider"],
                cwd=cwd, capture_output=True, text=True, timeout=timeout_s,
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
    if passed == failed == errored == 0 and "error" in output.lower():
        errored = 1
    return TestResult(passed, failed, errored, output[-4000:])
