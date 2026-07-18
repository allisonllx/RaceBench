"""Forced brokered peer negotiation.

Unlike `peer_contract`, agents do not need to voluntarily declare and ACK
contracts through public tools. The strategy infers write intent at the
collision point, asks affected peers for a private broker decision, then applies
or refuses the write based on those decisions.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from harness.strategies.base import Mutation, WriteOutcome, register
from harness.strategies.peer_contract import Intent, PeerContractStrategy, _symbols_overlap
from harness.symbols import FILE_SYMBOL, MODULE_SYMBOL, changed_symbols


@register
class PeerBrokerStrategy(PeerContractStrategy):
    name = "peer_broker"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mailboxes.clear()

    def extra_tool_schemas(self) -> list[dict]:
        return []

    async def handle_strategy_tool(self, agent_id: str, name: str,
                                   arguments: dict[str, Any]) -> str | None:
        return None

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
                        "(the file may have changed since you read it — re-read it)",
            )

        changed = changed_symbols(base or "", new)
        if not changed:
            return await self._apply_to_current(relpath, mutation, agent_id=agent_id)

        intent = await self._infer_intent(agent_id, relpath, changed)
        peers = self._required_peers(agent_id, relpath, changed, intent)
        if peers:
            outcome = await self._broker_negotiation(
                intent=intent,
                peers=peers,
                mutation=mutation,
                changed=changed,
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
    ) -> set[str]:
        peers: set[str] = set()
        for other in self.active:
            if other == agent_id:
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

            if self._broad_read_overlap(other, relpath, changed):
                peers.add(other)

        return peers

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
        started_at: float,
    ) -> WriteOutcome | None:
        active_peers = sorted(peer for peer in peers if peer in self.active)
        if not active_peers:
            return None

        self.log.log("coord", strategy=self.name, action="broker_triggered",
                     agent=intent.agent, contract_id=intent.contract_id,
                     path=intent.path, symbols=sorted(changed),
                     peers=active_peers)
        self.log.log("coord", strategy=self.name, action="blocked",
                     agent=intent.agent, path=intent.path,
                     contract_id=intent.contract_id, holders=active_peers)

        remaining = self.lock_timeout_s - (time.monotonic() - started_at)
        if remaining <= 0:
            return self._broker_timeout(intent, active_peers, started_at)

        tasks = [
            asyncio.create_task(self._ask_peer(
                peer, intent, mutation, changed, timeout=remaining))
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
            self.log.log("coord", strategy=self.name,
                         action="broker_revision_requested",
                         agent=intent.agent,
                         contract_id=intent.contract_id, path=intent.path,
                         peers=[d.get("agent") for d in revisions],
                         notes=notes[:300])
            return WriteOutcome(
                status="conflict",
                waited_s=time.monotonic() - started_at,
                message=(
                    "peer_broker asks you to revise before writing. "
                    f"Re-read current files, incorporate these peer constraints, "
                    f"then retry the write: {notes}"
                ),
            )

        self.log.log("coord", strategy=self.name,
                     action="broker_write_allowed", agent=intent.agent,
                     contract_id=intent.contract_id, path=intent.path,
                     peers=active_peers)
        return None

    async def _ask_peer(
        self,
        peer: str,
        intent: Intent,
        mutation: Mutation,
        changed: set[str],
        *,
        timeout: float,
    ) -> dict[str, str]:
        request = {
            "contract_id": intent.contract_id,
            "writer": intent.agent,
            "path": intent.path,
            "symbols": sorted(changed),
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
                     symbols=sorted(changed))
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
                     contract=normalized["contract"][:300])
        return normalized

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


def _preview(value: str, limit: int = 1800) -> str:
    value = str(value or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... [truncated]"
