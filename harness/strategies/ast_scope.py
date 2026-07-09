"""AST symbol-scope strategy (Grit/Phantom/Weave-style, reimplemented for
neutral measurement).

Writes claim the top-level symbols they change (Python ast diff; non-Python
files degrade to a whole-file claim). A write blocks only when it touches a
symbol another ACTIVE agent has already changed — so two agents editing
disjoint functions in the same file never stall, which is precisely the
false-positive case file-level locking pays for.

Reads record the agent's symbol-level read set. Read sets do not block anyone;
they are logged so the metrics pipeline can report read-write intersections
(the hook where a CoAgent-style notification mechanism would attach).
"""
from __future__ import annotations

import asyncio
import time

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register
from harness.symbols import changed_symbols, file_symbols


@register
class AstScopeStrategy(Strategy):
    name = "ast_scope"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._claims: dict[tuple[str, str], str] = {}   # (path, symbol) -> agent
        self._read_sets: dict[str, set[tuple[str, str]]] = {}
        self._released = asyncio.Condition()

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath):
            return None
        content = self.ws.read_file(relpath)
        reads = self._read_sets.setdefault(agent_id, set())
        for sym in file_symbols(content):
            reads.add((relpath, sym))
        return content

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        t0 = time.monotonic()
        logged_block = False
        while True:
            # compute the symbols this write would change, against current disk
            base = self.ws.read_file(relpath) if self.ws.exists(relpath) else None
            new = mutation.apply(base)
            if new is None:
                return WriteOutcome(
                    status="edit_failed",
                    message="old_string not found in current file content "
                            "(the file may have changed since you read it — re-read it)",
                )
            changed = changed_symbols(base or "", new)

            blockers = {
                (relpath, s): owner
                for s in changed
                if (owner := self._claims.get((relpath, s))) is not None
                and owner != agent_id and owner in self.active
            }
            if not blockers:
                async with self._released:
                    for s in changed:
                        self._claims[(relpath, s)] = agent_id
                # log read-write intersections (would-be notifications)
                for other, reads in self._read_sets.items():
                    if other == agent_id or other not in self.active:
                        continue
                    overlap = sorted(s for (p, s) in reads
                                     if p == relpath and s in changed)
                    if overlap:
                        self.log.log("coord", strategy=self.name,
                                     action="read_write_intersection",
                                     writer=agent_id, reader=other,
                                     path=relpath, symbols=overlap)
                outcome = await self._apply_to_current(relpath, mutation)
                outcome.waited_s = time.monotonic() - t0
                return outcome

            waited = time.monotonic() - t0
            remaining = self.lock_timeout_s - waited
            if remaining <= 0:
                return WriteOutcome(
                    status="lock_timeout", waited_s=waited,
                    message=f"symbols {sorted(s for _, s in blockers)} in {relpath} "
                            "are being changed by another agent; retry later",
                )
            if not logged_block:
                self.log.log("coord", strategy=self.name, action="blocked",
                             agent=agent_id, path=relpath,
                             symbols=sorted(s for _, s in blockers),
                             holders=sorted(set(blockers.values())))
                logged_block = True
            async with self._released:
                try:
                    await asyncio.wait_for(self._released.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass

    async def _release(self, agent_id: str) -> None:
        async with self._released:
            for key in [k for k, a in self._claims.items() if a == agent_id]:
                del self._claims[key]
            self._released.notify_all()
