# RaceBench: a neutral benchmark for multi-agent coding coordination

> Submission write-up, structured by the five judging pillars. ~1,000 words.
> Numbers marked [TBD] are filled from `results/grid-v1/comparison_table.md`
> after the real-model grid completes.

## 1. Problem

Parallel LLM coding agents are now a shipping product category (Cursor
background agents, Claude Code subagents, Devin), and the moment two agents
mutate the same repository they inherit every classical concurrency failure —
lost updates, stale reads, write-write clobbers — plus new agent-specific ones.
Several mechanisms have been proposed: CRDT convergence (CodeCRDT,
arXiv:2510.18893), git-hash optimistic concurrency (MegaAgent, arXiv:2408.09955),
LLM-advisory notifications (CoAgent, arXiv:2606.15376). Each is evaluated *by
its own authors, on its own task suite, with its own metrics*. The one formal
treatment (arXiv:2606.17182) says it outright: "the present generation of agent
benchmarks does not stress-test inter-agent shared state under contention."

**Success criteria (defined before building):** (a) one harness runs ≥4
coordination strategies unchanged on the same tasks; (b) every metric is
computed from a committed, replayable event log; (c) the suite contains at
least one task where the correct coordination behavior is *doing nothing*, so
over-coordination is measurable, not just under-coordination.

## 2. Approach

We are deliberately the baseline paper, not a new mechanism. The harness is a
minimal instrumented agent loop where **every read and write flows through a
pluggable coordination strategy** — which gives 100% read-set visibility by
construction (CoAgent's related work reports HTTP-sniffing sees only ~26% of
reads on SWE-bench workloads).

Strategies (each ~100 lines, labeled "X-style" — our reimplementations, not
the authors' systems): `naive` (floor), `file_lock`, `git_hash`
(MegaAgent-style read-snapshot + 3-way merge + surfaced conflicts),
`ast_scope` (symbol-level write claims via AST diff), and `notify`
(CoAgent-lite: unblocked writes plus advisory notifications to readers whose
read set the write intersects, with the reader's LLM judging relevance —
CoAgent's core idea without its serialization pre-order or saga inverses).
The AST idea is prior
art — Grit, Phantom, Weave, and arXiv:2603.24284 all do structural conflict
detection — but none has been measured against alternatives on fixed tasks;
that neutral measurement is our contribution, not the mechanism.

Twelve tasks cover the taxonomy from arXiv:2606.17182 / CoAgent plus three
harness-extension modes. Core modes: stale-read/lost-update, **benign
overlap** (disjoint functions, same file — correct behavior is zero
coordination), write-write clobber, 4-agent causal cascade, cross-file
interface change (invisible to file-scoped strategies), CooperBench-style
feature pair, antidependency/rw-canary, lock livelock stress, and
overhead-masks-benefit (disjoint packages). Extension modes: phantom-tool
registry drift, irreversible effect reordering, and split-view worktree
divergence. Each ships a collision map, hidden pytest oracle, and reference
solution. The paid real-model grid has not been re-run on the expanded suite
yet — offline scripted tests + reference oracles only for this expansion.

**Ruled out and why:** a full CRDT substrate (Yjs infrastructure exceeds the
window; CodeCRDT's own results are confounded by 82–189% code-volume
inflation); CoAgent's full MTPO (saga inverses beyond our effect loggers);
8+ agents (cost). CooperBench (arXiv:2601.13295) already covers the
*communication* axis with 652 tasks; we hold communication at zero and vary
the *mechanism* — complementary, not competing.

## 3. Evidence

Mechanics are pinned by 72 automated tests plus deterministic scripted-agent
trials (no API needed, committed under `results/smoke-*`):

- naive + stale whole-file writes silently loses one agent's feature
  (oracle 3/6) — the textbook lost update, reproduced;
- git_hash on identical writes: merged, 6/6, **zero silent losses**;
- benign overlap: file_lock stalls (1 FP stall/trial), ast_scope zero stalls;
  the FP classifier correctly labels t1's same-symbol stalls as true positives.

Real-model grid (gpt-5-mini, 6 tasks × 4 strategies × {2,4} agents × 5 reps):
correctness [TBD], tokens [TBD], wasted-work rate [TBD], FP stall rate [TBD].
Headline metric: **false-positive stall rate** — coordination events between
agents whose applied writes changed disjoint symbol sets. No prior paper
reports this number; Weave self-reports a ~95% false-conflict reduction but has
never been independently measured.

## 4. Constraints

Cost is a first-class design constraint: the runner enforces a hard USD/token
budget and resumes idempotently (existing logs are skipped), so a run killed by
the budget guard loses nothing. The full grid is ~200 trials; at gpt-5-mini
prices the projected cost is [TBD, est. <$25]. A calibration mode (one solo
agent doing all subtasks, naive strategy) gates the grid: we require >80% solo
pass rate per task before spending on the concurrency cells, so weak-model
noise cannot masquerade as coordination failure. Lock waits are bounded and
timeouts logged (deadlock becomes a datum, not a hang); trials are wall-clock
capped; every trial runs in a throwaway git workspace.

## 5. Honesty & Trajectory

**Taxonomy coverage (11 modes → tasks):** stale read → t1; benign overlap →
t2; write-write → t3; cascade → t4; cross-file → t5; feature pair → t6;
antidependency → t7; livelock → t8; overhead confound → t9; phantom tool →
t10; irreversible effects → t11; split-view → t12. Grid numbers above still
reflect the pre-expansion six-task run until the paid grid is re-executed.

Known limits: (1) twelve purpose-built tasks are a probe suite that isolates
failure modes, not a general benchmark — external validity is bounded and we
say so. (2) Strategies are our minimal reimplementations; results
characterize the *mechanism class*, not the cited systems. (3) Symbol
granularity is top-level only (a class is one symbol), so ast_scope
over-serializes within classes — visible in t6 and reported, not hidden.
(4) Scripted-agent results validate mechanics only; all headline claims come
from real-model trials with the event logs committed. (5) The solo-calibration
ceiling means results say little about tasks models can't do alone.
(6) Split-view merge is sequential git merge (force-integrate on conflict);
we do not claim a production CRDT/OT integrator.

Next: re-run the paid grid on t1–t12; port 2–3 real CooperBench tasks for
external validity; a second model family; cascade at 8 agents; deepen
`ast_scope` with a cross-file dep graph so t4/t5's visibility gap gets a
mechanism that can see it.

---

*Appendix pointers (not counted): metric definitions in `analysis/metrics.py`
docstring; per-task collision maps in `tasks/*/collision_map.yaml`; replay any
number in the tables from the committed JSONL logs via
`python -m analysis.make_report results/<run_id>`.*
