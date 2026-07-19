# Coordination decision guide

This guide turns RaceBench results into practical advice for building
multi-agent coding systems. It is not a universal ranking. RaceBench shows that
coordination value is selective: the right mechanism depends on the failure mode
you are trying to prevent.

Use Level A results for strategy rankings. Use Level C results, such as Cursor
or MegaAgent runs, as black-box runtime checks unless the external runtime emits
RaceBench-compatible read, write, and coordination events.

## Choose by failure mode

| Situation | Prefer | Watch out |
|-----------|--------|-----------|
| Silent lost updates are unacceptable | `file_lock`, `git_hash` | `naive` |
| Reads may go stale after another agent writes | `notify`, `adaptive_lease` | Pure locks if replanning is cheap |
| Benign same-file overlap is common | `ast_scope`, `ast_dep`, `adaptive_lease` | `file_lock` false-positive stalls |
| Cross-file semantic dependencies matter | `notify`, `adaptive_lease` | Same-file-only AST scopes |
| Agents need to agree on an interface | `peer_contract` | Forced broker as the default |
| You need a floor for comparison | `naive` | Removing it from the table |

## Treat `naive` as the floor, not a strawman

`naive` is important because some concurrent work should not coordinate at all.
High `naive` correctness on benign or disjoint tasks is not a benchmark bug. It
is the signal that coordination can be unnecessary or even harmful.

If a task already passes under `naive`, the interesting metrics are overhead:
wall clock, tokens, stalls, wasted work, and false-positive stalls.

## Treat `file_lock` as the safety baseline

`file_lock` is the simplest strong correctness baseline. It cleanly fixes the
hardened whole-file races (`t01_stale_clobber`, `t03_fetch_clobber`) and does
well on irreversible ordering tasks such as `t11_irreversible`.

The tradeoff is over-coordination. On benign same-file work, file locks can pass
the oracle while still creating false-positive stalls. Use this style when
silent loss is worse than waiting.

## Treat `git_hash` as the optimistic baseline

`git_hash` is useful when agents usually edit independently, but conflicts
should be surfaced instead of silently overwritten. It is less eager than
`file_lock`, more protective than `naive`, and easier to reason about than a
large semantic coordinator.

In practice, this is a good default to compare against when you want optimistic
concurrency with replayable conflict evidence.

## Use `notify` for cheap invalidation

`notify` lets writes land immediately, then warns agents whose read sets overlap
the write. In this suite it is useful on some antidependency cases, especially
`rw_d_tag_antidependency`.

It is not a universal repair mechanism. If the agent ignores, misunderstands, or
cannot act on a notice, correctness can still fail. Use notifications when
replanning is cheap and the agent loop is strong enough to self-correct.

## Read AST strategies as evidence for granularity

`ast_scope` and `ast_dep` show why coordination below file-level locking matters.
They avoid benign same-file stalls that `file_lock` creates, and `ast_dep` adds
some cross-file awareness through dependency edges.

Their implementation limits are visible too. The current versions are
top-level-symbol oriented, the import resolver is best effort, and class-internal
edits can still be over-serialized or missed. Treat them as evidence that
finer-grained coordination helps, not as finished production coordinators.

## Treat `adaptive_lease` as the promising extension

`adaptive_lease` is the most promising post-grid strategy. It tries to keep
file-lock safety while recovering finer granularity through symbol leases,
semantic-resource leases, and stale-overwrite refusal.

The current evidence is encouraging but early. It should be described as a
promising hybrid, not a proven winner. The next useful step is more repetitions
on the targeted slice and an obligation-carrying version that keeps preservation
promises visible until agents finish.

## Use `peer_contract`, not `peer_broker`, for the A2A story

`peer_contract` is the cleaner peer-negotiation result. Agents voluntarily
declare edit intent and ACK compatible work before overlapping writes. That maps
better to the practical A2A idea: agents should share intent when they know they
are touching an interface or shared surface.

`peer_broker` is now best treated as a diagnostic ablation. The targeted V2.5 run
showed that forced negotiation can recover hard overlaps, but the full extension
grid showed poor generalization: `peer_broker` scored below `naive` overall and
was especially weak on `t04`, `t05`, `t11`, `t12`, and `rw_c`.

The lesson is not "never negotiate." The lesson is that forced negotiation
should not be the default trigger. The likely better design is hybrid: adaptive
semantic leases first, broker only for ambiguous conflicts that need peer
judgment, followed by a mandatory re-read before commit.

## Read Level C separately

External runtime cells such as Cursor C1 answer a different question: can a real
worker loop survive RaceBench tasks under a fixed split? They do not become
strategy columns unless the runtime exposes a mediation protocol around reads
and writes. See `docs/external-coordination-protocol.md`.

The practical rule: compare strategy rankings in Level A; use Level C as an
external-validity check on whether the seeded collisions still matter outside
RaceBench's toy tool API.
