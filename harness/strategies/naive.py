"""Naive strategy: no coordination. Reads see whatever is on disk; writes land
immediately."""
from __future__ import annotations

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register


@register
class NaiveStrategy(Strategy):
    name = "naive"

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath, agent_id=agent_id):
            return None
        return self.ws.read_file(relpath, agent_id=agent_id)

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        return await self._apply_to_current(relpath, mutation, agent_id=agent_id)
