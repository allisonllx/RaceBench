"""CoAgent-style advisory notifications (arXiv:2606.15376), minimal variant.

Writes are never blocked — they land immediately, exactly like naive. But the
runtime watches read-write intersections: when an applied write changes a
symbol that another ACTIVE agent has already read, that reader gets a
notification injected into its context before its next model turn, and the
reader's own LLM judges whether the change invalidates its plan (CoAgent's
"self-healing" assumption A3).

This is deliberately CoAgent-LITE: no serialization pre-order, no saga
inverses, no mechanical reordering — just the notify-and-let-the-LLM-judge
core. The cost profile it exposes is the interesting part: every notification
consumes reader tokens whether or not the change mattered, and on a benign
overlap ALL of them are unnecessary (the reader read the whole file, so its
read set contains the other agent's function too).
"""
from __future__ import annotations

from collections import defaultdict

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register
from harness.symbols import file_symbols


@register
class NotifyStrategy(Strategy):
    name = "notify"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._read_sets: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self._mailboxes: dict[str, list[str]] = defaultdict(list)

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath, agent_id=agent_id):
            return None
        content = self.ws.read_file(relpath, agent_id=agent_id)
        for sym in file_symbols(content):
            self._read_sets[agent_id].add((relpath, sym))
        return content

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        outcome = await self._apply_to_current(relpath, mutation, agent_id=agent_id)
        if not outcome.ok:
            return outcome
        for reader, reads in self._read_sets.items():
            if reader == agent_id or reader not in self.active:
                continue
            overlap = sorted(s for (p, s) in reads
                             if p == relpath and s in outcome.changed)
            if overlap:
                self._mailboxes[reader].append(
                    f"[coordination notice] Another agent just modified "
                    f"{relpath} (changed: {', '.join(overlap)}). If anything "
                    "you are doing depends on that file, re-read it and adjust "
                    "your plan; if not, just continue."
                )
                self.log.log("coord", strategy=self.name, action="notified",
                             writer=agent_id, reader=reader, path=relpath,
                             symbols=overlap)
        return outcome

    def drain_notifications(self, agent_id: str) -> list[str]:
        msgs = self._mailboxes[agent_id]
        self._mailboxes[agent_id] = []
        return msgs
