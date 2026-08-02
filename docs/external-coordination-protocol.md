# External coordination protocol

This document exists to prevent one common misread: a Level C adapter is not
automatically a comparable coordination strategy. It becomes comparable only
when RaceBench can mediate the external system's reads and write intents.

RaceBench has two different extension stories:

| Level | What is comparable? | What RaceBench can claim |
|---|---|---|
| **A: Instrumented strategy** | Coordination mechanism | Apples-to-apples strategy metrics: correctness, tokens, stalls, false-positive stalls, read-set visibility |
| **C: Black-box runtime** | Whole external agent system | Oracle correctness and wall clock on the same tasks |

Level C is useful, but it is not a comparable strategy column by default. When
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

## Cursor SDK: observe vs mediate

Cursor's public SDK (TypeScript `@cursor/sdk` / Python `cursor-sdk`) exposes two
surfaces that matter for Level C. Neither is wired in the shipped RaceBench
`cursor` adapter yet (`Agent.prompt` + final usage only).

### Observe: stream tool calls

`agent.send(...)` returns a `Run` whose `stream()` / `messages()` iterator emits
normalized events, including `tool_call` with `name`, `status`, `args`, and
`result`. Built-in tools include read / write / edit / shell / grep / glob and
related workspace actions. Logging these into RaceBench JSONL (or a sidecar)
upgrades black-box C1 from oracle-only outcomes to auditable trajectories.

Important limits:

- Tool `args` / `result` shapes and even tool **names** are not a stable public
  contract; parse defensively.
- A completed `tool_call` is **after or during** the action. Observation alone
  does not give RaceBench a chance to `stall` / `merge` / `notify` before the
  workspace mutates, so FP-stall and strategy-column metrics remain unavailable.

### Mediate: project hooks

Cursor [hooks](https://cursor.com/docs/hooks) (`.cursor/hooks.json` in the trial
cwd, e.g. `preToolUse`, `beforeShellExecution`, `afterFileEdit`) can block,
modify, or audit tool use. That is the practical bridge to this protocol:

| RaceBench hook | Cursor surface (approximate) |
|---|---|
| `on_read` | `preToolUse` / completed `tool_call` for read-like tools |
| `on_write_intent` + `decision` | `preToolUse` (or edit/write gate) that can **deny** until RaceBench returns `allow` / `stall` / … |
| `on_write_committed` | `afterFileEdit` or completed write/edit `tool_call` |
| `on_agent_done` | run completion / agent dispose |

Until that bridge exists, keep Cursor cells as `mode: external` / `ext_cursor`.
After it exists and emits RaceBench `read` / `write` / `coord` events, a Cursor
row may enter strategy-style rollups under the same honesty rules as Level A.

See also [`adding-an-external-runtime.md`](adding-an-external-runtime.md)
(Cursor C1 today; planned stream/hooks upgrades).
