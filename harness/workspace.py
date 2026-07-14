"""Per-trial sandbox workspace: a git-initialised copy of a task repo.

Supports isolation modes:
  shared   — all agents read/write the same tree (default)
  worktree — each agent gets a private copy under .worktrees/<agent_id>/;
             merge_agent_trees() commits each tree onto agent/<id> (private
             index) then merges those branches into main before the oracle.

Git metadata lives in `.racebench_git` (not `.git`) so trial sandboxes stay
isolated from the host repo and from environments that block `.git` writes.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
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
        init = ws.git("init", "-q", "-b", "main", "--template=")
        # Confirm the trial repo is self-contained (not the host repo).
        git_dir = (dest / GIT_STORE).resolve()
        if init.returncode != 0 or not git_dir.is_dir():
            raise RuntimeError(
                f"git init failed in trial workspace {dest} "
                f"(stderr: {init.stderr.strip()!r}); refusing to run a trial "
                "without an isolated repository")
        ws.git("config", "user.email", "bench@racebench.local")
        ws.git("config", "user.name", "racebench")
        ws.git("config", "advice.detachedHead", "false")
        # GIT_DIR lives inside the work tree — never track it (or agent trees).
        (dest / ".gitignore").write_text(
            f"{GIT_STORE}/\n{WORKTREES}/\n", encoding="utf-8")
        ws.git("add", "-A")
        ws.git("commit", "-q", "-m", "initial task state")
        if isolation == "worktree":
            ws.setup_worktrees(agent_ids or [])
        return ws

    def setup_worktrees(self, agent_ids: list[str]) -> None:
        """Private file trees + branches forked from current main HEAD."""
        self._agent_ids = list(agent_ids)
        base = self.root / WORKTREES
        if base.exists():
            shutil.rmtree(base)
        base.mkdir(parents=True)
        head = self.git("rev-parse", "HEAD").stdout.strip()
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
            # Point agent branch at the same commit as main (no checkout fight).
            self.git("branch", "-f", f"agent/{aid}", head)

    def agent_root(self, agent_id: str | None = None) -> Path:
        if self.isolation == "worktree" and agent_id:
            return self.root / WORKTREES / agent_id
        return self.root

    def _index_path(self, agent_id: str | None = None) -> Path | None:
        if self.isolation == "worktree" and agent_id:
            idx_dir = self.root / GIT_STORE / "indexes"
            idx_dir.mkdir(parents=True, exist_ok=True)
            return idx_dir / agent_id
        return None

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

    def git(self, *args: str, work_tree: Path | None = None,
            index_file: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ,
                   GIT_DIR=str(self.root / GIT_STORE),
                   GIT_WORK_TREE=str(work_tree or self.root))
        if index_file is not None:
            env["GIT_INDEX_FILE"] = str(index_file)
        # Drop stale locks from interrupted prior ops (common in tests).
        lock = self.root / GIT_STORE / "index.lock"
        if lock.exists():
            try:
                lock.unlink()
            except OSError:
                pass
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True,
            check=False, env=env,
        )

    def _commit_work_tree(self, work_tree: Path, message: str,
                          branch: str | None = None,
                          agent_id: str | None = None) -> str:
        """Stage work_tree into a private index and commit (optionally to branch)."""
        index = self._index_path(agent_id)
        if index is not None and index.exists():
            index.unlink()
        self.git("add", "-A", work_tree=work_tree, index_file=index)
        # Parent = current tip of the target branch (or HEAD).
        if branch:
            parent = self.git("rev-parse", branch).stdout.strip()
        else:
            parent = self.git("rev-parse", "HEAD").stdout.strip()
        tree = self.git("write-tree", work_tree=work_tree, index_file=index)
        if tree.returncode != 0:
            raise RuntimeError(f"write-tree failed: {tree.stderr.strip()}")
        tree_oid = tree.stdout.strip()
        commit = self.git(
            "commit-tree", tree_oid, "-p", parent, "-m", message,
            work_tree=work_tree, index_file=index)
        if commit.returncode != 0:
            raise RuntimeError(f"commit-tree failed: {commit.stderr.strip()}")
        commit_oid = commit.stdout.strip()
        if branch:
            self.git("update-ref", f"refs/heads/{branch}", commit_oid)
        else:
            self.git("update-ref", "HEAD", commit_oid)
        return commit_oid

    def commit_all(self, message: str, agent_id: str | None = None) -> str:
        wt = self.agent_root(agent_id)
        if self.isolation == "worktree" and agent_id:
            return self._commit_work_tree(
                wt, message, branch=f"agent/{agent_id}", agent_id=agent_id)
        self.git("add", "-A", work_tree=wt)
        self.git("commit", "-q", "--allow-empty", "-m", message, work_tree=wt)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def _blob_at(self, rev: str, relpath: str) -> str | None:
        proc = self.git("show", f"{rev}:{relpath}")
        if proc.returncode != 0:
            return None
        return proc.stdout

    def _three_way_merge_text(self, base: str, ours: str, theirs: str) -> tuple[bool, str]:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            paths = {}
            for name, content in (("base", base), ("ours", ours), ("theirs", theirs)):
                p = Path(td) / name
                p.write_text(content, encoding="utf-8")
                paths[name] = p
            proc = subprocess.run(
                ["git", "merge-file", "-p",
                 "-L", "main", "-L", "base", "-L", "agent",
                 str(paths["ours"]), str(paths["base"]), str(paths["theirs"])],
                capture_output=True, text=True,
            )
            # merge-file -p prints result on stdout; rc 0 = clean
            return proc.returncode == 0, proc.stdout

    def _union_python_methods(self, ours: str, theirs: str) -> str | None:
        """If both sides are valid Python, union top-level + class methods by name.

        Prefer *theirs* when the same method exists on both sides; keep unique
        methods from either side. Used when line-level merge-file conflicts —
        the common t12 case where each agent rewrites Greeter but adds a
        different method.
        """
        import ast

        try:
            o_tree, t_tree = ast.parse(ours), ast.parse(theirs)
        except SyntaxError:
            return None

        def body_map(tree: ast.AST) -> dict[str, ast.AST]:
            out: dict[str, ast.AST] = {}
            for node in getattr(tree, "body", []):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    out[node.name] = node
            return out

        def method_score(node: ast.AST) -> int:
            """Higher is better. Stub `raise NotImplementedError` scores lowest."""
            body = getattr(node, "body", []) or []
            # Skip docstring
            stmts = body
            if (stmts and isinstance(stmts[0], ast.Expr)
                    and isinstance(getattr(stmts[0], "value", None), ast.Constant)):
                stmts = stmts[1:]
            if len(stmts) == 1 and isinstance(stmts[0], ast.Raise):
                exc = stmts[0].exc
                if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                    return 0
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) \
                        and exc.func.id == "NotImplementedError":
                    return 0
            return 1 + len(stmts)

        def merge_class(o_cls: ast.ClassDef, t_cls: ast.ClassDef) -> ast.ClassDef:
            methods: dict[str, ast.AST] = {}
            for node in o_cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[node.name] = node
            for node in t_cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    existing = methods.get(node.name)
                    if existing is None or method_score(node) >= method_score(existing):
                        methods[node.name] = node
            # Keep non-method body stmts from theirs (docstring etc.), then methods.
            preamble = [
                n for n in t_cls.body
                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            new_body = preamble + list(methods.values())
            return ast.ClassDef(
                name=t_cls.name, bases=t_cls.bases, keywords=t_cls.keywords,
                body=new_body or [ast.Pass()], decorator_list=t_cls.decorator_list,
            )

        o_map, t_map = body_map(o_tree), body_map(t_tree)
        names = list(dict.fromkeys([*o_map.keys(), *t_map.keys()]))
        new_body: list[ast.AST] = []
        # Keep module preamble (imports) from theirs if present, else ours.
        for node in t_tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                new_body.append(node)
        if not any(not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   for n in new_body):
            for node in o_tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    new_body.append(node)

        for name in names:
            o_n, t_n = o_map.get(name), t_map.get(name)
            if isinstance(o_n, ast.ClassDef) and isinstance(t_n, ast.ClassDef):
                new_body.append(merge_class(o_n, t_n))
            elif (isinstance(o_n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and isinstance(t_n, (ast.FunctionDef, ast.AsyncFunctionDef))):
                new_body.append(t_n if method_score(t_n) >= method_score(o_n) else o_n)
            elif t_n is not None:
                new_body.append(t_n)
            elif o_n is not None:
                new_body.append(o_n)

        try:
            return ast.unparse(ast.Module(body=new_body, type_ignores=[])) + "\n"
        except Exception:
            return None

    def _integrate_agent_branch(self, aid: str) -> bool:
        """Merge agent/<aid> into main. On conflict, per-file 3-way merge
        (not whole-tree overwrite) so disjoint edits in the same file can both
        survive — critical for t12_split_view."""
        branch = f"agent/{aid}"
        proc = self.git("merge", "-q", "--no-edit", branch)
        if proc.returncode == 0:
            return True

        # Abort the in-progress merge, then rebuild file-by-file.
        self.git("merge", "--abort")
        base = self.git("merge-base", "main", branch).stdout.strip()
        if not base:
            base = self.git("rev-parse", "main").stdout.strip()

        changed = self.git(
            "diff", "--name-only", "-z", base, branch).stdout.split("\0")
        changed = [c for c in changed if c]
        for rel in changed:
            if any(part in SKIP_PARTS for part in Path(rel).parts):
                continue
            theirs = self._blob_at(branch, rel)
            if theirs is None:
                # deleted on agent branch
                dest = self.root / rel
                if dest.exists():
                    dest.unlink()
                continue
            ours = self._blob_at("main", rel)
            ancestor = self._blob_at(base, rel)
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if ours is None or ancestor is None:
                dest.write_text(theirs, encoding="utf-8")
            elif ours == ancestor:
                dest.write_text(theirs, encoding="utf-8")
            elif theirs == ancestor:
                pass  # keep ours
            else:
                clean, merged = self._three_way_merge_text(ancestor, ours, theirs)
                if clean:
                    dest.write_text(merged, encoding="utf-8")
                elif rel.endswith(".py"):
                    unioned = self._union_python_methods(ours, theirs)
                    dest.write_text(unioned if unioned is not None else theirs,
                                    encoding="utf-8")
                else:
                    dest.write_text(theirs, encoding="utf-8")

        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m",
                 f"integrate agent/{aid} (per-file merge after conflict)")
        return False

    def merge_agent_trees(self) -> MergeResult:
        """Commit each agent tree onto agent/<id>, then merge into main."""
        if self.isolation != "worktree":
            return MergeResult(ok=True, message="shared isolation — nothing to merge")
        conflicts: list[str] = []

        for aid in self._agent_ids:
            wt = self.agent_root(aid)
            self._commit_work_tree(
                wt, f"agent {aid} final",
                branch=f"agent/{aid}", agent_id=aid)

        # Merge into main at the shared root (default index).
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("read-tree", "HEAD")  # sync index to main
        self.git("checkout-index", "-a", "-f")  # sync work tree files to main tip

        for aid in self._agent_ids:
            if not self._integrate_agent_branch(aid):
                conflicts.append(aid)

        return MergeResult(
            ok=len(conflicts) == 0,
            conflicts=conflicts,
            message=("clean" if not conflicts
                     else f"conflicts for agents: {conflicts}; "
                          "per-file merged"),
        )

    async def run_pytest(self, target: str, timeout_s: float = 120.0,
                         agent_id: str | None = None) -> TestResult:
        cwd = self.agent_root(agent_id) if agent_id else self.root

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-m", "pytest", target, "-q", "--tb=line",
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
