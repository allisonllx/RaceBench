"""Subprocess entry: run upstream MegaAgent against a RaceBench-seeded files/.

Requires env:
  RACEBENCH_ROOT, RACEBENCH_INSTRUCTION_DIR, MEGAAGENT_ROOT

Does not permanently patch the MegaAgent checkout; overrides config in-process.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# RaceBench repo root (adapters/megaagent/ -> ../../)
_RACEBENCH_REPO = Path(__file__).resolve().parents[2]
if str(_RACEBENCH_REPO) not in sys.path:
    sys.path.insert(0, str(_RACEBENCH_REPO))

from adapters.megaagent.prompt import build_prompts  # noqa: E402
from adapters.megaagent.sync import collect_files, seed_files  # noqa: E402


def _require_env(name: str) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        raise SystemExit(f"missing required env {name}")
    path = Path(raw).resolve()
    if not path.exists():
        raise SystemExit(f"{name} does not exist: {path}")
    return path


def _init_logger() -> None:
    logger = logging.getLogger()
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s: %(message)s")
    f_handler = logging.FileHandler("log.txt")
    f_handler.setFormatter(formatter)
    logger.addHandler(f_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)


def _ensure_dirs() -> None:
    Path("files").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)


def main() -> int:
    racebench_root = _require_env("RACEBENCH_ROOT")
    instruction_dir = _require_env("RACEBENCH_INSTRUCTION_DIR")
    megaagent_root = _require_env("MEGAAGENT_ROOT")

    if not (megaagent_root / "main.py").is_file():
        raise SystemExit(
            f"MEGAAGENT_ROOT={megaagent_root} does not look like MegaAgent "
            "(missing main.py)"
        )

    initial_prompt, additional_prompt = build_prompts(instruction_dir)

    # Run entirely from the MegaAgent checkout so their relative paths work.
    os.chdir(megaagent_root)
    if str(megaagent_root) not in sys.path:
        sys.path.insert(0, str(megaagent_root))

    import config  # type: ignore  # noqa: E402
    from agent import Agent, agent_dict  # type: ignore  # noqa: E402
    from llm import get_llm_response, input_token, output_token  # type: ignore  # noqa: E402
    from utils import (  # type: ignore  # noqa: E402
        delete_all_files_in_folder,
        git_commit,
        git_lock,
    )

    config.initial_prompt = initial_prompt
    config.additional_prompt = additional_prompt

    files_dir = megaagent_root / "files"
    exit_code = 1
    try:
        _ensure_dirs()
        delete_all_files_in_folder("logs")
        delete_all_files_in_folder("files")
        n_seed = seed_files(racebench_root, files_dir)
        # Upstream git_commit only commits already-tracked paths; stage seed.
        subprocess.run(
            ["git", "-C", "files", "add", "-A"],
            check=False,
            capture_output=True,
            text=True,
        )
        git_commit("RaceBench seed")
        if Path("log.txt").exists():
            Path("log.txt").unlink()
        _init_logger()
        logging.info("RaceBench MegaAgent bridge: seeded %s files", n_seed)

        begin_time = time.time()
        meta_output = get_llm_response(
            [{"role": "system", "content": config.initial_prompt}], False
        )["choices"][0]["message"]["content"]
        logging.info(meta_output)

        agent_pattern = re.compile(r'<agent name="(\w+)">(.*?)</agent>', re.DOTALL)
        agents = agent_pattern.findall(meta_output)
        if not agents:
            logging.error("CEO response contained no <agent name=...> blocks")
            return 1

        for agent in agents:
            if agent[0] == config.ceo_name:
                agent_dict[agent[0]] = Agent(agent[0], agent[1])

        if config.ceo_name not in agent_dict:
            logging.error("CEO %s missing from recruited agents", config.ceo_name)
            return 1

        for agent in agents:
            if agent[0] != config.ceo_name:
                agent_dict[config.ceo_name].add_subordinate(agent[0], "", agent[1])

        agent_dict[config.ceo_name].enqueue(
            "user",
            "Now let's start the project. Please split the task and talk to "
            "your subordinates to assign the tasks. Remember the codebase "
            "already exists under files/ — edit it to satisfy every RaceBench "
            "subtask.",
        )

        while True:
            time.sleep(1)
            if not agent_dict:
                logging.error("agent_dict empty")
                return 1
            if all(agent.state == "idle" for agent in agent_dict.values()):
                ok = True
                for agent in agent_dict.values():
                    try:
                        with git_lock:
                            with open(f"files/todo_{agent.name}.txt", "r") as f:
                                content = f.read()
                    except FileNotFoundError:
                        content = ""
                    if content != "":
                        agent.enqueue(
                            "system",
                            "Other agents have terminated. However, you still "
                            "have unfinished tasks in your TODO list. Please "
                            "finish them and clear it. If you are waiting for "
                            "someone, chances are that they have forgotten "
                            "about you. Please remind them.",
                        )
                        ok = False
                if not ok:
                    continue
                agent_dict[config.ceo_name].enqueue(
                    "system",
                    "All the agents have terminated. Please use read_file to "
                    "browse and proofread all the output files. Be sure to "
                    "test them if needed, and check whether every RaceBench "
                    "subtask is done (do not leave placeholders!). If complete "
                    "with 100% accuracy, call terminate; else assign remaining "
                    "tasks.",
                )
                while agent_dict[config.ceo_name].state != "idle":
                    time.sleep(1)
                if all(agent.state == "idle" for agent in agent_dict.values()):
                    break

        end_time = time.time()
        logging.info("Time elapsed: %s seconds", end_time - begin_time)
        logging.info(
            "Input tokens: %s, output tokens: %s", input_token, output_token
        )
        logging.info("Number of agents: %s", len(agent_dict))
        exit_code = 0
    except Exception:
        logging.exception("MegaAgent bridge failed")
        exit_code = 1
    finally:
        try:
            n_back = collect_files(files_dir, racebench_root)
            print(f"collected {n_back} files back to {racebench_root}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"collect_files failed: {exc}", flush=True)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
