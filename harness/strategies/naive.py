"""Naive strategy: no coordination. Reads see whatever is on disk; writes land
immediately. Whole-file overwrites silently clobber concurrent work (lost
update); stale replace anchors surface as edit_failed. The floor every other
strategy is compared against."""
from __future__ import annotations

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register


@register
class NaiveStrategy(Strategy):
    name = "naive"

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        return self.ws.read_file(relpath) if self.ws.exists(relpath) else None

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        return await self._apply_to_current(relpath, mutation)
