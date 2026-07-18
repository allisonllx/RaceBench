"""Instrumented agent loop."""
from __future__ import annotations

from dataclasses import dataclass

from harness.events import EventLogger
from harness.models import ModelClient, ToolCall
from harness.registry import ToolRegistry
from harness.strategies.base import Mutation, Strategy
from harness.tools import FILE_TOOL_SCHEMAS
from harness.workspace import Workspace

SYSTEM_PROMPT_SHARED = """You are a coding agent working inside a shared repository. \
Other agents are working on OTHER subtasks in this same repository AT THE SAME \
TIME, so files may change between your reads. You cannot talk to them directly \
unless the environment exposes explicit coordination tools.

Rules:
- Use glob/grep to find files before editing when the repo has many modules.
- Read a file before editing it.
- Prefer edit_file (exact string replacement) over write_file for existing files: \
whole-file overwrites destroy other agents' concurrent work.
- If an edit fails or is refused because of another agent's activity, re-read the \
file and reapply your change on top of the current content.
- If list_tools / invoke_tool are available, use them for registered external tools; \
tools can appear or disappear mid-run — re-list if invoke fails.
- Irreversible tools (send_email, deploy, charge) cannot be undone — call them only \
when the required order is correct.
- Only make changes needed for YOUR subtask.
- Run the tests when you believe you are done, fix what your subtask broke, then \
call done with a one-line summary.

Your subtask:
{subtask}
"""

SYSTEM_PROMPT_WORKTREE = """You are a coding agent working in an isolated git \
worktree. Other agents edit SEPARATE worktrees; you will not see their changes \
until an automatic end-of-trial merge. You cannot talk to them directly unless \
the environment exposes explicit coordination tools.

Rules:
- Use glob/grep to find files before editing when the repo has many modules.
- Read a file before editing it.
- Prefer edit_file (exact string replacement) over write_file for existing files.
- If list_tools / invoke_tool are available, use them for registered external tools; \
tools can appear or disappear mid-run — re-list if invoke fails.
- Irreversible tools (send_email, deploy, charge) cannot be undone — call them only \
when the required order is correct.
- Only make changes needed for YOUR subtask; leave other agents' symbols alone.
- Run the tests when you believe you are done, fix what your subtask broke, then \
call done with a one-line summary.

Your subtask:
{subtask}
"""

# Back-compat alias
SYSTEM_PROMPT = SYSTEM_PROMPT_SHARED


@dataclass
class AgentResult:
    agent_id: str
    status: str
    turns: int
    prompt_tokens: int
    completion_tokens: int


class Agent:
    def __init__(self, agent_id: str, subtask: str, model: ModelClient,
                 strategy: Strategy, workspace: Workspace, logger: EventLogger,
                 max_turns: int = 40,
                 registry: ToolRegistry | None = None,
                 isolation: str = "shared"):
        self.id = agent_id
        self.model = model
        self.strategy = strategy
        self.ws = workspace
        self.log = logger
        self.max_turns = max_turns
        self.registry = registry
        prompt_tmpl = (SYSTEM_PROMPT_WORKTREE if isolation == "worktree"
                       else SYSTEM_PROMPT_SHARED)
        self.messages: list[dict] = [
            {"role": "system", "content": prompt_tmpl.format(subtask=subtask)},
            {"role": "user", "content": "Begin your subtask now."},
        ]
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def _tool_schemas(self) -> list[dict]:
        schemas = list(FILE_TOOL_SCHEMAS)
        schemas.extend(self.strategy.extra_tool_schemas())
        if self.registry is not None:
            schemas.extend(self.registry.openai_tool_schemas())
        return schemas

    async def run(self) -> AgentResult:
        status = "max_turns"
        turn = 0
        try:
            for turn in range(1, self.max_turns + 1):
                import asyncio
                await asyncio.sleep(0)

                for note in self.strategy.drain_notifications(self.id):
                    self.messages.append({"role": "user", "content": note})
                    self.log.log("notification_delivered", agent=self.id,
                                 turn=turn, note=note[:300])

                model_turn = await self.model.complete(
                    self.messages, self._tool_schemas())
                self.prompt_tokens += model_turn.prompt_tokens
                self.completion_tokens += model_turn.completion_tokens
                self.log.log("llm_usage", agent=self.id, turn=turn,
                             prompt_tokens=model_turn.prompt_tokens,
                             completion_tokens=model_turn.completion_tokens)

                if not model_turn.tool_calls:
                    self.messages.append({"role": "assistant",
                                          "content": model_turn.text or ""})
                    self.messages.append({"role": "user",
                                          "content": "Use a tool. Call done when finished."})
                    continue

                assistant_msg = {
                    "role": "assistant",
                    "content": model_turn.text or None,
                    "tool_calls": [
                        {"id": tc.call_id or f"call-{turn}-{i}",
                         "type": "function",
                         "function": {"name": tc.name,
                                      "arguments": _dump_args(tc.arguments)}}
                        for i, tc in enumerate(model_turn.tool_calls)
                    ],
                }
                self.messages.append(assistant_msg)

                finished = False
                for i, tc in enumerate(model_turn.tool_calls):
                    result, is_done = await self._dispatch(tc, turn)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.call_id or f"call-{turn}-{i}",
                        "content": result[:8000],
                    })
                    if is_done:
                        finished = True
                if finished:
                    status = "done"
                    break
        except Exception as exc:  # noqa: BLE001
            status = "error"
            self.log.log("agent_error", agent=self.id, error=repr(exc)[:500])
        finally:
            await self.strategy.agent_done(self.id)
            self.log.log("agent_done", agent=self.id, status=status, turns=turn,
                         prompt_tokens=self.prompt_tokens,
                         completion_tokens=self.completion_tokens)
        return AgentResult(self.id, status, turn, self.prompt_tokens,
                           self.completion_tokens)

    async def _dispatch(self, tc: ToolCall, turn: int) -> tuple[str, bool]:
        name, args = tc.name, tc.arguments
        self.log.log("tool_call", agent=self.id, turn=turn, tool=name,
                     args={k: (v[:200] if isinstance(v, str) else v)
                           for k, v in args.items()})
        if name == "list_files":
            files = self.ws.list_files(agent_id=self.id)
            return "\n".join(files), False
        if name == "glob":
            hits = self.ws.glob_files(args.get("pattern", "*"), agent_id=self.id)
            self.log.log("search", agent=self.id, kind="glob",
                         pattern=args.get("pattern", ""), n=len(hits))
            return "\n".join(hits) or "(no matches)", False
        if name == "grep":
            hits = self.ws.grep(args.get("pattern", ""), agent_id=self.id,
                                glob=args.get("glob") or "*")
            self.log.log("search", agent=self.id, kind="grep",
                         pattern=args.get("pattern", ""), n=len(hits))
            return "\n".join(hits) or "(no matches)", False
        if name == "read_file":
            content = await self.strategy.read(self.id, args.get("path", ""))
            if content is None:
                return f"ERROR: {args.get('path')} not found or not readable right now.", False
            return content, False
        if name == "edit_file":
            outcome = await self.strategy.write(
                self.id, args.get("path", ""),
                Mutation(kind="replace", old_string=args.get("old_string", ""),
                         new_string=args.get("new_string", "")))
            if outcome.ok and self.registry:
                self.registry.note_write()
            return _describe(outcome), False
        if name == "write_file":
            outcome = await self.strategy.write(
                self.id, args.get("path", ""),
                Mutation(kind="overwrite", content=args.get("content", "")))
            if outcome.ok and self.registry:
                self.registry.note_write()
            return _describe(outcome), False
        if name == "run_tests":
            result = await self.ws.run_pytest("tests", agent_id=self.id)
            self.log.log("run_tests", agent=self.id, passed=result.passed,
                         failed=result.failed, errored=result.errored)
            return result.output[-4000:] or "(no output)", False
        strategy_result = await self.strategy.handle_strategy_tool(
            self.id, name, args)
        if strategy_result is not None:
            return strategy_result[:8000], False
        if name == "list_tools":
            if not self.registry:
                return "ERROR: no tool registry on this task", False
            return "\n".join(self.registry.list_names()) or "(none)", False
        if name == "invoke_tool":
            if not self.registry:
                return "ERROR: no tool registry on this task", False
            return self.registry.invoke(
                self.id, args.get("name", ""),
                args.get("arguments") or {}), False
        if name in ("send_email", "deploy", "charge") and self.registry:
            return self.registry.invoke(self.id, name, args), False
        if name == "done":
            return "acknowledged", True
        return f"ERROR: unknown tool {name}", False


def _describe(outcome) -> str:
    if outcome.ok:
        note = " (auto-merged with a concurrent edit)" if outcome.status == "merged" else ""
        return f"OK: change applied{note}."
    return f"REFUSED ({outcome.status}): {outcome.message}"


def _dump_args(arguments: dict) -> str:
    import json
    return json.dumps(arguments, ensure_ascii=False)
