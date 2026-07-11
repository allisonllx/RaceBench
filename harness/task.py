"""Task definitions: a task is a directory with task.yaml, repo/, oracle_tests/,
and collision_map.yaml (documentation of the seeded collision points)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


@dataclass
class TaskAgentSpec:
    id: str
    prompt: str


@dataclass
class Task:
    name: str
    path: Path
    failure_mode: str
    benign: bool
    agents: list[TaskAgentSpec]
    isolation: str = "shared"          # shared | worktree
    registry: dict[str, Any] = field(default_factory=dict)

    @property
    def repo(self) -> Path:
        return self.path / "repo"

    @property
    def oracle_tests(self) -> Path:
        return self.path / "oracle_tests"

    def agent_subset(self, n: int) -> list[TaskAgentSpec]:
        if n > len(self.agents):
            raise ValueError(f"task {self.name} defines {len(self.agents)} agents, "
                             f"requested {n}")
        return self.agents[:n]


def load_task(name: str, tasks_dir: Path = TASKS_DIR) -> Task:
    path = Path(tasks_dir) / name
    spec = yaml.safe_load((path / "task.yaml").read_text(encoding="utf-8"))
    isolation = spec.get("isolation", "shared")
    if isolation not in ("shared", "worktree"):
        raise ValueError(f"task {name}: isolation must be shared|worktree, "
                         f"got {isolation!r}")
    return Task(
        name=spec["name"],
        path=path,
        failure_mode=spec["failure_mode"],
        benign=bool(spec.get("benign", False)),
        agents=[TaskAgentSpec(id=a["id"], prompt=a["prompt"]) for a in spec["agents"]],
        isolation=isolation,
        registry=dict(spec.get("registry") or {}),
    )


def list_tasks(tasks_dir: Path = TASKS_DIR) -> list[str]:
    return sorted(p.name for p in Path(tasks_dir).iterdir()
                  if (p / "task.yaml").is_file())
