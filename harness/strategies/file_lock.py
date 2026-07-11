"""File-level locking: an agent acquires a file's lock on first touch (read or
write) and holds it until the agent finishes. Guarantees isolation per file at
the cost of blocking — including on benign overlaps (two agents editing
disjoint functions in one file), which is exactly the false-positive stall this
benchmark measures.

Lock waits are bounded by lock_timeout_s. On timeout the operation is refused
(status lock_timeout) and the agent is told to work on something else and retry
— a deliberate, logged livelock-avoidance choice rather than silent deadlock.
"""
from __future__ import annotations

import asyncio
import time

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register


@register
class FileLockStrategy(Strategy):
    name = "file_lock"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._owner: dict[str, str] = {}          # relpath -> agent_id
        self._released = asyncio.Condition()

    async def _acquire(self, agent_id: str, relpath: str) -> tuple[bool, float]:
        """Returns (acquired, seconds_waited)."""
        t0 = time.monotonic()
        logged_block = False
        async with self._released:
            while True:
                owner = self._owner.get(relpath)
                if owner is None or owner == agent_id or owner not in self.active:
                    self._owner[relpath] = agent_id
                    return True, time.monotonic() - t0
                waited = time.monotonic() - t0
                remaining = self.lock_timeout_s - waited
                if remaining <= 0:
                    return False, waited
                if not logged_block:
                    self.log.log("coord", strategy=self.name, action="blocked",
                                 agent=agent_id, path=relpath, holder=owner)
                    logged_block = True
                try:
                    await asyncio.wait_for(self._released.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return False, time.monotonic() - t0

    async def _release(self, agent_id: str) -> None:
        async with self._released:
            for path in [p for p, a in self._owner.items() if a == agent_id]:
                del self._owner[path]
            self._released.notify_all()

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if self.ws.exists(relpath, agent_id=agent_id):
            acquired, waited = await self._acquire(agent_id, relpath)
            if not acquired:
                self.log.log("coord", strategy=self.name, action="lock_timeout",
                             agent=agent_id, path=relpath, waited_s=round(waited, 3))
                return None
        if not self.ws.exists(relpath, agent_id=agent_id):
            return None
        return self.ws.read_file(relpath, agent_id=agent_id)

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        acquired, waited = await self._acquire(agent_id, relpath)
        if not acquired:
            return WriteOutcome(
                status="lock_timeout", waited_s=waited,
                message=f"file {relpath} is locked by another agent; "
                        "work on something else and retry later",
            )
        outcome = await self._apply_to_current(relpath, mutation, agent_id=agent_id)
        outcome.waited_s += waited
        return outcome
