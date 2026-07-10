"""Coordination-strategy interface.

A strategy is the ONLY path between an agent and the shared workspace. Every
read and write flows through it, so the event log has (by construction) 100%
read-set visibility — one of the benchmark's reported metrics.

Mutations are either whole-file overwrites/creates or anchored string
replacements. Replacements are applied against the CURRENT file content at
apply time (under the strategy's internal serialization), so concurrent edits
to disjoint regions of one file compose; a stale anchor that no longer matches
surfaces as `edit_failed` — which is exactly the wasted-work signal we want to
measure rather than hide.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from harness.events import EventLogger
from harness.symbols import changed_symbols
from harness.workspace import Workspace

# strategy modules self-register here via @register at import time


@dataclass
class Mutation:
    kind: Literal["overwrite", "replace"]
    content: str = ""       # overwrite: full new content
    old_string: str = ""    # replace
    new_string: str = ""    # replace

    def apply(self, base: str | None) -> str | None:
        """Return the new file content, or None if the mutation cannot apply."""
        if self.kind == "overwrite":
            return self.content
        if base is None:
            return None
        if self.old_string not in base:
            return None
        return base.replace(self.old_string, self.new_string, 1)


@dataclass
class WriteOutcome:
    status: Literal["applied", "merged", "conflict", "edit_failed", "lock_timeout"]
    message: str = ""
    waited_s: float = 0.0
    changed: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return self.status in ("applied", "merged")


class Strategy(ABC):
    """One instance per trial, shared by all agents in that trial."""

    name: str = "base"

    def __init__(self, workspace: Workspace, logger: EventLogger, agent_ids: list[str],
                 lock_timeout_s: float = 30.0):
        self.ws = workspace
        self.log = logger
        self.agent_ids = list(agent_ids)
        self.active = set(agent_ids)
        self.lock_timeout_s = lock_timeout_s
        # serializes the read-modify-write of a single apply; NOT a coordination
        # mechanism, just atomicity of individual file operations
        self._apply_lock = asyncio.Lock()

    # ---- agent-facing API -------------------------------------------------

    async def read(self, agent_id: str, relpath: str) -> str | None:
        content = await self._coordinate_read(agent_id, relpath)
        self.log.log("read", agent=agent_id, path=relpath,
                     found=content is not None,
                     size=len(content) if content is not None else 0)
        return content

    async def write(self, agent_id: str, relpath: str, mutation: Mutation) -> WriteOutcome:
        outcome = await self._coordinate_write(agent_id, relpath, mutation)
        self.log.log("write", agent=agent_id, path=relpath, kind=mutation.kind,
                     status=outcome.status, waited_s=round(outcome.waited_s, 3),
                     changed_symbols=sorted(outcome.changed), message=outcome.message[:500])
        return outcome

    async def agent_done(self, agent_id: str) -> None:
        self.active.discard(agent_id)
        await self._release(agent_id)
        self.log.log("agent_done_coord", agent=agent_id)

    # ---- strategy internals ----------------------------------------------

    @abstractmethod
    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None: ...

    @abstractmethod
    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome: ...

    async def _release(self, agent_id: str) -> None:
        """Release any claims held by a finished agent."""

    def drain_notifications(self, agent_id: str) -> list[str]:
        """Messages the strategy wants injected into the agent's context before
        its next model call. Only notification-based strategies use this."""
        return []

    # ---- shared helper ----------------------------------------------------

    async def _apply_to_current(self, relpath: str, mutation: Mutation) -> WriteOutcome:
        """Apply a mutation against current disk content (atomic, uncoordinated)."""
        async with self._apply_lock:
            base = self.ws.read_file(relpath) if self.ws.exists(relpath) else None
            new = mutation.apply(base)
            if new is None:
                return WriteOutcome(
                    status="edit_failed",
                    message="old_string not found in current file content "
                            "(the file may have changed since you read it — re-read it)",
                )
            self.ws.write_file(relpath, new)
            return WriteOutcome(status="applied",
                                changed=changed_symbols(base or "", new))


STRATEGIES: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    STRATEGIES[cls.name] = cls
    return cls


def get_strategy(name: str) -> type[Strategy]:
    if name not in STRATEGIES:
        raise KeyError(f"unknown strategy {name!r}; available: {sorted(STRATEGIES)}")
    return STRATEGIES[name]
