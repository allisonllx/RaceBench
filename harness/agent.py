"""Instrumented agent loop: model turn -> tool dispatch (through the
coordination strategy) -> tool result -> next turn. Every model call's token
usage and every tool outcome is written to the event log."""
from __future__ import annotations

from dataclasses import dataclass

from harness.events import EventLogger
from harness.models import ModelClient, ToolCall
from harness.strategies.base import Mutation, Strategy
from harness.tools import TOOL_SCHEMAS
from harness.workspace import Workspace

SYSTEM_PROMPT = """You are a coding agent working inside a shared repository. \
Other agents are working on OTHER subtasks in this same repository AT THE SAME \
TIME, so files may change between your reads. You cannot talk to them.

Rules:
- Read a file before editing it.
- Prefer edit_file (exact string replacement) over write_file for existing files: \
whole-file overwrites destroy other agents' concurrent work.
- If an edit fails or is refused because of another agent's activity, re-read the \
file and reapply your change on top of the current content.
- Only make changes needed for YOUR subtask.
- Run the tests when you believe you are done, fix what your subtask broke, then \
call done with a one-line summary.

Your subtask:
{subtask}
"""


@dataclass
class AgentResult:
    agent_id: str
    status: str  # done | max_turns | error
    turns: int
    prompt_tokens: int
    completion_tokens: int


class Agent:
    def __init__(self, agent_id: str, subtask: str, model: ModelClient,
                 strategy: Strategy, workspace: Workspace, logger: EventLogger,
                 max_turns: int = 20):
        self.id = agent_id
        self.model = model
        self.strategy = strategy
        self.ws = workspace
        self.log = logger
        self.max_turns = max_turns
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT.format(subtask=subtask)},
            {"role": "user", "content": "Begin your subtask now."},
        ]
        self.prompt_tokens = 0
        self.completion_tokens = 0

    async def run(self) -> AgentResult:
        status = "max_turns"
        turn = 0
        try:
            for turn in range(1, self.max_turns + 1):
                # yield to the event loop so concurrent agents interleave even
                # when the model client resolves without suspending (scripted mode)
                import asyncio
                await asyncio.sleep(0)

                # advisory strategies (notify) queue messages for injection
                for note in self.strategy.drain_notifications(self.id):
                    self.messages.append({"role": "user", "content": note})
                    self.log.log("notification_delivered", agent=self.id,
                                 turn=turn, note=note[:300])

                model_turn = await self.model.complete(self.messages, TOOL_SCHEMAS)
                self.prompt_tokens += model_turn.prompt_tokens
                self.completion_tokens += model_turn.completion_tokens
                self.log.log("llm_usage", agent=self.id, turn=turn,
                             prompt_tokens=model_turn.prompt_tokens,
                             completion_tokens=model_turn.completion_tokens)

                if not model_turn.tool_calls:
                    # nudge a text-only reply back into tool use
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
        except Exception as exc:  # noqa: BLE001 — a crashed agent is a trial datum
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
            return "\n".join(self.ws.list_files()), False
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
            return _describe(outcome), False
        if name == "write_file":
            outcome = await self.strategy.write(
                self.id, args.get("path", ""),
                Mutation(kind="overwrite", content=args.get("content", "")))
            return _describe(outcome), False
        if name == "run_tests":
            result = await self.ws.run_pytest("tests")
            self.log.log("run_tests", agent=self.id, passed=result.passed,
                         failed=result.failed, errored=result.errored)
            return result.output[-4000:] or "(no output)", False
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
