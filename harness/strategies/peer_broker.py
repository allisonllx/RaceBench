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
from harness.strategies.peer_contract import Intent, PeerContractStrategy
from harness.symbols import changed_symbols


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
            if decision.get("decision") != "ack"
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
            "decision": (
                "ack" if str(decision.get("decision") or "").lower() == "ack"
                else "conflict"
            ),
            "notes": str(decision.get("notes") or "")[:500],
            "contract": str(decision.get("contract") or "")[:500],
        }
        self.log.log("coord", strategy=self.name,
                     action="broker_decision", agent=peer,
                     writer=intent.agent, contract_id=intent.contract_id,
                     path=intent.path, decision=normalized["decision"],
                     notes=normalized["notes"][:300],
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
