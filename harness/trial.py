"""Run one trial: N agents, one task, one coordination strategy, one event log."""
from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from harness.agent import Agent
from harness.events import EventLogger
from harness.models import ModelClient
from harness.strategies import get_strategy
from harness.task import Task
from harness.workspace import Workspace


@dataclass
class TrialConfig:
    strategy: str
    n_agents: int
    rep: int = 0
    model_name: str = "scripted"
    max_turns: int = 20
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


async def run_trial(task: Task, cfg: TrialConfig,
                    model_factory, log_path: Path) -> TrialResult:
    """model_factory(agent_spec) -> ModelClient, so scripted mode can hand each
    agent its own script and API mode can share one client config."""
    logger = EventLogger(log_path)
    ws_dir = Path(cfg.workdir) / f"{task.name}-{cfg.trial_id}"
    ws = Workspace.create(task.repo, ws_dir)
    agents_specs = task.agent_subset(cfg.n_agents)

    logger.log("trial_start", task=task.name, failure_mode=task.failure_mode,
               benign=task.benign, strategy=cfg.strategy, n_agents=cfg.n_agents,
               rep=cfg.rep, model=cfg.model_name,
               agent_ids=[a.id for a in agents_specs])

    strategy = get_strategy(cfg.strategy)(
        ws, logger, [a.id for a in agents_specs], lock_timeout_s=cfg.lock_timeout_s)

    agents = [
        Agent(spec.id, spec.prompt, model_factory(spec), strategy, ws, logger,
              max_turns=cfg.max_turns)
        for spec in agents_specs
    ]

    t0 = time.monotonic()
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(a.run() for a in agents)),
            timeout=cfg.trial_timeout_s,
        )
    except asyncio.TimeoutError:
        logger.log("trial_timeout")
        results = []
    wall = time.monotonic() - t0

    # evaluate against the hidden oracle
    oracle_dst = ws.root / "oracle_tests"
    if oracle_dst.exists():
        shutil.rmtree(oracle_dst)
    shutil.copytree(task.oracle_tests, oracle_dst)
    test_result = await ws.run_pytest("oracle_tests")

    result = TrialResult(
        trial_id=cfg.trial_id,
        correct=test_result.all_passed,
        oracle_passed=test_result.passed,
        oracle_total=test_result.total,
        wall_clock_s=wall,
        prompt_tokens=sum(r.prompt_tokens for r in results),
        completion_tokens=sum(r.completion_tokens for r in results),
        agent_statuses={r.agent_id: r.status for r in results},
    )
    logger.log("trial_end", correct=result.correct,
               oracle_passed=result.oracle_passed, oracle_total=result.oracle_total,
               wall_clock_s=round(wall, 2),
               prompt_tokens=result.prompt_tokens,
               completion_tokens=result.completion_tokens,
               agent_statuses=result.agent_statuses,
               oracle_output=test_result.output[-2000:])
    logger.close()
    ws.cleanup()
    return result
