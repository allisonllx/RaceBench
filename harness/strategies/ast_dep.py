"""AST symbol-scope + cross-file dependency graph (ast_scope deepen).

Same-file claims match ast_scope. Additionally, a write blocks when:
  - a changed symbol's *use* references a def claimed by another active agent, or
  - a changed def has a *use-site* claimed by another active agent.

Reads never block; read sets are expanded with foreign defs for logging.
"""
from __future__ import annotations

import asyncio
import time

from harness.depgraph import DepGraph, build_depgraph
from harness.strategies.base import Mutation, Strategy, WriteOutcome, register
from harness.symbols import changed_symbols, file_symbols


@register
class AstDepStrategy(Strategy):
    name = "ast_dep"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._claims: dict[tuple[str, str], str] = {}  # (path, symbol) -> agent
        self._read_sets: dict[str, set[tuple[str, str]]] = {}
        self._released = asyncio.Condition()
        self._graph: DepGraph | None = None

    def _root_for(self, agent_id: str):
        return self.ws.agent_root(agent_id)

    def _graph_for(self, agent_id: str) -> DepGraph:
        # Shared isolation: one graph on ws.root. Worktree: rebuild from agent tree.
        root = self._root_for(agent_id)
        if self._graph is None or self._graph.root != root.resolve():
            self._graph = build_depgraph(root)
        return self._graph

    def _refresh(self, agent_id: str) -> DepGraph:
        self._graph = build_depgraph(self._root_for(agent_id))
        return self._graph

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath, agent_id=agent_id):
            return None
        content = self.ws.read_file(relpath, agent_id=agent_id)
        graph = self._graph_for(agent_id)
        reads = self._read_sets.setdefault(agent_id, set())
        reads.update(graph.expanded_read_keys(relpath, content))
        return content

    def _cross_file_blockers(self, agent_id: str, relpath: str,
                             new_content: str, changed: set[str],
                             graph: DepGraph) -> dict[tuple[str, str], str]:
        blockers: dict[tuple[str, str], str] = {}

        # Use → def: new content of changed symbols references a claimed def
        refs = graph.refs_from_source(relpath, new_content, symbols=changed)
        # Also consult index for dependents of changed defs (def → use)
        for s in changed:
            refs |= graph.refs_of(relpath, s)
            for use in graph.dependents_of(relpath, s):
                owner = self._claims.get(use)
                if owner and owner != agent_id and owner in self.active:
                    blockers[use] = owner

        for key in refs:
            owner = self._claims.get(key)
            if owner and owner != agent_id and owner in self.active:
                blockers[key] = owner

        # Proposed new edges: if we're about to claim a def that another agent
        # already claimed a dependent use of — covered by dependents_of above
        # using the *current* index. For brand-new refs in new_content that
        # point at claimed defs — covered by refs_from_source.
        return blockers

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        t0 = time.monotonic()
        logged_block = False
        while True:
            graph = self._graph_for(agent_id)
            base = (self.ws.read_file(relpath, agent_id=agent_id)
                    if self.ws.exists(relpath, agent_id=agent_id) else None)
            new = mutation.apply(base)
            if new is None:
                return WriteOutcome(
                    status="edit_failed",
                    message="old_string not found in current file content "
                            "(the file may have changed since you read it — re-read it)",
                )
            changed = changed_symbols(base or "", new)

            # Same-file claims
            blockers = {
                (relpath, s): owner
                for s in changed
                if (owner := self._claims.get((relpath, s))) is not None
                and owner != agent_id and owner in self.active
            }
            # Cross-file
            blockers.update(self._cross_file_blockers(
                agent_id, relpath, new, changed, graph))

            if not blockers:
                async with self._released:
                    for s in changed:
                        self._claims[(relpath, s)] = agent_id
                # Log intersections against expanded read sets
                for other, reads in self._read_sets.items():
                    if other == agent_id or other not in self.active:
                        continue
                    touched = {(relpath, s) for s in changed}
                    # also defs we change that others have in read set
                    overlap_keys = sorted(touched & reads)
                    # foreign: others read a def we changed
                    for s in changed:
                        for use in graph.dependents_of(relpath, s):
                            if use in reads:
                                overlap_keys.append(use)
                    # we write a use of a def they read
                    for key in graph.refs_from_source(relpath, new, changed):
                        if key in reads:
                            overlap_keys.append(key)
                    overlap_keys = sorted(set(overlap_keys))
                    if overlap_keys:
                        self.log.log("coord", strategy=self.name,
                                     action="read_write_intersection",
                                     writer=agent_id, reader=other,
                                     path=relpath,
                                     symbols=[f"{p}:{s}" for p, s in overlap_keys])
                outcome = await self._apply_to_current(
                    relpath, mutation, agent_id=agent_id)
                outcome.waited_s = time.monotonic() - t0
                self._refresh(agent_id)
                return outcome

            waited = time.monotonic() - t0
            remaining = self.lock_timeout_s - waited
            if remaining <= 0:
                return WriteOutcome(
                    status="lock_timeout", waited_s=waited,
                    message=f"symbols {sorted(f'{p}:{s}' for p, s in blockers)} "
                            "are held by another agent; retry later",
                )
            if not logged_block:
                self.log.log("coord", strategy=self.name, action="blocked",
                             agent=agent_id, path=relpath,
                             symbols=sorted(f"{p}:{s}" for p, s in blockers),
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
