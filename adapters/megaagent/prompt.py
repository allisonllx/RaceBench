"""Build MegaAgent CEO prompts from a RaceBench instruction pack."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _strip_front_matter(md: str) -> str:
    """Keep the Subtask section body when present; else return full text."""
    m = re.search(r"##\s+Subtask\s*\n+(.*)", md, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return md.strip()


def load_agent_briefs(instruction_dir: Path) -> list[tuple[str, str]]:
    """Return [(agent_id, subtask_text), ...] sorted by id."""
    agents_dir = Path(instruction_dir) / "agents"
    if not agents_dir.is_dir():
        raise FileNotFoundError(f"missing agents dir: {agents_dir}")
    briefs: list[tuple[str, str]] = []
    for path in sorted(agents_dir.glob("*.md")):
        briefs.append((path.stem, _strip_front_matter(path.read_text(encoding="utf-8"))))
    if not briefs:
        raise ValueError(f"no agent briefs under {agents_dir}")
    return briefs


def build_prompts(
    instruction_dir: Path,
    *,
    ceo_name: str = "Bob",
) -> tuple[str, str]:
    """Return (initial_prompt, additional_prompt) for MegaAgent config override."""
    instruction_dir = Path(instruction_dir)
    task_meta: dict = {}
    task_json = instruction_dir / "task.json"
    if task_json.is_file():
        task_meta = json.loads(task_json.read_text(encoding="utf-8"))

    task_name = task_meta.get("name", "racebench_task")
    briefs = load_agent_briefs(instruction_dir)

    subtask_blocks = []
    for agent_id, text in briefs:
        subtask_blocks.append(
            f"### RaceBench agent `{agent_id}`\n{text}\n"
        )
    subtasks_blob = "\n".join(subtask_blocks)

    initial_prompt = f"""\
You are {ceo_name}, the leader of a software team working on an EXISTING codebase.
The project files are already present under the `files/` directory (RaceBench task
`{task_name}`). Do NOT start a greenfield app (no Gobang, no new unrelated project).

Your goal is to satisfy EVERY RaceBench subtask below by editing the existing
modules in place. You are recruiting employees and assigning work. For each
employee (including yourself), write a prompt. Specify name (one word, no prefix),
job, and what files/functions to change. Clarify collaborators' names and jobs.
The format must be:

<agent name="Alice">
...instructions...
</agent>

Every employee is lazy and will ignore anything not in their prompt. Work for each
employee should be non-divisible, concrete (which file to edit), and limited to
specific instructions. Cover the whole set of subtasks. Speed up by adding enough
employees to divide the work.

## RaceBench subtasks (ALL must be completed)

{subtasks_blob}
"""

    additional_prompt = f"""\
You are completing RaceBench task `{task_name}` by editing the EXISTING project
already in `files/`. Prefer modifying existing Python modules over creating a new
top-level application.

Hard rules:
- Do NOT create or modify `oracle_tests/` (the harness scores with a hidden copy).
- Do NOT delete the existing project structure just to rewrite everything.
- Implement every RaceBench subtask listed in your hiring brief.
- Leave a remarkable TODO in your TODO list (change_task_status) whenever work
  remains. Clear the TODO list and call `terminate` only when everything is done.
- You can only output function calls. Do NOT output anything else directly.
"""

    return initial_prompt, additional_prompt
