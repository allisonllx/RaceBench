"""Mediated peer-contract coordination.

Agents declare structured edit intent before risky writes. When another active
agent has read or declared overlapping work, the write waits for that peer to
ACK the intent. This keeps the mechanism inside RaceBench's Level A strategy
layer: the harness detects overlap and enforces the protocol, while the agents
provide the contract text.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
import time
from typing import Any

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register
from harness.symbols import FILE_SYMBOL, changed_symbols, file_symbols


DECLARE_INTENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "declare_intent",
        "description": (
            "Peer-contract strategy tool. Call before editing a file. Describe "
            "the path, symbols, structural change, exported names, and anything "
            "other agents must preserve."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Top-level symbols you expect to change.",
                },
                "summary": {"type": "string"},
                "exports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names or interfaces other agents can rely on.",
                },
                "must_preserve": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Existing behavior or signatures to preserve.",
                },
            },
            "required": ["path", "summary"],
        },
    },
}

ACK_CONTRACT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ack_contract",
        "description": (
            "Peer-contract strategy tool. ACK another agent's intent when one "
            "final implementation can satisfy both subtasks; reject only when "
            "the requirements cannot coexist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "contract_id": {"type": "string"},
                "decision": {
                    "type": "string",
                    "enum": ["ack", "conflict"],
                    "description": (
                        "Use ack when the final code can include both changes, "
                        "even if both agents touch the same file or function. "
                        "Use conflict only when no final code can satisfy both "
                        "subtasks."
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Short compatibility reason, behavior you will preserve, "
                        "or why the requirements cannot coexist."
                    ),
                },
            },
            "required": ["contract_id", "decision"],
        },
    },
}


@dataclass
class Intent:
    contract_id: str
    agent: str
    path: str
    symbols: set[str] = field(default_factory=set)
    summary: str = ""
    exports: list[str] = field(default_factory=list)
    must_preserve: list[str] = field(default_factory=list)
    inferred: bool = False


@register
class PeerContractStrategy(Strategy):
    name = "peer_contract"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._read_sets: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self._intents: dict[str, list[Intent]] = defaultdict(list)
        self._intent_by_id: dict[str, Intent] = {}
        self._acks: dict[str, dict[str, str]] = defaultdict(dict)
        self._ack_notes: dict[str, dict[str, str]] = defaultdict(dict)
        self._proposed: set[tuple[str, str]] = set()
        self._mailboxes: dict[str, list[str]] = defaultdict(list)
        self._next_intent = 1
        self._changed = asyncio.Condition()

        protocol_note = (
            "[peer-contract protocol] Before editing, call declare_intent with "
            "the file path, symbols you expect to change, a short summary, any "
            "exports other agents can rely on, and must-preserve constraints. "
            "If you receive a peer intent, ACK when one final implementation "
            "can satisfy both subtasks, even if both agents touch the same file "
            "or function. If you ACK, finish your own changes so they preserve "
            "the peer intent. Use conflict only when the requirements cannot "
            "coexist."
        )
        for agent_id in self.agent_ids:
            self._mailboxes[agent_id].append(protocol_note)

    def extra_tool_schemas(self) -> list[dict]:
        return [DECLARE_INTENT_SCHEMA, ACK_CONTRACT_SCHEMA]

    async def handle_strategy_tool(self, agent_id: str, name: str,
                                   arguments: dict[str, Any]) -> str | None:
        if name == "declare_intent":
            return await self._declare_intent(agent_id, arguments)
        if name == "ack_contract":
            return await self._ack_contract(agent_id, arguments)
        return None

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath, agent_id=agent_id):
            return None
        content = self.ws.read_file(relpath, agent_id=agent_id)
        for sym in file_symbols(content):
            self._read_sets[agent_id].add((relpath, sym))
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
                        "(the file may have changed since you read it — re-read it)",
            )

        changed = changed_symbols(base or "", new)
        if not changed:
            return await self._apply_to_current(relpath, mutation, agent_id=agent_id)

        own_intent = self._matching_intent(agent_id, relpath, changed)
        if own_intent is None:
            own_intent = await self._infer_intent(agent_id, relpath, changed)

        required = self._required_peers(agent_id, relpath, changed, own_intent)
        if required:
            self._propose_to_peers(own_intent, required, reason="write_overlap")
            outcome = await self._wait_for_contract(own_intent, required, t0)
            if outcome is not None:
                return outcome
            self.log.log("coord", strategy=self.name,
                         action="contract_write_allowed", agent=agent_id,
                         contract_id=own_intent.contract_id, path=relpath,
                         peers=sorted(required))

        outcome = await self._apply_to_current(relpath, mutation, agent_id=agent_id)
        outcome.waited_s += time.monotonic() - t0
        return outcome

    async def _release(self, agent_id: str) -> None:
        async with self._changed:
            self._changed.notify_all()

    def drain_notifications(self, agent_id: str) -> list[str]:
        msgs = self._mailboxes[agent_id]
        self._mailboxes[agent_id] = []
        return msgs

    async def _declare_intent(self, agent_id: str, arguments: dict[str, Any]) -> str:
        path = str(arguments.get("path") or "").strip()
        if not path:
            return "ERROR: declare_intent requires a non-empty path."
        intent = self._new_intent(
            agent_id=agent_id,
            path=path,
            symbols=_clean_list(arguments.get("symbols")),
            summary=str(arguments.get("summary") or "")[:500],
            exports=_clean_items(arguments.get("exports")),
            must_preserve=_clean_items(arguments.get("must_preserve")),
            inferred=False,
        )
        self.log.log("coord", strategy=self.name, action="intent_declared",
                     agent=agent_id, contract_id=intent.contract_id,
                     path=intent.path, symbols=sorted(intent.symbols),
                     summary=intent.summary[:300], exports=intent.exports,
                     must_preserve=intent.must_preserve)

        peers = self._overlapping_peers_for_intent(intent)
        if peers:
            self._propose_to_peers(intent, peers, reason="intent_overlap")
        async with self._changed:
            self._changed.notify_all()
        if not peers:
            return f"OK: intent {intent.contract_id} declared; no active overlap found."
        return (
            f"OK: intent {intent.contract_id} declared; waiting for ACK from "
            f"{', '.join(sorted(peers))} before overlapping writes."
        )

    async def _ack_contract(self, agent_id: str, arguments: dict[str, Any]) -> str:
        contract_id = str(arguments.get("contract_id") or "").strip()
        decision = str(arguments.get("decision") or "").strip().lower()
        notes = str(arguments.get("notes") or "")[:500]
        intent = self._intent_by_id.get(contract_id)
        if intent is None:
            return f"ERROR: unknown contract_id {contract_id!r}."
        if intent.agent == agent_id:
            return "ERROR: agents cannot ACK their own contract."
        if decision not in {"ack", "conflict"}:
            return "ERROR: decision must be 'ack' or 'conflict'."

        self._acks[contract_id][agent_id] = decision
        self._ack_notes[contract_id][agent_id] = notes
        self.log.log("coord", strategy=self.name, action="contract_ack",
                     agent=agent_id, owner=intent.agent,
                     contract_id=contract_id, path=intent.path,
                     decision=decision, notes=notes[:300])
        async with self._changed:
            self._changed.notify_all()
        if decision == "ack":
            return f"OK: acknowledged {contract_id}."
        return f"OK: marked {contract_id} as conflicting."

    async def _infer_intent(self, agent_id: str, relpath: str,
                            changed: set[str]) -> Intent:
        intent = self._new_intent(
            agent_id=agent_id,
            path=relpath,
            symbols=set(changed),
            summary="inferred from write without prior declare_intent",
            exports=[],
            must_preserve=[],
            inferred=True,
        )
        self.log.log("coord", strategy=self.name, action="intent_inferred",
                     agent=agent_id, contract_id=intent.contract_id,
                     path=relpath, symbols=sorted(intent.symbols))
        async with self._changed:
            self._changed.notify_all()
        return intent

    def _new_intent(
        self,
        *,
        agent_id: str,
        path: str,
        symbols: set[str],
        summary: str,
        exports: list[str],
        must_preserve: list[str],
        inferred: bool,
    ) -> Intent:
        contract_id = f"contract-{self._next_intent}"
        self._next_intent += 1
        intent = Intent(
            contract_id=contract_id,
            agent=agent_id,
            path=path,
            symbols=set(symbols),
            summary=summary,
            exports=list(exports),
            must_preserve=list(must_preserve),
            inferred=inferred,
        )
        self._intents[agent_id].append(intent)
        self._intent_by_id[contract_id] = intent
        return intent

    def _matching_intent(self, agent_id: str, relpath: str,
                         changed: set[str]) -> Intent | None:
        for intent in reversed(self._intents.get(agent_id, [])):
            if intent.path == relpath and _symbols_overlap(intent.symbols, changed):
                return intent
        return None

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
            if self._peer_intent_overlaps(other, relpath, changed):
                peers.add(other)
                continue
            reads = {sym for path, sym in self._read_sets.get(other, set())
                     if path == relpath}
            if reads and _symbols_overlap(reads, changed):
                peers.add(other)
        return {
            peer for peer in peers
            if self._acks[own_intent.contract_id].get(peer) != "ack"
        }

    def _peer_intent_overlaps(self, peer: str, relpath: str,
                              changed: set[str]) -> bool:
        return any(
            intent.path == relpath and _symbols_overlap(intent.symbols, changed)
            for intent in self._intents.get(peer, [])
        )

    def _overlapping_peers_for_intent(self, intent: Intent) -> set[str]:
        peers: set[str] = set()
        for other in self.active:
            if other == intent.agent:
                continue
            peer_intents = [
                peer_intent for peer_intent in self._intents.get(other, [])
                if peer_intent.path == intent.path
            ]
            if peer_intents:
                if any(_symbols_overlap(peer_intent.symbols, intent.symbols)
                       for peer_intent in peer_intents):
                    peers.add(other)
                continue
            if self._peer_intent_overlaps(other, intent.path, intent.symbols):
                peers.add(other)
                continue
            reads = {sym for path, sym in self._read_sets.get(other, set())
                     if path == intent.path}
            if reads and _symbols_overlap(reads, intent.symbols):
                peers.add(other)
        return peers

    def _propose_to_peers(self, intent: Intent, peers: set[str], *,
                          reason: str) -> None:
        for peer in sorted(peers):
            key = (intent.contract_id, peer)
            if key in self._proposed:
                continue
            self._proposed.add(key)
            note = (
                "[peer-contract request] "
                f"{intent.agent} wants to edit {intent.path}"
                f" (contract_id={intent.contract_id}, "
                f"symbols={', '.join(sorted(intent.symbols)) or 'unspecified'}). "
                f"Summary: {intent.summary or 'unspecified'}. "
                f"Exports: {', '.join(intent.exports) or 'none'}. "
                f"Must preserve: {', '.join(intent.must_preserve) or 'none'}. "
                "ACK when one final implementation can satisfy both subtasks, "
                "even if both agents touch the same file or function. If you "
                "ACK, finish your own changes so they preserve this intent. "
                "Use conflict only when the requirements cannot coexist."
            )
            self._mailboxes[peer].append(note)
            self.log.log("coord", strategy=self.name,
                         action="contract_proposed", agent=intent.agent,
                         peer=peer, contract_id=intent.contract_id,
                         path=intent.path, symbols=sorted(intent.symbols),
                         reason=reason)

    async def _wait_for_contract(
        self,
        intent: Intent,
        required: set[str],
        started_at: float,
    ) -> WriteOutcome | None:
        logged_block = False
        while True:
            active_required = {peer for peer in required if peer in self.active}
            conflicts = sorted(
                peer for peer in active_required
                if self._acks[intent.contract_id].get(peer) == "conflict"
            )
            if conflicts:
                return WriteOutcome(
                    status="conflict",
                    waited_s=time.monotonic() - started_at,
                    message=(
                        f"peer_contract rejected by {', '.join(conflicts)}: "
                        f"{self._conflict_notes(intent.contract_id, conflicts)}"
                    ),
                )
            pending = sorted(
                peer for peer in active_required
                if self._acks[intent.contract_id].get(peer) != "ack"
            )
            if not pending:
                return None

            waited = time.monotonic() - started_at
            remaining = self.lock_timeout_s - waited
            if remaining <= 0:
                self.log.log("coord", strategy=self.name,
                             action="contract_timeout", agent=intent.agent,
                             contract_id=intent.contract_id, path=intent.path,
                             peers=pending, waited_s=round(waited, 3))
                return WriteOutcome(
                    status="lock_timeout",
                    waited_s=waited,
                    message=(
                        f"peer_contract needs ACK from {', '.join(pending)} "
                        f"before editing {intent.path}; ask peers to ACK or "
                        "retry after they finish"
                    ),
                )
            if not logged_block:
                self.log.log("coord", strategy=self.name, action="blocked",
                             agent=intent.agent, path=intent.path,
                             contract_id=intent.contract_id, holders=pending)
                logged_block = True
            async with self._changed:
                try:
                    await asyncio.wait_for(self._changed.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass

    def _conflict_notes(self, contract_id: str, peers: list[str]) -> str:
        notes = [
            f"{peer}: {self._ack_notes[contract_id].get(peer, '').strip()}"
            for peer in peers
            if self._ack_notes[contract_id].get(peer, "").strip()
        ]
        return "; ".join(notes) or "no reason provided"


def _clean_list(value: Any) -> set[str]:
    return set(_clean_items(value))


def _clean_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = list(value) if isinstance(value, (tuple, set)) else [value]
    cleaned = [str(item).strip()[:120] for item in raw if str(item).strip()]
    return sorted(set(cleaned))


def _symbols_overlap(left: set[str], right: set[str]) -> bool:
    if not left or not right:
        return True
    if FILE_SYMBOL in left or FILE_SYMBOL in right:
        return True
    return not left.isdisjoint(right)
