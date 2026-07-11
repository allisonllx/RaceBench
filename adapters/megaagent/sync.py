"""Copy trees between RaceBench workspaces and MegaAgent's files/ directory."""
from __future__ import annotations

import shutil
from pathlib import Path

SEED_SKIP_NAMES = {
    ".racebench_git",
    ".worktrees",
    ".racebench_instructions",
    "oracle_tests",
    "__pycache__",
    ".git",
    ".DS_Store",
}

COLLECT_SKIP_NAMES = {
    ".git",
    ".gitkeep",
    "__pycache__",
    ".DS_Store",
}


def _should_skip_seed(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return any(part in SEED_SKIP_NAMES for part in rel_parts)


def _should_skip_collect(path: Path, root: Path) -> bool:
    name = path.name
    if name in COLLECT_SKIP_NAMES:
        return True
    if name.startswith("todo_") and name.endswith(".txt"):
        return True
    if name.startswith("status_") and name.endswith(".txt"):
        return True
    rel_parts = path.relative_to(root).parts
    return any(part in COLLECT_SKIP_NAMES for part in rel_parts)


def seed_files(racebench_root: Path, megaagent_files: Path) -> int:
    """Copy RaceBench workspace into MegaAgent files/. Returns file count."""
    src = Path(racebench_root).resolve()
    dst = Path(megaagent_files).resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"racebench root missing: {src}")
    dst.mkdir(parents=True, exist_ok=True)

    copied = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip_seed(path, src):
            continue
        rel = path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def collect_files(megaagent_files: Path, racebench_root: Path) -> int:
    """Copy MegaAgent files/ back into RaceBench root. Returns file count."""
    src = Path(megaagent_files).resolve()
    dst = Path(racebench_root).resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"megaagent files missing: {src}")
    dst.mkdir(parents=True, exist_ok=True)

    copied = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip_collect(path, src):
            continue
        rel = path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied
