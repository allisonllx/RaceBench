"""Level C: external runtime path (bring-your-own agent system).

RaceBench owns the workspace, instruction brief, oracle, and JSONL log.
An ExternalRuntime edits agent trees directly — no in-process Agent/Strategy
loop. Metrics honesty: correctness + wall clock are primary; stalls / read-set
/ tokens are N/A unless the adapter emits compatible events.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from harness.events import EventLogger
from harness.task import Task, TaskAgentSpec
from harness.trial import TrialConfig, TrialResult, finish_trial, merge_and_score
from harness.workspace import Workspace

RULES_BLURB = """\
# RaceBench external agent brief

Edit files under your assigned working tree only.
Do not create or modify `oracle_tests/` — the harness scores with a hidden copy.
When finished, exit successfully; the harness will merge (if worktree) and run the oracle.
"""


@dataclass
class ExternalOutcome:
    ok: bool
    agent_statuses: dict[str, str]
    message: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ExternalContext:
    task: Task
    workspace: Workspace
    agent_specs: list[TaskAgentSpec]
    instruction_dir: Path
    timeout_s: float
    log: EventLogger


class ExternalRuntime(Protocol):
    name: str

    async def run(self, ctx: ExternalContext) -> ExternalOutcome: ...


def write_instruction_pack(
    instruction_dir: Path,
    task: Task,
    ws: Workspace,
    agent_specs: list[TaskAgentSpec],
) -> None:
    """Write task.json, paths.json, and per-agent markdown briefs."""
    instruction_dir.mkdir(parents=True, exist_ok=True)
    agents_dir = instruction_dir / "agents"
    agents_dir.mkdir(exist_ok=True)

    agent_ids = [a.id for a in agent_specs]
    (instruction_dir / "task.json").write_text(
        json.dumps(
            {
                "name": task.name,
                "failure_mode": task.failure_mode,
                "benign": task.benign,
                "isolation": task.isolation,
                "agent_ids": agent_ids,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths = {
        "root": str(ws.root),
        "agents": {a.id: str(ws.agent_root(a.id)) for a in agent_specs},
    }
    (instruction_dir / "paths.json").write_text(
        json.dumps(paths, indent=2) + "\n", encoding="utf-8"
    )
    for spec in agent_specs:
        body = (
            f"{RULES_BLURB}\n"
            f"## Agent id\n\n`{spec.id}`\n\n"
            f"## Working tree\n\n`{ws.agent_root(spec.id)}`\n\n"
            f"## Subtask\n\n{spec.prompt.strip()}\n"
        )
        (agents_dir / f"{spec.id}.md").write_text(body, encoding="utf-8")


async def run_external_trial(
    task: Task,
    cfg: TrialConfig,
    runtime: ExternalRuntime,
    log_path: Path,
) -> TrialResult:
    """Workspace + instruction pack + external runtime + oracle."""
    logger = EventLogger(log_path)
    ws_dir = Path(cfg.workdir) / f"{task.name}-{cfg.trial_id}"
    agents_specs = task.agent_subset(cfg.n_agents)
    agent_ids = [a.id for a in agents_specs]

    ws = Workspace.create(
        task.repo, ws_dir,
        isolation=task.isolation,
        agent_ids=agent_ids,
    )
    instruction_dir = ws_dir / ".racebench_instructions"
    write_instruction_pack(instruction_dir, task, ws, agents_specs)

    logger.log(
        "trial_start",
        task=task.name,
        failure_mode=task.failure_mode,
        benign=task.benign,
        strategy=cfg.strategy,
        n_agents=cfg.n_agents,
        rep=cfg.rep,
        model=cfg.model_name,
        isolation=task.isolation,
        agent_ids=agent_ids,
        mode="external",
        adapter=runtime.name,
    )

    ctx = ExternalContext(
        task=task,
        workspace=ws,
        agent_specs=agents_specs,
        instruction_dir=instruction_dir,
        timeout_s=cfg.trial_timeout_s,
        log=logger,
    )

    t0 = time.monotonic()
    timed_out = False
    try:
        outcome = await asyncio.wait_for(
            runtime.run(ctx),
            timeout=cfg.trial_timeout_s,
        )
    except asyncio.TimeoutError:
        logger.log("trial_timeout")
        timed_out = True
        outcome = ExternalOutcome(
            ok=False,
            agent_statuses={aid: "timeout" for aid in agent_ids},
            message="external runtime timed out",
        )
    wall = time.monotonic() - t0

    logger.log(
        "external_end",
        adapter=runtime.name,
        ok=outcome.ok,
        message=outcome.message,
        timed_out=timed_out,
    )

    test_result = await merge_and_score(task, ws, logger)
    statuses = outcome.agent_statuses or {
        aid: ("timeout" if timed_out else "unknown") for aid in agent_ids
    }

    return finish_trial(
        cfg=cfg,
        logger=logger,
        ws=ws,
        test_result=test_result,
        wall=wall,
        prompt_tokens=outcome.prompt_tokens,
        completion_tokens=outcome.completion_tokens,
        agent_statuses=statuses,
    )


def external_strategy_id(adapter_name: str) -> str:
    """Synthetic strategy id for resume filenames / TrialConfig."""
    return f"ext_{adapter_name}"
