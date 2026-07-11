"""Run one trial: N agents, one task, one coordination strategy, one event log."""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from harness.agent import Agent
from harness.events import EventLogger
from harness.registry import ToolRegistry
from harness.strategies import get_strategy
from harness.task import Task
from harness.workspace import TestResult, Workspace


@dataclass
class TrialConfig:
    strategy: str
    n_agents: int
    rep: int = 0
    model_name: str = "scripted"
    max_turns: int = 40
    lock_timeout_s: float = 30.0
    trial_timeout_s: float = 900.0
    workdir: Path = Path(".trial_workspaces")

    @property
    def trial_id(self) -> str:
        return f"{self.strategy}-n{self.n_agents}-r{self.rep}"


@dataclass
class TrialResult:
    trial_id: str
    correct: bool
    oracle_passed: int
    oracle_total: int
    wall_clock_s: float
    prompt_tokens: int
    completion_tokens: int
    agent_statuses: dict[str, str]


async def merge_and_score(
    task: Task,
    ws: Workspace,
    logger: EventLogger,
) -> TestResult:
    """Merge worktrees if needed, copy hidden oracle tests, run pytest.

    Shared by the in-process Agent path and Level C external runtimes.
    """
    if task.isolation == "worktree":
        merge = ws.merge_agent_trees()
        logger.log("worktree_merge", ok=merge.ok, conflicts=merge.conflicts,
                   message=merge.message)

    oracle_dst = ws.root / "oracle_tests"
    if oracle_dst.exists():
        shutil.rmtree(oracle_dst)
    shutil.copytree(task.oracle_tests, oracle_dst)
    return await ws.run_pytest("oracle_tests")


def finish_trial(
    *,
    cfg: TrialConfig,
    logger: EventLogger,
    ws: Workspace,
    test_result: TestResult,
    wall: float,
    prompt_tokens: int,
    completion_tokens: int,
    agent_statuses: dict[str, str],
) -> TrialResult:
    """Log trial_end, cleanup workspace, return TrialResult."""
    result = TrialResult(
        trial_id=cfg.trial_id,
        correct=test_result.all_passed,
        oracle_passed=test_result.passed,
        oracle_total=test_result.total,
        wall_clock_s=wall,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        agent_statuses=agent_statuses,
    )
    logger.log("trial_end", correct=result.correct,
               oracle_passed=result.oracle_passed, oracle_total=result.oracle_total,
               wall_clock_s=round(wall, 2),
               prompt_tokens=result.prompt_tokens,
               completion_tokens=result.completion_tokens,
               agent_statuses=result.agent_statuses,
               oracle_output=test_result.output[-2000:])
    logger.close()
    if os.environ.get("RACEBENCH_KEEP_WORKSPACE") == "1":
        print(f"  kept workspace at {ws.root}", flush=True)
    else:
        ws.cleanup()
    return result


async def run_trial(task: Task, cfg: TrialConfig,
                    model_factory, log_path: Path) -> TrialResult:
    logger = EventLogger(log_path)
    ws_dir = Path(cfg.workdir) / f"{task.name}-{cfg.trial_id}"
    agents_specs = task.agent_subset(cfg.n_agents)
    agent_ids = [a.id for a in agents_specs]

    ws = Workspace.create(
        task.repo, ws_dir,
        isolation=task.isolation,
        agent_ids=agent_ids,
    )

    logger.log("trial_start", task=task.name, failure_mode=task.failure_mode,
               benign=task.benign, strategy=cfg.strategy, n_agents=cfg.n_agents,
               rep=cfg.rep, model=cfg.model_name, isolation=task.isolation,
               agent_ids=agent_ids)

    strategy = get_strategy(cfg.strategy)(
        ws, logger, agent_ids, lock_timeout_s=cfg.lock_timeout_s)

    registry = None
    if task.registry:
        registry = ToolRegistry(ws, logger, task.registry)

    agents = [
        Agent(spec.id, spec.prompt, model_factory(spec), strategy, ws, logger,
              max_turns=cfg.max_turns, registry=registry,
              isolation=task.isolation)
        for spec in agents_specs
    ]

    t0 = time.monotonic()
    timed_out = False
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(a.run() for a in agents)),
            timeout=cfg.trial_timeout_s,
        )
    except asyncio.TimeoutError:
        logger.log("trial_timeout")
        results = []
        timed_out = True
    wall = time.monotonic() - t0

    test_result = await merge_and_score(task, ws, logger)

    # On timeout, gather is cancelled so AgentResults are lost — recover
    # token counters from the still-alive Agent objects (updated each turn).
    if results:
        prompt_tokens = sum(r.prompt_tokens for r in results)
        completion_tokens = sum(r.completion_tokens for r in results)
        agent_statuses = {r.agent_id: r.status for r in results}
    else:
        prompt_tokens = sum(a.prompt_tokens for a in agents)
        completion_tokens = sum(a.completion_tokens for a in agents)
        agent_statuses = {
            a.id: ("timeout" if timed_out else "unknown") for a in agents
        }

    return finish_trial(
        cfg=cfg,
        logger=logger,
        ws=ws,
        test_result=test_result,
        wall=wall,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        agent_statuses=agent_statuses,
    )
