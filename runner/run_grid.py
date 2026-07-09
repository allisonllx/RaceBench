"""Grid orchestrator with cost guardrails and resume.

Usage:
    python -m runner.run_grid --config runner/config.smoke.yaml
    python -m runner.run_grid --config runner/config.example.yaml --calibrate

Every trial writes results/<run_id>/<task>__<strategy>-n<N>-r<rep>.jsonl.
Existing logs are skipped, so an interrupted (or budget-stopped) run resumes
by re-running the same command.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import yaml

from harness.models import OpenAIModel, ScriptedModel
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
    cfg.setdefault("max_turns", 20)
    cfg.setdefault("lock_timeout_s", 30)
    cfg.setdefault("trial_timeout_s", 900)
    cfg.setdefault("budget", {})
    cfg.setdefault("prices", {})
    return cfg


def estimate_usd(prices: dict, model: str, prompt_tokens: int,
                 completion_tokens: int) -> float:
    p = prices.get(model)
    if not p:
        return 0.0
    return (prompt_tokens * p.get("input", 0.0)
            + completion_tokens * p.get("output", 0.0)) / 1e6


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


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--calibrate", action="store_true",
                        help="run each task with ONE agent doing all subtasks "
                             "(naive strategy) to measure the solo ceiling")
    args = parser.parse_args()
    cfg = load_config(args.config)

    if cfg["mode"] == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Export it, or use a scripted config "
              "(runner/config.smoke.yaml) for an offline run.", file=sys.stderr)
        return 1

    run_id = cfg["run_id"] + ("-calibration" if args.calibrate else "")
    out_dir = RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    budget = cfg["budget"]
    spent_usd = 0.0
    spent_tokens = 0
    n_run = n_skipped = 0

    strategies = ["naive"] if args.calibrate else cfg["strategies"]
    agent_counts = [1] if args.calibrate else cfg["agent_counts"]

    for task_name in cfg["tasks"]:
        for strategy in strategies:
            for n in agent_counts:
                task = load_task(task_name)
                if args.calibrate:
                    task = calibration_task(task)
                elif n > len(task.agents):
                    continue  # task doesn't define enough agents for this cell
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
                    if log_path.exists():
                        n_skipped += 1
                        continue

                    if budget.get("max_usd") and spent_usd >= budget["max_usd"]:
                        print(f"BUDGET STOP: ${spent_usd:.2f} >= "
                              f"${budget['max_usd']}; resume later with the "
                              "same command", file=sys.stderr)
                        return 2
                    if (budget.get("max_total_tokens")
                            and spent_tokens >= budget["max_total_tokens"]):
                        print(f"BUDGET STOP: {spent_tokens} tokens; resume "
                              "later with the same command", file=sys.stderr)
                        return 2

                    print(f"[{task_name} | {strategy} | n={n} | rep={rep}] ...",
                          flush=True)
                    try:
                        result = await run_trial(
                            task, trial_cfg,
                            make_model_factory(cfg, task_name), log_path)
                    except KeyError as exc:  # scripted mode without a script
                        print(f"  skipped: {exc}", flush=True)
                        log_path.unlink(missing_ok=True)
                        continue
                    n_run += 1
                    spent_tokens += result.prompt_tokens + result.completion_tokens
                    spent_usd += estimate_usd(
                        cfg["prices"], cfg.get("model", ""),
                        result.prompt_tokens, result.completion_tokens)
                    print(f"  correct={result.correct} "
                          f"oracle={result.oracle_passed}/{result.oracle_total} "
                          f"wall={result.wall_clock_s:.1f}s "
                          f"tokens={result.prompt_tokens + result.completion_tokens} "
                          f"(cum ~${spent_usd:.2f})", flush=True)

    print(f"\ndone: {n_run} trials run, {n_skipped} skipped (already present); "
          f"~${spent_usd:.2f}, {spent_tokens} tokens. Results in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
