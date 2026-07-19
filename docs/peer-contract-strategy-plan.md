# Peer Contract Strategy Plan

RaceBench currently compares coordination strategies that block, notify, detect
stale writes, or claim AST/dependency scopes. The `peer_contract` strategy adds
a different Level A mechanism: when agents may overlap, the harness asks them to
declare intent and acknowledge a compact shared contract before committing risky
writes.

This is a mediated peer negotiation layer. The harness detects collisions and
enforces the protocol, but the agents provide the intent and agreement text.

Prior-art anchor: `peer_contract` and `peer_broker` are inspired by automated
negotiation work such as Li, Vo, and Kowalczyk's POANCD protocol
([UAI 2011 / arXiv 1202.3740](https://arxiv.org/abs/1202.3740)), which studies
distributed negotiation over combinatorial domains under incomplete information.
RaceBench does not implement POANCD directly. It adapts the high-level idea of
agents exchanging partial commitments or constraints toward mutually acceptable
agreements to the narrower setting of concurrent code edits.

## Goals

- [x] Add an instrumented Level A strategy that tests structured peer
      negotiation, not only locks or stale-write detection.
- [x] Preserve RaceBench's neutral benchmark framing: `peer_contract` is one
      comparable strategy column, not the whole project.
- [x] Log enough events for validation, metrics, and replay without exposing
      hidden model reasoning.
- [x] Keep V1 small enough to run on targeted race-heavy tasks before any full
      grid rerun.

## Non-Goals

- [x] Do not claim full decentralization. The harness mediates the session.
- [x] Do not turn Level C external runtimes into strategy comparisons unless
      they emit RaceBench-compatible read/write/intent events.
- [x] Do not build a CRDT, merge engine, or manager-agent planner in V1.
- [x] Do not require paid reruns before the mechanics are covered by tests.

## V1: Tool-Based Peer Contract

- [x] Add optional strategy-owned tools to the agent loop:
      `declare_intent` and `ack_contract`.
- [x] Add base strategy hooks:
      `extra_tool_schemas()` and `handle_strategy_tool(...)`.
- [x] Implement `peer_contract` as a normal Level A strategy.
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

This is useful polish, but it should not block the small peer-strategy rerun.
The broker fix in V2 is higher priority because the first targeted logs showed
hard veto loops.

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

## V2: Forced Private Negotiation Session

- [x] Add a `NegotiationBroker` that can ask affected agents for a private
      structured response when a write collision is detected.
- [x] Pause only the involved agents, not the whole trial.
- [x] Exchange compact JSON intents, then collect ACK or conflict decisions.
- [x] Bound negotiation wall-clock time with the existing lock timeout.
- [x] Log broker requests, broker decisions, write-allowed events, conflicts,
      and timeouts.
- [x] Include a compact write preview so peers judge the actual proposed change,
      not only the file and symbols.
- [x] Support `ack_with_constraints`, returning peer requirements to the writer
      as a revision request instead of treating every concern as a hard veto.
- [x] Support `irrelevant`, allowing peers to explicitly say a brokered write
      does not affect their subtask.
- [x] Reduce broad read-set triggers: function-level writes now broker on
      overlapping peer intents, while module/file-level writes still broker
      against peers that read the same file.
- [ ] Compare against V1 to see whether forced negotiation is worth the extra
      runtime and token cost.

## V5: Cached Obligation Broker

Implemented after targeted V4 showed that `peer_broker` could recover hard
cases, but sometimes bought correctness through too many revision loops. The
worst example was `rw_e_cascade`: the oracle passed, but the run used many
broker requests, refused writes, and tokens.

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
- [ ] Run the targeted V5 live config and compare against V4, `peer_contract`,
      and `adaptive_lease`.

## V3: External Mediation Protocol

- [ ] Convert the protocol into adapter-facing hooks:
      `on_read`, `on_write_intent`, `decision`, `on_write_committed`, and
      `on_agent_done`.
- [ ] Implement one external adapter that emits compatible events.
- [ ] Keep external runtimes without these hooks as Level C black-box checks.
- [ ] Document which results are strategy-comparable and which are only
      correctness/wall-clock smoke checks.

## Evaluation Plan

- [x] First run offline scripted tests.
- [ ] Then run a tiny smoke grid with `peer_contract` and `peer_broker`.
- [x] Add a targeted sensitivity config for race-heavy tasks.
- [ ] Run the targeted sensitivity grid on race-heavy tasks.
- [ ] Compare against `naive`, `notify`, `file_lock`, `git_hash`, and `ast_dep`.
- [ ] Treat the strategy as successful if it improves hard race correctness,
      avoids file-lock false-positive stalls on benign overlap, and produces
      interpretable replay evidence at acceptable token/runtime cost.
