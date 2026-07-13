"""Run a single Level C external-runtime trial (no coordination strategy grid).

Resume: if the output JSONL already contains a ``trial_end`` event, the trial
is treated as done and not re-run. Incomplete logs (file exists but no
``trial_end``) are replaced.

Examples:
  python -m runner.run_external --task t02_benign_overlap --adapter scripted
  python -m runner.run_external --task t02_benign_overlap --adapter shell \\
      --command 'python path/to/my_agent.py'
  python -m runner.run_external --task t02_benign_overlap --adapter megaagent \\
      --megaagent-root /path/to/MegaAgent
  python -m runner.run_external --task t02_benign_overlap --adapter cursor
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from harness.events import has_trial_end, read_trial_end
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
    p.add_argument(
        "--cursor-model",
        default="composer-2.5",
        help="Cursor SDK model id for --adapter cursor (default: composer-2.5)",
    )
    p.add_argument(
        "--n-agents",
        type=int,
        default=None,
        help="agent count (default: all agents defined in task.yaml)",
    )
    p.add_argument("--rep", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path("results/ext-smoke"))
    p.add_argument("--workdir", type=Path, default=Path(".trial_workspaces"))
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument(
        "--force",
        action="store_true",
        help="re-run even if the output log already has trial_end",
    )
    args = p.parse_args()

    if args.adapter == "shell" and not args.command.strip():
        p.error("--command is required when --adapter shell")

    kwargs: dict = {}
    if args.adapter == "shell":
        kwargs["command"] = args.command
    if args.adapter == "megaagent" and args.megaagent_root is not None:
        kwargs["megaagent_root"] = args.megaagent_root
    if args.adapter == "cursor":
        kwargs["model"] = args.cursor_model
    runtime = get_runtime(args.adapter, **kwargs)

    task = load_task(args.task)
    n_agents = args.n_agents if args.n_agents is not None else len(task.agents)
    if n_agents < task.min_agents:
        p.error(
            f"task {task.name} requires at least {task.min_agents} agents "
            f"(got --n-agents {n_agents}; omit flag to use all {len(task.agents)})"
        )
    if n_agents > len(task.agents):
        p.error(
            f"task {task.name} defines {len(task.agents)} agents, "
            f"requested {n_agents}"
        )

    strategy = external_strategy_id(runtime.name)
    cfg = TrialConfig(
        strategy=strategy,
        n_agents=n_agents,
        rep=args.rep,
        model_name=f"external:{runtime.name}",
        trial_timeout_s=args.timeout,
        workdir=args.workdir,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out / f"{task.name}__{cfg.trial_id}.jsonl"

    if not args.force and has_trial_end(log_path):
        end = read_trial_end(log_path) or {}
        correct = bool(end.get("correct"))
        print(
            f"{task.name} adapter={runtime.name} skipped (trial_end present) "
            f"correct={correct} "
            f"oracle={end.get('oracle_passed', '?')}/{end.get('oracle_total', '?')} "
            f"log={log_path}"
        )
        raise SystemExit(0 if correct else 1)

    # Incomplete prior attempt: replace so EventLogger does not append.
    if log_path.exists():
        log_path.unlink()

    result = asyncio.run(run_external_trial(task, cfg, runtime, log_path))
    print(
        f"{task.name} adapter={runtime.name} correct={result.correct} "
        f"oracle={result.oracle_passed}/{result.oracle_total} "
        f"wall={result.wall_clock_s:.1f}s log={log_path}"
    )
    raise SystemExit(0 if result.correct else 1)


if __name__ == "__main__":
    main()
