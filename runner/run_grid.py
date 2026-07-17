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
from harness.models import AsyncRequestRateLimiter, OpenAIModel, ScriptedModel
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
    cfg.setdefault("provider", "openai")
    cfg.setdefault("request_rpm", None)
    cfg.setdefault("max_model_retries", 4)
    cfg.setdefault("model_retry_initial_s", 10.0)
    cfg.setdefault("model_retry_max_s", 120.0)
    cfg.setdefault("rerun_infra_errors", False)
    return cfg


def resolve_openai_provider(cfg: dict) -> dict:
    """Resolve credentials for OpenAI-compatible chat-completions providers."""
    provider = str(cfg.get("provider") or "openai")
    api_key_env = str(
        cfg.get("api_key_env")
        or ("OPENAI_API_KEY" if provider == "openai"
            else f"{provider.upper()}_API_KEY")
    )
    base_url_env = cfg.get("base_url_env")
    base_url = cfg.get("base_url")
    if not base_url and base_url_env:
        base_url = os.environ.get(str(base_url_env))
    return {
        "provider": provider,
        "api_key_env": api_key_env,
        "api_key": os.environ.get(api_key_env),
        "base_url": base_url,
        "base_url_env": base_url_env,
    }


def make_model_factory(cfg: dict, task_name: str):
    if cfg["mode"] == "scripted":
        variant = cfg["script_variant"]

        def factory(spec: TaskAgentSpec):
            return ScriptedModel(script=get_script(task_name, spec.id, variant))
        return factory

    provider = resolve_openai_provider(cfg)
    rate_limiter = cfg.get("_request_rate_limiter")
    if rate_limiter is None and cfg.get("request_rpm"):
        rate_limiter = AsyncRequestRateLimiter(float(cfg["request_rpm"]))
        cfg["_request_rate_limiter"] = rate_limiter

    def factory(spec: TaskAgentSpec):  # noqa: ARG001, one client config for all agents
        return OpenAIModel(
            model=cfg["model"],
            temperature=cfg.get("temperature"),
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            rate_limiter=rate_limiter,
            max_retries=int(cfg["max_model_retries"]),
            retry_initial_s=float(cfg["model_retry_initial_s"]),
            retry_max_s=float(cfg["model_retry_max_s"]),
        )
    return factory


def calibration_task(task):
    """Solo baseline: one agent gets every subtask. If a single agent cannot
    reach a high pass rate with no concurrency at all, the task is measuring
    model weakness, not coordination."""
    merged = "\n\n".join(
        f"Subtask {i + 1}: {a.prompt}" for i, a in enumerate(task.agents))
    task.agents = [TaskAgentSpec(id="solo", prompt=merged)]
    # min_agents gates multi-agent grid cells only; solo calibration is n=1.
    task.min_agents = 1
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


INFRA_ERROR_MARKERS = (
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "InternalServerError",
    "RateLimitError",
    "ServiceUnavailable",
    "code': 429",
    '"code": 429',
)


def should_rerun_existing_log(path: Path, cfg: dict) -> bool:
    """True for stale infrastructure-failure logs when config opts in."""
    if not cfg.get("rerun_infra_errors"):
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(marker in text for marker in INFRA_ERROR_MARKERS)


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
                elif n < task.min_agents or n > len(task.agents):
                    # Causal-cascade (and similar) tasks need the full agent
                    # chain; truncating drops later consumers and makes the
                    # oracle unreachable regardless of strategy.
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
    provider = resolve_openai_provider(cfg)

    if cfg["mode"] == "openai" and not provider["api_key"]:
        print(f"{provider['api_key_env']} is not set for provider "
              f"{provider['provider']}. Add it to .env at the repo root "
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
        provider=provider["provider"] if cfg["mode"] == "openai" else cfg["mode"],
        base_url=provider["base_url"] if cfg["mode"] == "openai" else None,
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
            if should_rerun_existing_log(job.log_path, cfg):
                job.log_path.unlink(missing_ok=True)
                to_run.append(job)
            else:
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
                if should_rerun_existing_log(job.log_path, cfg):
                    job.log_path.unlink(missing_ok=True)
                else:
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
