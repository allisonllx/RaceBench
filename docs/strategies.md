# Level A strategies

All strategies implement the same interface (`harness/strategies/base.py`) and are
labeled "X-style": faithful-but-minimal reimplementations, not the original authors'
systems. RaceBench covers **nine coordination mechanism classes**. The first six
make up the committed `grid-v1` baseline; the last three are post-grid extensions
evaluated in targeted and extension runs.

For claim-level narrative and iteration notes, see
[`writeup/writeup_1000.md`](../writeup/writeup_1000.md) (Strategy Catalog appendix).
To add a new strategy, follow [`adding-a-strategy.md`](adding-a-strategy.md).

## Baseline (`grid-v1`)

1. `naive`: direct writes, last write wins. The floor.
2. `file_lock`: file-level lock on first touch, held until the agent finishes.
3. `git_hash`: MegaAgent-style optimistic concurrency: record content at read, 3-way
   merge on write, surface conflicts back to the agent.
4. `ast_scope`: symbol-level write claims via Python AST diff (Grit/Phantom/Weave-style;
   see [`prior-art.md`](prior-art.md)): two agents editing disjoint functions in the
   same file never stall.
5. `ast_dep`: `ast_scope` plus a workspace import/use dependency graph: stalls when a
   write races a claimed cross-file definition or use-site.
6. `notify`: CoAgent-lite advisory notifications: writes land immediately; agents whose
   read set intersects a landed write get a notice injected into context and self-judge.

## Post-grid extensions

7. `peer_contract`: voluntary mediated peer negotiation. Agents can call
   `declare_intent` before editing and `ack_contract` after receiving an overlap
   notice. Overlapping writes wait for peer ACK; disjoint declared edits can proceed.
8. `peer_broker`: forced mediated peer negotiation. The runtime detects an
   overlapping write, opens a private broker decision with affected peers, and
   applies the write unless peers report a true conflict. Peers can request
   concrete constraints that are cached as obligations, mark the write irrelevant
   to their subtask, or reject the write.
9. `adaptive_lease`: conservative adaptive locking. Precise function/class
   edits get symbol leases, uncertain module/file edits fall back to a file
   lease, semantic resources can be declared or inferred across files, and stale
   whole-file overwrites are refused rather than silently clobbering another
   agent's landed work.

`peer_contract` and `peer_broker` are intentionally separate, like `ast_scope`
and `ast_dep`: they test whether voluntary negotiation is enough, and whether a
runtime-triggered broker is worth the extra turn and token cost.
`adaptive_lease` is a separate hybrid: it asks whether `file_lock` safety can be
kept while recovering some `ast_scope` granularity.

Plans: [`adaptive-lease-strategy-plan.md`](adaptive-lease-strategy-plan.md),
[`peer-contract-strategy-plan.md`](peer-contract-strategy-plan.md).
How to run targeted / extension grids:
[`running-experiments.md`](running-experiments.md).

## Log note (`peer_broker`)

Normal agent turns are positive. `peer_broker` may emit `llm_usage` with
`phase: "broker"` and `turn: -1`, `-2`, etc. Those are private broker decision
calls outside the normal agent tool loop, not negative progress.

## Adding a strategy (summary)

Implement `_coordinate_read` and `_coordinate_write`, register with `@register`,
import in `harness/strategies/__init__.py`, add the name to `strategies:` in a
runner config, and smoke-test with `runner/configs/config.smoke.yaml` (scripted
agents, no API key). Strategies can also expose optional strategy-owned tools
through `extra_tool_schemas()` / `handle_strategy_tool(...)`, or use private
broker callbacks through `request_negotiation(...)`.

Full checklist: [`adding-a-strategy.md`](adding-a-strategy.md).

## Out of scope (hackathon window)

Reasons in `writeup/`: full CRDT substrate; CoAgent's full MTPO with serialization
pre-order and saga inverses; 8+ agent scale; lock-on-write-only `file_lock` and
`git_hash`+worktree hybrids (redundant with `ast_scope` / task-level
`isolation: worktree`).
