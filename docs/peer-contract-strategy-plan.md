# Peer Contract Strategy Plan

RaceBench currently compares coordination strategies that block, notify, detect
stale writes, or claim AST/dependency scopes. The peer-negotiation track adds a
different Level A mechanism: when agents may overlap, the harness asks them to
share intent before committing risky writes.

This is a mediated peer negotiation layer. The harness detects collisions and
enforces the protocol, but the agents provide the intent, compatibility notes,
or constraints.

Prior-art anchor: `peer_contract` and `peer_broker` are inspired by automated
negotiation work such as Li, Vo, and Kowalczyk's POANCD protocol
([UAI 2011 / arXiv 1202.3740](https://arxiv.org/abs/1202.3740)), which studies
distributed negotiation over combinatorial domains under incomplete information.
RaceBench does not implement POANCD directly. It adapts the high-level idea of
agents exchanging partial commitments or constraints toward mutually acceptable
agreements to the narrower setting of concurrent code edits.

## Version Naming Note

Early result folders use raw run labels such as
`results/grid-v1-peer-targeted-v4/` and `results/grid-v1-peer-targeted-v5/`.
Conceptually, those runs are not new top-level protocols. They are V2.x broker
refinements.

This document uses:

| Conceptual version | Meaning | Raw run label |
|--------------------|---------|---------------|
| V1 | Voluntary `peer_contract` tools | initial peer runs |
| V1.5 | Intent-scope and replay diagnostics | partial polish |
| V2.0 | Forced `peer_broker` session | initial broker |
| V2.4 | Trigger and conflict-semantics cleanup | targeted `v4` |
| V2.5 | Cached obligation broker | targeted `v5` |
| V3 | External mediation protocol | future work |

The result folders are not renamed because they are committed artifacts. The
writeup should refer to the conceptual versions and can mention raw folder names
only when linking to logs.

## Goals

- [x] Add an instrumented Level A strategy that tests structured peer
      negotiation, not only locks or stale-write detection.
- [x] Preserve RaceBench's neutral benchmark framing: peer negotiation is one
      strategy family, not the whole project.
- [x] Log enough events for validation, metrics, and replay without exposing
      hidden model reasoning.
- [x] Keep early versions small enough to run on targeted race-heavy tasks
      before any full grid rerun.

## Non-Goals

- [x] Do not claim full decentralization. The harness mediates the session.
- [x] Do not turn Level C external runtimes into strategy comparisons unless
      they emit RaceBench-compatible read/write/intent events.
- [x] Do not build a CRDT, merge engine, or manager-agent planner in V1.
- [x] Do not require paid reruns before the mechanics are covered by tests.

## V1: Tool-Based Peer Contract

`peer_contract` is the voluntary A2A strategy. Agents declare edit intent and
ACK compatible peer work before overlapping writes proceed.

- [x] Add optional strategy-owned tools to the agent loop:
      `declare_intent` and `ack_contract`.
- [x] Add base strategy hooks:
      `extra_tool_schemas()` and `handle_strategy_tool(...)`.
- [x] Track declared intents with file path, optional symbols, summary,
      exports, and must-preserve constraints.
- [x] Detect overlap at write time using same-file and symbol intersections.
- [x] Allow writes with no overlap.
- [x] Require ACK before overlapping writes proceed.
- [x] Refuse overlapping writes with a clear retry message when no contract is
      acknowledged before timeout.
- [x] Deliver peer intent notifications through the existing notification
      mechanism.
- [x] Log `coord` events:
      `intent_declared`, `contract_proposed`, `contract_ack`,
      `contract_write_allowed`, and `contract_timeout`.
- [x] Add unit and scripted tests for registration, non-overlap, overlap
      gating, ACK success, timeout/refusal, and event logging.
- [x] Clarify ACK semantics: same-file or same-function overlap is not a
      conflict when one final implementation can satisfy both subtasks.

## V1.5: Smarter Intent Scope And Diagnostics

This is useful polish for `peer_contract`, but it should not block evaluating
the broker family. The early targeted logs showed that forced negotiation needed
trigger and retry-loop fixes first.

- [x] Use changed-symbol detection when possible so same-file disjoint edits do
      not needlessly stall.
- [ ] Add dependency-graph overlap for cross-file read/write antidependencies.
- [ ] Count negotiation metrics in analysis:
      negotiations per trial, ACK rate, contract timeout rate, and token
      overhead.
- [ ] Surface contract events in `report.html` replay with a distinct marker.
- [x] Add targeted grid config:
      `t01`, `t03`, `t04`, `rw_d_antidependency`, `rw_e_cascade`, plus one
      benign-overlap task such as `t02` or `t09`.

## V2.0: Forced Private Broker Session

`peer_broker` tests a stronger hypothesis: agents should not need to voluntarily
declare intent. The runtime detects an overlapping write and privately asks
affected peers whether the write is compatible.

- [x] Ask affected agents for a private structured response when a write
      collision is detected.
- [x] Pause only the involved agents, not the whole trial.
- [x] Exchange compact JSON intents, then collect ACK or conflict decisions.
- [x] Bound negotiation wall-clock time with the existing lock timeout.
- [x] Log broker requests, broker decisions, write-allowed events, conflicts,
      and timeouts.
- [x] Include a compact write preview so peers judge the actual proposed change,
      not only the file and symbols.

Broker log convention: normal agent-loop turns are positive. Private broker LLM
calls are logged as `llm_usage` with `phase: "broker"` and `turn: -1`, `-2`,
etc. The negative turn marks an out-of-band negotiation call and keeps it
separate from the agent's normal ReAct/tool trajectory.

## V2.4: Trigger And Conflict-Semantics Cleanup

These refinements correspond to the raw targeted `v4` run. They still belong to
the V2 broker family because they change broker trigger policy and decision
semantics, not the overall architecture.

- [x] Support `ack_with_constraints`, returning peer requirements to the writer
      instead of treating every concern as a hard veto.
- [x] Support `irrelevant`, allowing peers to say a brokered write does not
      affect their subtask.
- [x] Reduce broad read-set triggers: function-level writes now broker on
      overlapping peer intents, while module/file-level writes still broker
      against peers that read the same file.
- [x] Clarify conflict semantics: conflict means no final implementation can
      satisfy both subtasks, not merely that two agents touch the same file or
      function.
- [x] Analyze the targeted run: both `peer_contract` and `peer_broker` reached
      4/5, but broker was slower and token-heavier. The `rw_e_cascade` pass was
      correct but unhealthy, with many stalls, refused writes, and max-turn
      agents.

## V2.5: Cached Obligation Broker

These refinements correspond to the raw targeted `v5` run. The goal was to keep
the useful part of broker negotiation while preventing revision loops.

- [x] Reuse adaptive-lease semantic-resource inference as a narrower broker
      trigger. Same-file symbol overlap still triggers, but broad read overlap
      is now a fallback when no semantic resource is available.
- [x] Record semantic resources read by each peer so cross-file dependencies
      such as `article.summary.*`, `tag.normalization`, `api.fetch.*`, and
      `datasource.parse_dataset.public_api` can trigger a broker session.
- [x] Cache broker decisions by writer, peer, and conflict key so later writes
      to the same semantic resource do not repeatedly ask the same peer.
- [x] Treat `ack_with_constraints` as an obligation instead of an immediate
      refused write. Hard `conflict` still refuses.
- [x] Inject obligation notes into the writer's future context and log
      `broker_obligation_recorded` / `broker_constraints_recorded`.
- [x] Trim broker write previews to reduce private-negotiation prompt cost.
- [x] Run the targeted V2.5 config and compare against V2.4, `peer_contract`,
      and `adaptive_lease`.
- [x] Run the full extension grid and update the interpretation: `peer_broker`
      scored 51/80, below `naive` at 56/80 and below `peer_contract` at 67/80.
      This makes broker a useful ablation or fallback idea, not a headline
      success.

## V3: External Mediation Protocol

V3 is reserved for making peer negotiation available to external runtimes. This
is separate from V2.x because it changes the public adapter contract rather than
just broker behavior inside RaceBench.

- [ ] Convert the protocol into adapter-facing hooks:
      `on_read`, `on_write_intent`, `decision`, `on_write_committed`, and
      `on_agent_done`.
- [ ] Implement one external adapter that emits compatible events.
- [ ] Keep external runtimes without these hooks as Level C black-box checks.
- [ ] Document which results are strategy-comparable and which are only
      correctness/wall-clock smoke checks.

## Evaluation Plan

- [x] Run offline scripted tests.
- [x] Run targeted peer grids through the V2.5 broker refinement.
- [x] Compare against `naive`, `notify`, `file_lock`, `git_hash`, and `ast_dep`
      on the targeted slice.
- [x] Run a full extension grid for `peer_contract`, `peer_broker`, and
      `adaptive_lease`.
- [x] Treat broker honestly after the full grid: targeted improvement did not
      generalize, so broker is an ablation/fallback story.
- [ ] Prototype the next hybrid: adaptive semantic leases first, broker only for
      ambiguous conflicts, followed by mandatory re-read before commit.
- [ ] Add persistent obligations to `peer_contract` after an ACK.
