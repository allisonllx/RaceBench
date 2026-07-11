"""Grid orchestrator with cost guardrails and resume.

Usage:
    python -m runner.run_grid --config runner/config.smoke.yaml
    python -m runner.run_grid --config runner/config.example.yaml --calibrate
    python -m runner.run_grid --config runner/config.example.yaml --parallel 4

Every trial writes results/<run_id>/<task>__<strategy>-n<N>-r<rep>.jsonl.
Existing logs are skipped, so an interrupted (or budget-stopped) run resumes
by re-running the same command.

Set `parallel:` in the config (or `--parallel N`) to run up to N trials at once.
Agents within a trial already run concurrently; this parallelizes across trials.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from harness.env import ENV_FILE, load_env
from harness.models import OpenAIModel, ScriptedModel
from harness.pricing import DEFAULT_PRICES, estimate_usd, write_run_meta
from harness.scripts import get_script
from harness.task import TaskAgentSpec, load_task
from harness.trial import TrialConfig, run_trial

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cfg.setdefault("mode", "openai")
    cfg.setdefault("script_variant", "edit")
    cfg.setdefault("agent_counts", [2])
    cfg.setdefault("reps", 1)
    cfg.setdefault("max_turns", 40)
    cfg.setdefault("lock_timeout_s", 30)
    cfg.setdefault("trial_timeout_s", 900)
    cfg.setdefault("parallel", 1)
    cfg.setdefault("budget", {})
    cfg.setdefault("prices", {})
    return cfg


def make_model_factory(cfg: dict, task_name: str):
    if cfg["mode"] == "scripted":
        variant = cfg["script_variant"]

        def factory(spec: TaskAgentSpec):
            return ScriptedModel(script=get_script(task_name, spec.id, variant))
        return factory

    def factory(spec: TaskAgentSpec):  # noqa: ARG001 — one client config for all agents
        return OpenAIModel(model=cfg["model"])
    return factory


def calibration_task(task):
    """Solo baseline: one agent gets every subtask. If a single agent cannot
    reach a high pass rate with no concurrency at all, the task is measuring
    model weakness, not coordination."""
    merged = "\n\n".join(
        f"Subtask {i + 1}: {a.prompt}" for i, a in enumerate(task.agents))
    task.agents = [TaskAgentSpec(id="solo", prompt=merged)]
    return task


@dataclass
class PendingTrial:
    task_name: str
    strategy: str
    n: int
    rep: int
    trial_cfg: TrialConfig
    log_path: Path


@dataclass
class GridState:
    spent_usd: float = 0.0
    spent_tokens: int = 0
    n_run: int = 0
    n_skipped: int = 0
    n_script_skip: int = 0
    budget_stop: bool = False


def collect_pending(cfg: dict, out_dir: Path, calibrate: bool) -> list[PendingTrial]:
    strategies = ["naive"] if calibrate else cfg["strategies"]
    agent_counts = [1] if calibrate else cfg["agent_counts"]
    pending: list[PendingTrial] = []
    for task_name in cfg["tasks"]:
        for strategy in strategies:
            for n in agent_counts:
                task = load_task(task_name)
                if calibrate:
                    task = calibration_task(task)
                elif n > len(task.agents):
                    continue
                for rep in range(cfg["reps"]):
                    trial_cfg = TrialConfig(
                        strategy=strategy, n_agents=n, rep=rep,
                        model_name=(cfg.get("model", "scripted")
                                    if cfg["mode"] == "openai"
                                    else f"scripted-{cfg['script_variant']}"),
                        max_turns=cfg["max_turns"],
                        lock_timeout_s=cfg["lock_timeout_s"],
                        trial_timeout_s=cfg["trial_timeout_s"],
                    )
                    log_path = out_dir / f"{task_name}__{trial_cfg.trial_id}.jsonl"
                    pending.append(PendingTrial(
                        task_name=task_name, strategy=strategy, n=n, rep=rep,
                        trial_cfg=trial_cfg, log_path=log_path,
                    ))
    return pending


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--calibrate", action="store_true",
                        help="run each task with ONE agent doing all subtasks "
                             "(naive strategy) to measure the solo ceiling")
    parser.add_argument("--parallel", type=int, default=None,
                        help="max concurrent trials (overrides config parallel:)")
    args = parser.parse_args()
    load_env()
    cfg = load_config(args.config)

    if cfg["mode"] == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Add it to .env at the repo root "
              f"({ENV_FILE}) or export it in your shell. For an offline run, "
              "use runner/config.smoke.yaml.", file=sys.stderr)
        return 1

    parallel = max(1, args.parallel if args.parallel is not None else int(cfg["parallel"]))
    run_id = cfg["run_id"] + ("-calibration" if args.calibrate else "")
    out_dir = RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    prices = {**DEFAULT_PRICES, **(cfg.get("prices") or {})}
    write_run_meta(
        out_dir,
        run_id=run_id,
        model=cfg.get("model", "scripted"),
        mode=cfg["mode"],
        prices=prices,
        budget=cfg.get("budget"),
    )

    budget = cfg["budget"]
    state = GridState()
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(parallel)

    pending = collect_pending(cfg, out_dir, args.calibrate)
    to_run: list[PendingTrial] = []
    for job in pending:
        if job.log_path.exists():
            state.n_skipped += 1
        else:
            to_run.append(job)

    if parallel > 1:
        print(f"parallel={parallel} ({len(to_run)} pending, "
              f"{state.n_skipped} already present)", flush=True)

    async def run_one(job: PendingTrial) -> None:
        async with sem:
            async with lock:
                if state.budget_stop:
                    return
                if budget.get("max_usd") and state.spent_usd >= budget["max_usd"]:
                    state.budget_stop = True
                    print(f"BUDGET STOP: ${state.spent_usd:.2f} >= "
                          f"${budget['max_usd']}; resume later with the "
                          "same command", file=sys.stderr)
                    return
                if (budget.get("max_total_tokens")
                        and state.spent_tokens >= budget["max_total_tokens"]):
                    state.budget_stop = True
                    print(f"BUDGET STOP: {state.spent_tokens} tokens; resume "
                          "later with the same command", file=sys.stderr)
                    return

            # Re-check after waiting on the semaphore (another worker may have
            # written the same path in a weird resume race; normally unique).
            if job.log_path.exists():
                async with lock:
                    state.n_skipped += 1
                return

            label = (f"[{job.task_name} | {job.strategy} | "
                     f"n={job.n} | rep={job.rep}]")
            print(f"{label} ...", flush=True)
            task = load_task(job.task_name)
            if args.calibrate:
                task = calibration_task(task)
            try:
                result = await run_trial(
                    task, job.trial_cfg,
                    make_model_factory(cfg, job.task_name), job.log_path)
            except KeyError as exc:  # scripted mode without a script
                print(f"  {label} skipped: {exc}", flush=True)
                job.log_path.unlink(missing_ok=True)
                async with lock:
                    state.n_script_skip += 1
                return

            cost = estimate_usd(
                prices, cfg.get("model", ""),
                result.prompt_tokens, result.completion_tokens)
            async with lock:
                state.n_run += 1
                state.spent_tokens += (
                    result.prompt_tokens + result.completion_tokens)
                state.spent_usd += cost
                cum = state.spent_usd
            print(f"  {label} correct={result.correct} "
                  f"oracle={result.oracle_passed}/{result.oracle_total} "
                  f"wall={result.wall_clock_s:.1f}s "
                  f"tokens={result.prompt_tokens + result.completion_tokens} "
                  f"(cum ~${cum:.2f})", flush=True)

    await asyncio.gather(*(run_one(job) for job in to_run))

    print(f"\ndone: {state.n_run} trials run, {state.n_skipped} skipped "
          f"(already present); ~${state.spent_usd:.2f}, {state.spent_tokens} "
          f"tokens. Results in {out_dir}")
    return 2 if state.budget_stop else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
