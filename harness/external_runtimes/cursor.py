"""Cursor SDK Level C1 runtime — one local Agent.prompt per RaceBench brief.

C1 (harness-swap): fixed roles and briefs from `.racebench_instructions/`.
This measures Cursor *worker* loops under a known split, not Cursor multitask /
product orchestration. On shared isolation all agents share one cwd (unmediated
concurrent writers). On worktree tasks each agent gets its own cwd from
paths.json; the harness merges before the oracle.

Requires CURSOR_API_KEY and: pip install -e '.[cursor]'
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.external import ExternalContext, ExternalOutcome

INSTALL_HINT = "pip install -e '.[cursor]'"


def missing_cursor_deps() -> list[str]:
    missing: list[str] = []
    try:
        import cursor_sdk  # noqa: F401
    except ImportError:
        missing.append("cursor-sdk")
    return missing


def _load_paths(instruction_dir: Path) -> dict[str, Any]:
    raw = (instruction_dir / "paths.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _agent_brief(instruction_dir: Path, agent_id: str) -> str:
    path = instruction_dir / "agents" / f"{agent_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"missing agent brief: {path}")
    return path.read_text(encoding="utf-8")


def _usage_tokens(result: Any) -> tuple[int, int]:
    """Extract (input, output) tokens from RunResult.usage if present."""
    usage = getattr(result, "usage", None)
    if usage is None:
        return 0, 0
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    return inp, out


def _run_one_agent(
    *,
    agent_id: str,
    prompt: str,
    cwd: str,
    api_key: str,
    model: str,
) -> tuple[str, str, str, int, int]:
    """Sync SDK call. Returns (agent_id, status, message, prompt_tokens, completion_tokens)."""
    from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=cwd),
            ),
        )
    except CursorAgentError as err:
        return (
            agent_id,
            "error",
            f"startup failed: {getattr(err, 'message', str(err))}",
            0,
            0,
        )
    except Exception as err:  # noqa: BLE001 — surface SDK surprises to the harness
        return agent_id, "error", f"{type(err).__name__}: {err}", 0, 0

    prompt_tok, completion_tok = _usage_tokens(result)
    status = getattr(result, "status", None)
    if status is None:
        status = "finished" if result else "error"
    status_s = str(status).lower()
    if status_s in {"finished", "done", "completed", "success"}:
        return agent_id, "done", "", prompt_tok, completion_tok
    if status_s in {"error", "failed"}:
        return agent_id, "error", f"run status={status_s}", prompt_tok, completion_tok
    if status_s in {"cancelled", "canceled", "timeout"}:
        return (
            agent_id,
            "timeout",
            f"run status={status_s}",
            prompt_tok,
            completion_tok,
        )
    return (
        agent_id,
        "error",
        f"unexpected status={status_s!r}",
        prompt_tok,
        completion_tok,
    )


@dataclass
class CursorExternalRuntime:
    """Level C1: parallel Cursor local agents on fixed RaceBench briefs."""

    name: str = "cursor"
    model: str = "composer-2.5"

    async def run(self, ctx: ExternalContext) -> ExternalOutcome:
        missing = missing_cursor_deps()
        if missing:
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=(
                    "Cursor C1 adapter missing packages: "
                    + ", ".join(missing)
                    + f". Install with: {INSTALL_HINT}"
                ),
            )

        api_key = os.environ.get("CURSOR_API_KEY", "").strip()
        if not api_key:
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=(
                    "CURSOR_API_KEY not set. Export a Cursor user or service-account "
                    "API key, then retry. See docs/adding-an-external-runtime.md."
                ),
            )

        try:
            paths = _load_paths(ctx.instruction_dir)
            agent_paths = paths.get("agents") or {}
        except Exception as err:  # noqa: BLE001
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=f"failed to read paths.json: {err}",
            )

        jobs: list[tuple[str, str, str]] = []
        for spec in ctx.agent_specs:
            cwd = agent_paths.get(spec.id)
            if not cwd:
                return ExternalOutcome(
                    ok=False,
                    agent_statuses={s.id: "error" for s in ctx.agent_specs},
                    message=f"paths.json missing agents.{spec.id}",
                )
            try:
                prompt = _agent_brief(ctx.instruction_dir, spec.id)
            except FileNotFoundError as err:
                return ExternalOutcome(
                    ok=False,
                    agent_statuses={s.id: "error" for s in ctx.agent_specs},
                    message=str(err),
                )
            jobs.append((spec.id, prompt, str(cwd)))

        ctx.log.log(
            "external_cursor_start",
            model=self.model,
            n_agents=len(jobs),
            isolation=ctx.task.isolation,
            agent_ids=[j[0] for j in jobs],
        )

        async def _one(
            agent_id: str, prompt: str, cwd: str
        ) -> tuple[str, str, str, int, int]:
            return await asyncio.to_thread(
                _run_one_agent,
                agent_id=agent_id,
                prompt=prompt,
                cwd=cwd,
                api_key=api_key,
                model=self.model,
            )

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[_one(aid, prompt, cwd) for aid, prompt, cwd in jobs],
                    return_exceptions=True,
                ),
                timeout=ctx.timeout_s,
            )
        except asyncio.TimeoutError:
            ctx.log.log("external_cursor_timeout", timeout_s=ctx.timeout_s)
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "timeout" for s in ctx.agent_specs},
                message="cursor C1 agents timed out",
            )

        statuses: dict[str, str] = {}
        messages: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0
        for item, (aid, _, _) in zip(results, jobs, strict=True):
            if isinstance(item, BaseException):
                statuses[aid] = "error"
                messages.append(f"{aid}: {type(item).__name__}: {item}")
                continue
            agent_id, status, msg, ptok, ctok = item
            statuses[agent_id] = status
            prompt_tokens += int(ptok or 0)
            completion_tokens += int(ctok or 0)
            if msg:
                messages.append(f"{agent_id}: {msg}")

        for spec in ctx.agent_specs:
            statuses.setdefault(spec.id, "error")

        ok = all(statuses.get(s.id) == "done" for s in ctx.agent_specs)
        ctx.log.log(
            "external_cursor_end",
            ok=ok,
            agent_statuses=statuses,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            message="; ".join(messages)[:1000],
        )
        return ExternalOutcome(
            ok=ok,
            agent_statuses=statuses,
            message="; ".join(messages) if messages else ("ok" if ok else "agent errors"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
