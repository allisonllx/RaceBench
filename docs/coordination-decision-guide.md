# Coordination decision guide

This guide turns the `results/grid-v1/` evidence into practical advice for
building multi-agent coding systems. It is not a universal ranking; RaceBench
shows that coordination value is selective.

## Use coarse locks when correctness beats parallelism

`file_lock` is the safest shipped baseline on many hard clobber and ordering
tasks. In the Level A grid it cleanly fixes the hardened whole-file races
(`t01_stale_clobber`, `t03_fetch_clobber`) and does well on irreversible effects
(`t11_irreversible`).

The cost is over-coordination. On benign same-file work (`t02_benign_overlap`,
`rw_c_benign_overlap`) file locks pass the oracle but add false-positive stalls.
Use this style when serializing shared files is acceptable and silent loss is
more expensive than waiting.

## Use notification-style coordination for cheap invalidation

`notify` lets writes land immediately, then warns agents whose read sets overlap
the write. In this suite it is cheap on wall clock and useful on some
antidependency cases, especially `rw_d_tag_antidependency`.

It is not a universal repair mechanism. If the agent ignores, misunderstands, or
cannot act on a notice, correctness still fails. Use notifications when
replanning is cheap and the agent loop is strong enough to self-correct.

## Keep `naive` as a real baseline

High `naive` correctness on benign/disjoint tasks is not a bug. Some concurrent
work should not coordinate at all. `naive` is the floor that reveals whether a
coordination mechanism is buying correctness or just adding latency.

If a task already passes under `naive`, the interesting metric is overhead:
tokens, wall clock, stalls, and false-positive stalls.

## Use finer granularity when false positives matter

`ast_scope` and `ast_dep` show the value of moving below file-level locking.
They avoid benign same-file stalls that `file_lock` creates, and `ast_dep` adds
cross-file awareness for dependency races.

Their limits are visible too: the implementation is top-level-symbol oriented,
the import resolver is best effort, and class-internal edits can still be
over-serialized or missed. Treat AST/dependency strategies as evidence for the
shape of a better mechanism, not as a finished production coordinator.

## Read Level C separately

External runtime cells such as Cursor C1 answer a different question: can a real
worker loop survive RaceBench tasks under a fixed split? They do not become
strategy columns unless the runtime exposes a mediation protocol around reads
and writes. See `docs/external-coordination-protocol.md`.

The practical rule: compare strategy rankings in Level A; use Level C as an
external-validity check on whether the seeded collisions still matter outside
RaceBench's toy tool API.
