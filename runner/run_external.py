"""Run a single Level C external-runtime trial (no coordination strategy grid).

Examples:
  python -m runner.run_external --task t2_benign_overlap --adapter scripted
  python -m runner.run_external --task t2_benign_overlap --adapter shell \\
      --command 'python path/to/my_agent.py'
  python -m runner.run_external --task t2_benign_overlap --adapter megaagent \\
      --megaagent-root /path/to/MegaAgent
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from harness.external import external_strategy_id, run_external_trial
from harness.external_runtimes import get_runtime, list_runtimes
from harness.task import load_task
from harness.trial import TrialConfig


def main() -> None:
    p = argparse.ArgumentParser(description="RaceBench Level C external trial")
    p.add_argument("--task", required=True, help="task name under tasks/")
    p.add_argument(
        "--adapter",
        default="scripted",
        choices=list_runtimes(),
        help="external runtime name",
    )
    p.add_argument(
        "--command",
        default="",
        help="shell command (required when --adapter shell)",
    )
    p.add_argument(
        "--megaagent-root",
        type=Path,
        default=None,
        help="path to Xtra-Computing/MegaAgent clone (or set MEGAAGENT_ROOT)",
    )
    p.add_argument("--n-agents", type=int, default=2)
    p.add_argument("--rep", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path("results/ext-smoke"))
    p.add_argument("--workdir", type=Path, default=Path(".trial_workspaces"))
    p.add_argument("--timeout", type=float, default=900.0)
    args = p.parse_args()

    if args.adapter == "shell" and not args.command.strip():
        p.error("--command is required when --adapter shell")

    kwargs: dict = {}
    if args.adapter == "shell":
        kwargs["command"] = args.command
    if args.adapter == "megaagent" and args.megaagent_root is not None:
        kwargs["megaagent_root"] = args.megaagent_root
    runtime = get_runtime(args.adapter, **kwargs)

    task = load_task(args.task)
    strategy = external_strategy_id(runtime.name)
    cfg = TrialConfig(
        strategy=strategy,
        n_agents=args.n_agents,
        rep=args.rep,
        model_name=f"external:{runtime.name}",
        trial_timeout_s=args.timeout,
        workdir=args.workdir,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out / f"{task.name}__{cfg.trial_id}.jsonl"

    result = asyncio.run(run_external_trial(task, cfg, runtime, log_path))
    print(
        f"{task.name} adapter={runtime.name} correct={result.correct} "
        f"oracle={result.oracle_passed}/{result.oracle_total} "
        f"wall={result.wall_clock_s:.1f}s log={log_path}"
    )
    raise SystemExit(0 if result.correct else 1)


if __name__ == "__main__":
    main()
