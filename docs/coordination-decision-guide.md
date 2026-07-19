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
| Benign same-file overlap is common | `naive`, `notify`, `adaptive_lease` | `file_lock` false-positive stalls |
| You need syntactic conflict diagnostics | `ast_scope`, `ast_dep` | Treat as probes, not correctness leaders |
| Cross-file semantic dependencies matter | `notify`, `adaptive_lease`, sometimes `file_lock` | Same-file-only AST scopes |
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

## Read AST strategies as diagnostics, not winners

`ast_scope` and `ast_dep` are useful because they isolate a narrower question:
what happens if coordination uses top-level Python symbols instead of whole
files?

They do show one real benefit: on benign same-file overlap, they avoid the
false-positive stalls that `file_lock` creates. That is a granularity result,
not an overall correctness win.

The correctness evidence is weaker. In the combined 9-strategy report,
`ast_scope` scores 49/80 and `ast_dep` scores 48/80, below `naive` at 56/80 and
below `adaptive_lease` at 63/80. So the practical read is not "AST solves
coordination." It is "pure syntax-level scope is a useful baseline, but not
enough."

Their implementation limits are visible too. The current versions are
top-level-symbol oriented, the import resolver is best effort, and class-internal
edits can still be over-serialized or missed. Use them to find where file-level
locking is too coarse, then compare against richer approaches such as
`adaptive_lease`, `git_hash`, or `file_lock`.

## Treat `adaptive_lease` as the promising extension

`adaptive_lease` is the most promising post-grid strategy. It tries to keep
file-lock safety while recovering finer granularity through symbol leases,
semantic-resource leases, and stale-overwrite refusal.

The current evidence is broader than the first targeted smoke. In the full
extension run, `adaptive_lease` scored 63/80, or 78.8%. That beats `naive`,
`ast_scope`, and `ast_dep`, but it does not beat `file_lock`, `git_hash`, or
`peer_contract`.

So the practical read is "promising hybrid", not "proven winner." The next
useful step is focused improvement on weak cells such as `t08`, `rw_b`, and
`rw_d`, plus an obligation-carrying version that keeps preservation promises
visible until agents finish.

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
