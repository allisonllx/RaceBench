# External coordination protocol

RaceBench has two different extension stories:

| Level | What is comparable? | What RaceBench can claim |
|---|---|---|
| **A: Instrumented strategy** | Coordination mechanism | Apples-to-apples strategy metrics: correctness, tokens, stalls, false-positive stalls, read-set visibility |
| **C: Black-box runtime** | Whole external agent system | Oracle correctness and wall clock on the same tasks |

Level C is useful, but it is not an "external strategy" column by default. When
Cursor, MegaAgent, Claude Code, Devin, or a shell command edits the workspace
directly, RaceBench cannot mediate every read and write. Shared-isolation C1 is
therefore closest to Level A `naive` plus a foreign worker loop, model, and edit
policy. That is an external-validity check, not a mechanism comparison.

## When a runtime can become a strategy column

An external system can be compared as a coordination strategy only if every
agent read and write intent crosses a RaceBench-compatible mediation boundary.
The minimum protocol is:

| Hook/event | Purpose |
|---|---|
| `on_read(agent_id, path, content_hash, symbols)` | Tell the coordinator what an agent observed |
| `on_write_intent(agent_id, path, old_hash, touched_symbols, proposed_content)` | Ask before mutating shared state |
| `decision` | Coordinator returns `allow`, `stall`, `conflict`, `merge`, or `notify` |
| `on_write_committed(agent_id, path, new_hash, touched_symbols)` | Confirm what actually landed |
| `on_agent_done(agent_id)` | Release locks, claims, or subscriptions |

The protocol does not require the external runtime to expose prompts or private
reasoning. It does require a complete mediation path for filesystem state, so
RaceBench can attribute stalls, conflicts, notifications, and false positives to
the mechanism rather than to the worker loop.

## Event compatibility

Adapters that implement the protocol should emit normal RaceBench JSONL events:

- `read` for mediated reads
- `write` for applied, merged, refused, or conflicted writes
- `coord` for stalls, notifications, merge conflicts, and timeouts
- `trial_start` with `mode: "strategy"` or no `mode` field

Adapters that do not implement this protocol should keep `mode: "external"` and
use synthetic strategy ids such as `ext_cursor`. Their results belong in Level C
black-box runtime sections, not in Level A strategy rollups.

## Why this boundary matters

Without mediation, an external runtime that passes a hard RaceBench task may be
better because it rereads more often, uses smaller edits, has a stronger model,
or recovers from failed writes. Those are valuable system properties, but they
are not evidence that the runtime's coordination mechanism outperformed
`git_hash`, `file_lock`, `notify`, or another Level A strategy.

RaceBench keeps the claim narrower: Level A compares mechanisms with full
visibility; Level C checks whether real worker stacks survive the same seeded
collisions under fixed RaceBench briefs.
