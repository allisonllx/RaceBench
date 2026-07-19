"""Adaptive file/symbol/resource lease strategy.

This strategy tries to keep the part of file_lock that is valuable, namely a
conservative fallback when scope is uncertain, while avoiding file_lock's
benign same-file false positives.

V1 is deliberately mechanical and verifier-friendly:
  - precise top-level function/class edits acquire symbol leases;
  - module-level, whole-file, non-Python, or parse-uncertain edits acquire a
    file lease;
  - stale whole-file overwrites are refused instead of silently clobbering a
    change made after the writer's last read.

V2 adds semantic resources. Agents can declare resources up front, and the
runtime also infers a small conservative resource catalog from paths/symbols.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
import time
from typing import Any

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register
from harness.symbols import FILE_SYMBOL, MODULE_SYMBOL, changed_symbols, file_symbols

LeaseKey = tuple[str, str, str]
FILE_LEASE = "file"
SYMBOL_LEASE = "symbol"
RESOURCE_LEASE = "resource"
BROAD_SYMBOLS = {FILE_SYMBOL, MODULE_SYMBOL}

DECLARE_SCOPE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "declare_scope",
        "description": (
            "Adaptive-lease strategy tool. Declare semantic resources your "
            "subtask will change or must preserve before risky edits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "resources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Behavior-level resources, for example "
                        "tag.normalization, article.summary.schema, "
                        "article.summary.feed_output, api.fetch.signature, "
                        "datasource.parse_dataset.public_api."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": "Optional primary file path for the scope.",
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional top-level symbols involved.",
                },
                "summary": {"type": "string"},
                "exports": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "must_preserve": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["resources"],
        },
    },
}


@register
class AdaptiveLeaseStrategy(Strategy):
    name = "adaptive_lease"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._leases: dict[LeaseKey, str] = {}
        self._read_sets: dict[str, set[tuple[str, str]]] = {}
        self._resource_read_sets: dict[str, set[str]] = defaultdict(set)
        self._declared_resources: dict[str, set[str]] = defaultdict(set)
        self._read_snapshots: dict[tuple[str, str], str] = {}
        self._mailboxes: dict[str, list[str]] = defaultdict(list)
        self._released = asyncio.Condition()
        note = (
            "[adaptive-lease protocol] Before risky cross-file or behavior "
            "changes, call declare_scope with semantic resources you will "
            "change or must preserve. Examples: tag.normalization, "
            "article.summary.schema, article.summary.feed_output, "
            "api.fetch.signature, datasource.parse_dataset.public_api. "
            "If you receive a semantic overlap notice, re-read the named files "
            "and preserve that behavior."
        )
        for agent_id in self.agent_ids:
            self._mailboxes[agent_id].append(note)

    def extra_tool_schemas(self) -> list[dict]:
        return [DECLARE_SCOPE_SCHEMA]

    async def handle_strategy_tool(self, agent_id: str, name: str,
                                   arguments: dict[str, Any]) -> str | None:
        if name == "declare_scope":
            return await self._declare_scope(agent_id, arguments)
        return None

    def drain_notifications(self, agent_id: str) -> list[str]:
        msgs = self._mailboxes[agent_id]
        self._mailboxes[agent_id] = []
        return msgs

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath, agent_id=agent_id):
            return None
        content = self.ws.read_file(relpath, agent_id=agent_id)
        self._read_snapshots[(agent_id, relpath)] = content
        reads = self._read_sets.setdefault(agent_id, set())
        symbols = file_symbols(content)
        for sym in symbols:
            reads.add((relpath, sym))
        resources = _semantic_resources(relpath, content, symbols)
        self._resource_read_sets[agent_id].update(resources)
        return content

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        t0 = time.monotonic()
        logged_block = False
        while True:
            base = (self.ws.read_file(relpath, agent_id=agent_id)
                    if self.ws.exists(relpath, agent_id=agent_id) else None)
            new = mutation.apply(base)
            if new is None:
                return WriteOutcome(
                    status="edit_failed",
                    message="old_string not found in current file content "
                            "(the file may have changed since you read it, re-read it)",
                )

            changed = changed_symbols(base or "", new)
            if not changed:
                return await self._apply_to_current(relpath, mutation,
                                                    agent_id=agent_id)

            resources = (
                self._declared_resources.get(agent_id, set())
                | _semantic_resources(relpath, new, changed)
            )
            leases = _lease_keys(relpath, changed, resources)
            async with self._released:
                blockers = self._blockers(agent_id, leases)
                if not blockers:
                    for key in leases:
                        self._leases[key] = agent_id
                    self.log.log("coord", strategy=self.name,
                                 action="lease_acquired", agent=agent_id,
                                 path=relpath, lease_level=_lease_level(leases),
                                 symbols=sorted(changed),
                                 resources=sorted(resources))
                    break

                waited = time.monotonic() - t0
                remaining = self.lock_timeout_s - waited
                if remaining <= 0:
                    return WriteOutcome(
                        status="lock_timeout",
                        waited_s=waited,
                        message=(
                            f"leases for {relpath} are held by "
                            f"{', '.join(sorted(set(blockers.values())))}; "
                            "re-read or retry after they finish"
                        ),
                    )
                if not logged_block:
                    self.log.log("coord", strategy=self.name, action="blocked",
                                 agent=agent_id, path=relpath,
                                 lease_level=_lease_level(leases),
                                 symbols=sorted(changed),
                                 resources=sorted(resources),
                                 holders=sorted(set(blockers.values())))
                    logged_block = True
                try:
                    await asyncio.wait_for(self._released.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass

        waited = time.monotonic() - t0
        if self._stale_overwrite(agent_id, relpath, mutation, base or "", changed):
            await self._release_leases(agent_id, leases)
            self.log.log("coord", strategy=self.name,
                         action="stale_overwrite_refused", agent=agent_id,
                         path=relpath, symbols=sorted(changed))
            return WriteOutcome(
                status="conflict",
                waited_s=waited,
                message=(
                    f"{relpath} changed since your last read; re-read it and "
                    "retry so you do not overwrite another agent's work"
                ),
            )

        self._log_read_write_intersections(
            agent_id, relpath, changed, resources, leases)
        outcome = await self._apply_to_current(relpath, mutation, agent_id=agent_id)
        outcome.waited_s += time.monotonic() - t0
        if not outcome.ok:
            await self._release_leases(agent_id, leases)
        return outcome

    async def _release(self, agent_id: str) -> None:
        await self._release_leases(agent_id, None)
        self._declared_resources.pop(agent_id, None)

    async def _declare_scope(self, agent_id: str, arguments: dict[str, Any]) -> str:
        resources = _clean_resources(arguments.get("resources"))
        path = str(arguments.get("path") or "").strip()
        symbols = set(_clean_items(arguments.get("symbols")))
        summary = str(arguments.get("summary") or "")[:500]
        exports = _clean_items(arguments.get("exports"))
        must_preserve = _clean_items(arguments.get("must_preserve"))
        if path or symbols or summary:
            resources |= _semantic_resources(path, summary, symbols)
        if not resources:
            return "ERROR: declare_scope requires at least one semantic resource."

        leases = _resource_lease_keys(resources)
        t0 = time.monotonic()
        logged_block = False
        async with self._released:
            while True:
                blockers = self._blockers(agent_id, leases)
                if not blockers:
                    for key in leases:
                        self._leases[key] = agent_id
                    self._declared_resources[agent_id].update(resources)
                    self.log.log("coord", strategy=self.name,
                                 action="scope_declared", agent=agent_id,
                                 path=path, symbols=sorted(symbols),
                                 resources=sorted(resources),
                                 summary=summary, exports=exports,
                                 must_preserve=must_preserve)
                    self.log.log("coord", strategy=self.name,
                                 action="lease_acquired", agent=agent_id,
                                 path=path, lease_level=RESOURCE_LEASE,
                                 symbols=sorted(symbols),
                                 resources=sorted(resources))
                    return (
                        "OK: semantic scope declared for "
                        f"{', '.join(sorted(resources))}."
                    )

                waited = time.monotonic() - t0
                remaining = self.lock_timeout_s - waited
                holders = sorted(set(blockers.values()))
                if remaining <= 0:
                    self.log.log("coord", strategy=self.name,
                                 action="scope_timeout", agent=agent_id,
                                 path=path, resources=sorted(resources),
                                 holders=holders, waited_s=round(waited, 3))
                    return (
                        "ERROR: semantic resources are currently held by "
                        f"{', '.join(holders)}; re-read or retry later."
                    )
                if not logged_block:
                    self.log.log("coord", strategy=self.name,
                                 action="blocked", agent=agent_id,
                                 path=path, lease_level=RESOURCE_LEASE,
                                 resources=sorted(resources), holders=holders)
                    logged_block = True
                try:
                    await asyncio.wait_for(self._released.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass

    async def _release_leases(
        self,
        agent_id: str,
        keys: set[LeaseKey] | None,
    ) -> None:
        async with self._released:
            drop = [
                key for key, owner in self._leases.items()
                if owner == agent_id and (keys is None or key in keys)
            ]
            for key in drop:
                del self._leases[key]
            self._released.notify_all()

    def _blockers(self, agent_id: str, leases: set[LeaseKey]) -> dict[LeaseKey, str]:
        blockers: dict[LeaseKey, str] = {}
        for requested in leases:
            for held, owner in self._leases.items():
                if owner == agent_id or owner not in self.active:
                    continue
                if _leases_conflict(requested, held):
                    blockers[held] = owner
        return blockers

    def _stale_overwrite(
        self,
        agent_id: str,
        relpath: str,
        mutation: Mutation,
        current: str,
        changed: set[str],
    ) -> bool:
        if mutation.kind != "overwrite":
            return False
        snapshot = self._read_snapshots.get((agent_id, relpath))
        if snapshot is None:
            return False
        changed_since_read = changed_symbols(snapshot, current)
        if not changed_since_read:
            return False
        if BROAD_SYMBOLS & (changed | changed_since_read):
            return True
        return not changed.isdisjoint(changed_since_read)

    def _log_read_write_intersections(
        self,
        agent_id: str,
        relpath: str,
        changed: set[str],
        resources: set[str],
        leases: set[LeaseKey],
    ) -> None:
        file_level = any(key[0] == FILE_LEASE for key in leases)
        for other, reads in self._read_sets.items():
            if other == agent_id or other not in self.active:
                continue
            overlap = sorted(
                sym for path, sym in reads
                if path == relpath and (file_level or sym in changed)
            )
            if overlap:
                self.log.log("coord", strategy=self.name,
                             action="read_write_intersection",
                             writer=agent_id, reader=other, path=relpath,
                             symbols=overlap)
            resource_overlap = sorted(
                resources & self._resource_read_sets.get(other, set()))
            if resource_overlap:
                self.log.log("coord", strategy=self.name,
                             action="semantic_read_write_intersection",
                             writer=agent_id, reader=other, path=relpath,
                             resources=resource_overlap)
                self._mailboxes[other].append(
                    "[adaptive-lease notice] "
                    f"{agent_id} changed semantic resources "
                    f"{', '.join(resource_overlap)} in {relpath}. "
                    "Re-read affected files before editing and preserve this "
                    "behavior in your own changes."
                )


def _lease_keys(
    relpath: str,
    changed: set[str],
    resources: set[str] | None = None,
) -> set[LeaseKey]:
    leases = _resource_lease_keys(resources or set())
    if BROAD_SYMBOLS & changed:
        leases.add((FILE_LEASE, relpath, FILE_SYMBOL))
        return leases
    leases.update((SYMBOL_LEASE, relpath, sym) for sym in changed)
    return leases


def _resource_lease_keys(resources: set[str]) -> set[LeaseKey]:
    return {(RESOURCE_LEASE, resource, resource) for resource in resources}


def _lease_level(leases: set[LeaseKey]) -> str:
    if any(key[0] == FILE_LEASE for key in leases):
        return FILE_LEASE
    if any(key[0] == RESOURCE_LEASE for key in leases):
        return RESOURCE_LEASE
    return SYMBOL_LEASE


def _leases_conflict(left: LeaseKey, right: LeaseKey) -> bool:
    left_level, left_path, left_symbol = left
    right_level, right_path, right_symbol = right
    if left_level == RESOURCE_LEASE or right_level == RESOURCE_LEASE:
        return left_level == right_level and left_path == right_path
    if left_path != right_path:
        return False
    if left_level == FILE_LEASE or right_level == FILE_LEASE:
        return True
    return left_symbol == right_symbol


def _semantic_resources(
    relpath: str,
    content: str,
    symbols: set[str] | None = None,
) -> set[str]:
    resources: set[str] = set()
    path = relpath.replace("\\", "/").lower()
    text = f"{path}\n{content}".lower()
    symbols = symbols or set()
    symbol_text = " ".join(sorted(symbols)).lower()
    combined = f"{text}\n{symbol_text}"

    if "tag" in combined and (
        "conduit/" in path
        or "tag_article_count" in combined
        or "list_articles" in combined
        or "create_article" in combined
    ):
        resources.add("tag.normalization")

    if "fetch" in combined and ("api.py" in path or "fetch" in symbol_text):
        resources.add("api.fetch.signature")
        if "timeout" in combined:
            resources.add("api.fetch.timeout_behavior")
        if "retry" in combined or "retries" in combined:
            resources.add("api.fetch.retry_behavior")

    if (
        "summary" in combined
        and ("conduit/" in path or "article" in combined)
    ):
        resources.add("article.summary")
        if "db/schema.py" in path or "schemas/article.py" in path:
            resources.add("article.summary.schema")
        if (
            "serializers/article_format.py" in path
            or "routes_articles.py" in path
            or "services/articles.py" in path
        ):
            resources.add("article.summary.article_output")
        if "services/feed.py" in path:
            resources.add("article.summary.feed_output")
        if "comments" in path:
            resources.add("article.summary.comments_output")

    if (
        "parse_dataset" in combined
        or "parse_records" in combined
        or "datasource/" in path
    ) and (
        "datasource/" in path
        or "pipeline/text.py" in path
        or "report/from_text.py" in path
    ):
        resources.add("datasource.parse_dataset.public_api")

    return resources


def _clean_resources(value: Any) -> set[str]:
    return {
        item
        for item in _clean_items(value)
        if item and all(ch.isalnum() or ch in "._:-/" for ch in item)
    }


def _clean_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = list(value) if isinstance(value, (tuple, set)) else [value]
    return sorted({str(item).strip()[:160] for item in raw if str(item).strip()})
