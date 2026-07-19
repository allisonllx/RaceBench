"""Forced brokered peer negotiation.

Unlike `peer_contract`, agents do not need to voluntarily declare and ACK
contracts through public tools. The strategy infers write intent at the
collision point, asks affected peers for a private broker decision, then applies
or refuses the write based on those decisions.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
import time
from typing import Any

from harness.strategies.base import Mutation, WriteOutcome, register
from harness.strategies.adaptive_lease import _semantic_resources
from harness.strategies.peer_contract import Intent, PeerContractStrategy, _symbols_overlap
from harness.symbols import FILE_SYMBOL, MODULE_SYMBOL, changed_symbols, file_symbols


@register
class PeerBrokerStrategy(PeerContractStrategy):
    name = "peer_broker"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mailboxes.clear()
        self._resource_read_sets: dict[str, set[str]] = defaultdict(set)
        self._decision_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._obligation_cache: set[tuple[str, str, str]] = set()

    def extra_tool_schemas(self) -> list[dict]:
        return []

    async def handle_strategy_tool(self, agent_id: str, name: str,
                                   arguments: dict[str, Any]) -> str | None:
        return None

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        content = await super()._coordinate_read(agent_id, relpath)
        if content is not None:
            self._resource_read_sets[agent_id].update(
                _semantic_resources(relpath, content, file_symbols(content)))
        return content

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        t0 = time.monotonic()
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
            return await self._apply_to_current(relpath, mutation, agent_id=agent_id)

        resources = _semantic_resources(relpath, new, changed)
        intent = await self._infer_intent(agent_id, relpath, changed)
        peers = self._required_peers(agent_id, relpath, changed, intent, resources)
        if peers:
            outcome = await self._broker_negotiation(
                intent=intent,
                peers=peers,
                mutation=mutation,
                changed=changed,
                resources=resources,
                started_at=t0,
            )
            if outcome is not None:
                return outcome

        outcome = await self._apply_to_current(relpath, mutation, agent_id=agent_id)
        outcome.waited_s += time.monotonic() - t0
        return outcome

    def _required_peers(
        self,
        agent_id: str,
        relpath: str,
        changed: set[str],
        own_intent: Intent,
        resources: set[str] | None = None,
    ) -> set[str]:
        peers: set[str] = set()
        resources = resources or set()
        for other in self.active:
            if other == agent_id:
                continue
            if self._has_allowing_cache(agent_id, other, relpath, changed, resources):
                continue

            peer_intents = [
                intent for intent in self._intents.get(other, [])
                if intent.path == relpath
            ]
            if peer_intents:
                if any(_symbols_overlap(intent.symbols, changed)
                       for intent in peer_intents):
                    peers.add(other)
                continue

            if self._semantic_read_overlap(other, resources):
                peers.add(other)
                continue

            if not resources and self._broad_read_overlap(other, relpath, changed):
                peers.add(other)

        return peers

    def _semantic_read_overlap(self, peer: str, resources: set[str]) -> bool:
        return bool(resources & self._resource_read_sets.get(peer, set()))

    def _broad_read_overlap(
        self,
        peer: str,
        relpath: str,
        changed: set[str],
    ) -> bool:
        if not ({FILE_SYMBOL, MODULE_SYMBOL} & changed):
            return False
        return any(path == relpath for path, _sym in self._read_sets.get(peer, set()))

    async def _broker_negotiation(
        self,
        *,
        intent: Intent,
        peers: set[str],
        mutation: Mutation,
        changed: set[str],
        resources: set[str],
        started_at: float,
    ) -> WriteOutcome | None:
        active_peers = sorted(peer for peer in peers if peer in self.active)
        if not active_peers:
            return None

        cached_conflicts = self._cached_conflicts(
            intent.agent, active_peers, intent.path, changed, resources)
        if cached_conflicts:
            notes = "; ".join(
                f"{peer}: {decision.get('notes') or 'cached conflict'}"
                for peer, decision in cached_conflicts.items()
            )
            self.log.log("coord", strategy=self.name,
                         action="broker_conflict", agent=intent.agent,
                         contract_id=intent.contract_id, path=intent.path,
                         peers=sorted(cached_conflicts),
                         notes=notes[:300], cached=True)
            return WriteOutcome(
                status="conflict",
                waited_s=time.monotonic() - started_at,
                message=f"peer_broker rejected by cached peer decision: {notes}",
            )

        self.log.log("coord", strategy=self.name, action="broker_triggered",
                     agent=intent.agent, contract_id=intent.contract_id,
                     path=intent.path, symbols=sorted(changed),
                     resources=sorted(resources), peers=active_peers)
        self.log.log("coord", strategy=self.name, action="blocked",
                     agent=intent.agent, path=intent.path,
                     contract_id=intent.contract_id, holders=active_peers,
                     resources=sorted(resources))

        remaining = self.lock_timeout_s - (time.monotonic() - started_at)
        if remaining <= 0:
            return self._broker_timeout(intent, active_peers, started_at)

        tasks = [
            asyncio.create_task(self._ask_peer(
                peer, intent, mutation, changed, resources, timeout=remaining))
            for peer in active_peers
        ]
        try:
            decisions = await asyncio.wait_for(
                asyncio.gather(*tasks), timeout=remaining)
        except asyncio.TimeoutError:
            for task in tasks:
                task.cancel()
            return self._broker_timeout(intent, active_peers, started_at)

        conflicts = [
            decision for decision in decisions
            if decision.get("decision") == "conflict"
        ]
        self._cache_decisions(intent.agent, intent.path, changed, resources, decisions)
        if conflicts:
            notes = "; ".join(
                f"{d.get('agent')}: {d.get('notes') or 'no reason provided'}"
                for d in conflicts
            )
            self.log.log("coord", strategy=self.name,
                         action="broker_conflict", agent=intent.agent,
                         contract_id=intent.contract_id, path=intent.path,
                         peers=[d.get("agent") for d in conflicts],
                         notes=notes[:300])
            return WriteOutcome(
                status="conflict",
                waited_s=time.monotonic() - started_at,
                message=f"peer_broker rejected by peer: {notes}",
            )

        revisions = [
            decision for decision in decisions
            if decision.get("decision") == "ack_with_constraints"
        ]
        if revisions:
            notes = self._revision_notes(revisions)
            self._record_obligations(
                intent.agent, intent.path, changed, resources, revisions)
            self.log.log("coord", strategy=self.name,
                         action="broker_constraints_recorded",
                         agent=intent.agent,
                         contract_id=intent.contract_id, path=intent.path,
                         peers=[d.get("agent") for d in revisions],
                         resources=sorted(resources), notes=notes[:300])

        self.log.log("coord", strategy=self.name,
                     action="broker_write_allowed", agent=intent.agent,
                     contract_id=intent.contract_id, path=intent.path,
                     resources=sorted(resources), peers=active_peers,
                     obligations_recorded=bool(revisions))
        return None

    async def _ask_peer(
        self,
        peer: str,
        intent: Intent,
        mutation: Mutation,
        changed: set[str],
        resources: set[str],
        *,
        timeout: float,
    ) -> dict[str, str]:
        request = {
            "contract_id": intent.contract_id,
            "writer": intent.agent,
            "path": intent.path,
            "symbols": sorted(changed),
            "resources": sorted(resources),
            "mutation_kind": mutation.kind,
            "summary": "broker-inferred write intent",
            "old_string_preview": _preview(
                mutation.old_string if mutation.kind == "replace" else ""),
            "write_preview": _preview(
                mutation.new_string if mutation.kind == "replace"
                else mutation.content),
            "peer_intents": [
                {
                    "contract_id": peer_intent.contract_id,
                    "symbols": sorted(peer_intent.symbols),
                    "summary": peer_intent.summary,
                }
                for peer_intent in self._intents.get(peer, [])
                if peer_intent.path == intent.path
            ],
        }
        self.log.log("coord", strategy=self.name,
                     action="broker_request", agent=intent.agent, peer=peer,
                     contract_id=intent.contract_id, path=intent.path,
                     symbols=sorted(changed), resources=sorted(resources))
        decision = await asyncio.wait_for(
            self.request_negotiation(peer, request), timeout=timeout)
        normalized = {
            "agent": peer,
            "decision": _normalize_decision(decision.get("decision")),
            "notes": str(decision.get("notes") or "")[:500],
            "constraints": _clean_constraints(decision.get("constraints")),
            "contract": str(decision.get("contract") or "")[:500],
        }
        self.log.log("coord", strategy=self.name,
                     action="broker_decision", agent=peer,
                     writer=intent.agent, contract_id=intent.contract_id,
                     path=intent.path, decision=normalized["decision"],
                     notes=normalized["notes"][:300],
                     constraints=normalized["constraints"],
                     contract=normalized["contract"][:300],
                     resources=sorted(resources))
        return normalized

    def _cache_decisions(
        self,
        writer: str,
        relpath: str,
        changed: set[str],
        resources: set[str],
        decisions: list[dict[str, Any]],
    ) -> None:
        for decision in decisions:
            peer = str(decision.get("agent") or "")
            if not peer:
                continue
            for key in _conflict_keys(relpath, changed, resources):
                self._decision_cache[(writer, peer, key)] = dict(decision)

    def _has_allowing_cache(
        self,
        writer: str,
        peer: str,
        relpath: str,
        changed: set[str],
        resources: set[str],
    ) -> bool:
        for key in _conflict_keys(relpath, changed, resources):
            decision = self._decision_cache.get((writer, peer, key))
            if decision and decision.get("decision") in {
                "ack", "ack_with_constraints", "irrelevant",
            }:
                return True
        return False

    def _cached_conflicts(
        self,
        writer: str,
        peers: list[str],
        relpath: str,
        changed: set[str],
        resources: set[str],
    ) -> dict[str, dict[str, Any]]:
        conflicts: dict[str, dict[str, Any]] = {}
        for peer in peers:
            for key in _conflict_keys(relpath, changed, resources):
                decision = self._decision_cache.get((writer, peer, key))
                if decision and decision.get("decision") == "conflict":
                    conflicts[peer] = decision
                    break
        return conflicts

    def _record_obligations(
        self,
        writer: str,
        relpath: str,
        changed: set[str],
        resources: set[str],
        revisions: list[dict[str, Any]],
    ) -> None:
        parts: list[str] = []
        for decision in revisions:
            peer = str(decision.get("agent") or "peer")
            requirements = _decision_requirements(decision)
            if not requirements:
                continue
            cache_key = (
                writer,
                peer,
                "|".join(_conflict_keys(relpath, changed, resources)),
            )
            if cache_key in self._obligation_cache:
                continue
            self._obligation_cache.add(cache_key)
            parts.append(f"{peer}: {requirements}")

        if not parts:
            return
        note = (
            "[peer-broker obligation] Peer constraints for "
            f"{relpath}: {' | '.join(parts)}. Preserve these requirements in "
            "later edits and before calling done. The broker cached this "
            "decision and will not re-ask for the same conflict key."
        )
        self._mailboxes[writer].append(note)
        self.log.log("coord", strategy=self.name,
                     action="broker_obligation_recorded", agent=writer,
                     path=relpath, symbols=sorted(changed),
                     resources=sorted(resources), notes=note[:300])

    def _broker_timeout(
        self,
        intent: Intent,
        peers: list[str],
        started_at: float,
    ) -> WriteOutcome:
        waited = time.monotonic() - started_at
        self.log.log("coord", strategy=self.name, action="broker_timeout",
                     agent=intent.agent, contract_id=intent.contract_id,
                     path=intent.path, peers=peers,
                     waited_s=round(waited, 3))
        return WriteOutcome(
            status="lock_timeout",
            waited_s=waited,
            message=(
                f"peer_broker could not obtain decisions from "
                f"{', '.join(peers)} before editing {intent.path}"
            ),
        )

    def _revision_notes(self, revisions: list[dict[str, Any]]) -> str:
        parts = []
        for decision in revisions:
            agent = decision.get("agent")
            constraints = decision.get("constraints") or []
            contract = str(decision.get("contract") or "").strip()
            notes = str(decision.get("notes") or "").strip()
            requirements = "; ".join(constraints)
            if contract:
                requirements = f"{requirements}; {contract}" if requirements else contract
            if not requirements:
                requirements = notes or "revise to preserve peer requirements"
            parts.append(f"{agent}: {requirements}")
        return " | ".join(parts)


def _normalize_decision(value: Any) -> str:
    decision = str(value or "").lower()
    if decision in {"ack", "ack_with_constraints", "irrelevant", "conflict"}:
        return decision
    return "conflict"


def _clean_constraints(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = list(value) if isinstance(value, (tuple, set)) else [value]
    return sorted({str(item).strip()[:200] for item in raw if str(item).strip()})


def _conflict_keys(
    relpath: str,
    changed: set[str],
    resources: set[str],
) -> tuple[str, ...]:
    if resources:
        return tuple(f"resource:{resource}" for resource in sorted(resources))
    if {FILE_SYMBOL, MODULE_SYMBOL} & changed:
        return (f"file:{relpath}",)
    symbols = sorted(changed) or ["<unknown>"]
    return tuple(f"symbol:{relpath}:{symbol}" for symbol in symbols)


def _decision_requirements(decision: dict[str, Any]) -> str:
    constraints = decision.get("constraints") or []
    contract = str(decision.get("contract") or "").strip()
    notes = str(decision.get("notes") or "").strip()
    parts = [str(item).strip() for item in constraints if str(item).strip()]
    if contract:
        parts.append(contract)
    if not parts and notes:
        parts.append(notes)
    return "; ".join(parts)


def _preview(value: str, limit: int = 900) -> str:
    value = str(value or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... [truncated]"
