# RaceBench: a neutral benchmark for multi-agent coding coordination

> Structured by the five judging pillars. Length is above the usual ~1k-word
> target while we document incidents and reasoning. Headline numbers below come
> from committed `results/grid-v1/` logs (`comparison_table*.md`, `trials.csv`).
> Cost (USD) is derived at report time from `trial_end` token counts; old JSONL
> logs do not need re-running.
>
> Reader map: Sections 1-4 make the core benchmark claim. Section 5 is the
> honesty section: it explains why Level A is the strategy comparison, why Level
> C is only black-box runtime scoring, and where the benchmark breaks.

## 1. Problem

Parallel coding agents are no longer hypothetical. Cursor background agents,
Claude Code subagents, Devin-style systems, and similar tools all make it easy
to run more than one agent on the same repository.

That creates a familiar software problem in a new setting. If two agents read
and edit the same files at the same time, one agent can overwrite the other's
work, make decisions from stale code, or block safe parallel work for no reason.

Several coordination mechanisms already exist: CRDT-style convergence
(CodeCRDT, arXiv:2510.18893), git-hash optimistic concurrency (MegaAgent,
arXiv:2408.09955), and LLM-advisory notifications (CoAgent, arXiv:2606.15376).
The problem is that each paper evaluates its own mechanism on its own tasks with
its own metrics.

RaceBench asks for a neutral comparison and a design testbed. The taxonomy paper
(arXiv:2606.17182) says current agent benchmarks do not stress-test shared
state under contention. RaceBench is my attempt to make that contention visible
and measurable, then use it to test whether new coordination ideas really help
or only move the failure into more stalls, more tokens, slower runs, or hidden
over-coordination.

**Success criteria (defined before building):**

1. One harness runs at least four coordination strategies unchanged on the same tasks.
2. Every metric is computed from a committed, replayable event log.
3. The suite contains at least one task where correct coordination is *doing
   nothing*, so over-coordination is measurable, not only under-coordination.

## 2. Approach

RaceBench is deliberately a benchmark first, not a new coordination mechanism.
It runs the same tasks under different coordination policies and records what
happens.

The core design is simple: every agent read and write goes through a pluggable
strategy. I call this Level A. Because the harness owns the file tools, it can
see every `read_file` and every write. That gives full visibility for the
strategy comparison.

This matters because observing agent reads from outside is hard. CoAgent's
related work reports that HTTP-sniffing sees only about 26% of reads on
SWE-bench workloads.

### Coordination strategies

Each strategy is intentionally small. The labels are "X-style" because these
are minimal reimplementations of mechanism classes, not the original authors'
full systems. The headline `grid-v1` table uses six baseline strategies:

| Strategy | Mechanism |
|----------|-----------|
| `naive` | Direct writes; last writer wins (floor) |
| `file_lock` | File-level lock on first touch, held until agent finishes |
| `git_hash` | MegaAgent-style read snapshot + 3-way merge + surfaced conflicts |
| `ast_scope` | Same-file symbol claims via AST diff |
| `ast_dep` | `ast_scope` plus import/use dep graph (cross-file races on t04/t05/t07) |
| `notify` | CoAgent-lite: writes land immediately; advisory notices to intersecting readers |

AST-level claims are prior art (Grit, Phantom, Weave, arXiv:2603.24284). The
missing piece is a neutral comparison against other coordination styles on the
same tasks. That comparison is the contribution here.

I keep `ast_scope` and `ast_dep` as separate columns because they answer a
specific question: how much does the dependency graph add beyond same-file
symbol claims?

After the main grid, RaceBench adds three post-grid extensions:

| Strategy | Mechanism |
|----------|-----------|
| `peer_contract` | Voluntary agent-to-agent negotiation with declared intent and peer ACKs |
| `peer_broker` | Forced brokered negotiation with cached obligations |
| `adaptive_lease` | Semantic adaptive locking with symbol/resource leases |

Together, the project now covers **nine mechanism classes**.

The extension strategies are not claimed as invented from scratch. Peer
negotiation connects to older multi-agent negotiation work such as Contract Net
and POANCD. Adaptive leases connect to database and systems work on lock
granularity, semantic locking, and adaptive locks. The RaceBench contribution is
adapting those ideas to LLM coding agents at the file-tool boundary and measuring
their correctness, cost, latency, and false-positive stalls on the same tasks.
The README lists the specific prior-art sources.

### Task suite: how we built it

The task suite starts from the failure modes described in arXiv:2606.17182 and
CoAgent. For each failure mode, I built a tiny repository that tries to isolate
one kind of race.

The goal is attribution. If a strategy fails, I want to know whether it failed
because of coordination, not because the app itself was too hard.

That produced **t01 through t12**. Each task has a seeded repository, fixed agent
briefs, a collision map, a hidden pytest oracle, and a reference solution. In
this writeup, "oracle" means the hidden test suite that decides whether the
final repository is correct.

| Mode | Task | Why it exists |
|------|------|---------------|
| Stale read / lost update | `t01_stale_clobber` | Whole-file rewrite race (hardened; v1 archived) |
| Benign overlap | `t02_benign_overlap` | Correct coordination is *do nothing* (false-positive stalls) |
| Write-write clobber | `t03_fetch_clobber` | Whole-`fetch` rewrite race (hardened; v1 archived) |
| Causal cascade | `t04_cascade` | 4-agent dependency chain |
| Cross-file interface | `t05_cross_file` | Invisible to file-scoped locks / same-file AST |
| Feature pair | `t06_feature_pair` | CooperBench-style coupled features |
| Antidependency / rw-canary | `t07_rw_canary` | Read-write ordering hazard |
| Lock livelock | `t08_livelock` | Coordination thrash under contention |
| Overhead confound | `t09_overhead` | Disjoint packages; cost without benefit |
| Phantom tool / registry | `t10_phantom_tool` | Tool surface drifts |
| Irreversible effects | `t11_irreversible` | Ordering of non-rewindable side effects |
| Split-view worktrees | `t12_split_view` | Isolation until end merge |

**Hardening t01 and t03.** The first versions of `t01` and `t03` were too easy.
gpt-5-mini often used anchored `edit_file` calls, and those edits composed
cleanly even under `naive`.

That meant the task was not reliably testing stale whole-file writes. I archived
those versions under `tasks/_archive/` and replaced them with hardened siblings
that require whole-file `write_file` from the agent's last read.

**Conduit track (added later).** The first tasks were useful probes, but they
were very small. Real coding work usually has layered imports, shared schemas,
and serializers between routes and storage.

To add structure without losing reproducibility, I added a trimmed
RealWorld-inspired Conduit app using FastAPI, SQLite, and Pydantic. It adds four
denser races: `rw_c` benign same-file overlap, `rw_b` signature drift, `rw_d`
tag-count antidependency, and `rw_e` a 3-agent cascade.

**Conduit limits (deliberate).** Conduit is still not a full production app. It
does not use Newman, Postgres, or long-running servers. The tests use FastAPI
`TestClient` and in-process SQLite.

This keeps the benchmark cheap and reproducible. Conduit improves structural
realism, but it does not claim full deployment realism.

**What I ruled out.** I did not build a full CRDT substrate. Yjs was too large
for the window, and CodeCRDT would introduce its own code-volume effects. I also
did not implement CoAgent's full MTPO saga layer because it needs inverse
operations and effect logging beyond this benchmark.

I also deferred 8+ agent tasks for cost. CooperBench (arXiv:2601.13295) already
studies the communication axis. RaceBench holds communication mostly fixed and
varies the coordination mechanism.

The real-model grid (`results/grid-v1/`, gpt-5-mini) covers t01-t12 + four
`rw_*` Conduit tasks. Offline scripted tests validate mechanics on every expansion.

## 3. Evidence

### Scripted mechanics (no API)

Before spending API tokens, I used cheap scripted trials under
`results/smoke-*` to check that the harness can reproduce the race patterns it
claims to measure.

The scripted checks cover four mechanics:

- **Lost update.** Under `naive`, stale whole-file writes silently lose one
  agent's feature. The oracle falls to 3/6, which confirms the probe works.
- **Optimistic merge.** Under `git_hash`, identical writes merge cleanly. The
  oracle passes 6/6 with zero silent losses.
- **False-positive stalls.** On benign same-file overlap, `file_lock` waits even
  though the edits are safe. `ast_scope` and `ast_dep` do not wait.
- **Cross-file dependency.** On `t05_cross_file`, `ast_scope` cannot see the
  dependency. `ast_dep` sees the edge, stalls, then finishes after release.

### Real-model grid (complete)

The main evidence is the gpt-5-mini grid in `results/grid-v1/`. It contains
**480 completed trials**: 16 tasks x 6 strategies x 5 repetitions.

Most tasks run with two agents. `rw_e_cascade` uses three agents, and
`t04_cascade` uses four agents, because those tasks are designed as dependency
chains.

You can regenerate the tables and static explorer with:

```bash
python -m analysis.make_report results/grid-v1
```

You can validate the logs with:

```bash
python -m analysis.validate_logs results/grid-v1 --expect-trials 480
```

**Spend and pass rate.** The full grid cost about **$13.56** and used about
**37.7M tokens**, under the $25 / 40M-token guardrail. The pooled oracle pass
rate was **74.4%** (357/480).

At n=2, by-strategy correctness ranges from **0.64** for `ast_dep` to **0.94**
for `file_lock`. The report command also emits bootstrap confidence-interval
tables and `results/grid-v1/report.html`.

**Post-grid 9-strategy extension.** I also ran a full extension grid after the
headline table to recognize the three new strategies on the same 16 tasks. The
combined artifact is `results/grid-v1-plus-extensions/`, built from
`results/grid-v1/` and `results/grid-v1-extensions-full/`.

This is not the 480-trial headline grid, because the strategies were added after
the baseline run. It is still valuable evidence. In the combined report,
`peer_contract` scores **67/80** (**83.8%**), `adaptive_lease` scores **63/80**
(**78.8%**), and `peer_broker` scores **51/80** (**63.8%**). That places
`peer_contract` close to `git_hash` (**68/80**) and below `file_lock`
(**72/80**), while `adaptive_lease` beats both AST strategies but does not
replace file locks.

**Cross-run checks.** I also generated `results/cross-run-analysis/` to compare
the OpenAI grid with the Agnes sensitivity run and the solo calibration run.
These are support checks, not replacements for the main grid.

On the eight overlapping Agnes sensitivity tasks, `agnes-2.0-flash` scores
**69.4%** versus **57.9%** for gpt-5-mini on the same Level A cells. It uses
fewer tokens on average (**74.9k** vs **97.8k**) but takes much longer wall time
(**219s** vs **81s**).

The solo comparison is cleaner. Solo calibration succeeds on **96.2%** of
trials, while parallel correctness drops under every strategy: `file_lock`
**90.0%**, `git_hash` **85.0%**, `notify` **80.0%**, `naive` **70.0%**,
`ast_scope` **61.2%**, and `ast_dep` **60.0%**. That means most tasks are
solvable by one agent; the failures become more informative when multiple
agents edit at once.

The speed story is not "parallel always wins." Solo calibration averages
**45.7s** and **44.5k** tokens per trial. Parallel `notify` averages **51.8s**
and **72.7k** tokens, and parallel `naive` averages **57.1s** and **78.3k**
tokens. Safer coordination costs more time: `git_hash` averages **63.0s**,
while `file_lock` averages **174.2s**. RaceBench makes that tradeoff explicit:
parallelism can buy coordination risk, extra tokens, or waiting unless the
mechanism fits the failure mode.

**Condensed strategy takeaways:**

| Scenario | Best current read |
|----------|-------------------|
| Hard lost updates or irreversible ordering | `file_lock` is the strongest safety baseline; `git_hash` is the optimistic baseline. |
| Benign or disjoint work | `naive`, `notify`, and `adaptive_lease` avoid file-lock over-coordination. |
| Stale reads / antidependencies | `notify` is cheap and useful when agents can re-read; `adaptive_lease` is promising but still uneven. |
| Pure same-file syntax scope | `ast_scope` / `ast_dep` are diagnostics, not correctness leaders. They show where file locks are too coarse, but not that AST scope wins overall. |
| Interface agreement between agents | `peer_contract` is the cleaner A2A result; `peer_broker` is an ablation after poor full-grid generalization. |

**Headline finding on t02.** `t02_benign_overlap` is the "do nothing" test. All
six baseline strategies pass the oracle 5/5, so correctness is not the signal.
The signal is unnecessary waiting. `file_lock` averages **1.0 false-positive
stall per trial**, while `ast_scope`, `ast_dep`, and `notify` average **0**.

**t12 after the worktree fix.** The fixed `t12_split_view` cells are in the main
grid. The pre-fix logs are archived. After the fix, all six baseline strategies
score **5/5** at n=2. See
[Incident: t12 worktree merge (fixed)](#incident-t12-worktree-merge-fixed) for
the postmortem.

**Headline metric.** RaceBench reports **false-positive stall rate**. This means
a coordination strategy blocked two agents even though their final applied
writes changed disjoint symbols.

I have not found a prior benchmark that reports this number directly. Weave
self-reports about 95% false-conflict reduction, but it has not been measured
independently on a fixed suite of coordination tasks.

### Reading a strong `naive` column

High pooled `naive` correctness does **not** mean the suite fails to seed races.
The suite is deliberately mixed:

- **Benign / overhead probes** (`t02`, `rw_c`, `t09`) should pass under naive.
  Their job is to expose false-positive stalls and cost, not lost updates.
- **Hard races** can break naive: hardened `t01`/`t03` show naive **0/5** vs
  `file_lock` **5/5**, and `rw_d` shows naive **1/5** vs notify **5/5**.

The archived v1 versions of t01 and t03 did not trigger the intended race often
enough. Models preferred anchored `edit_file` calls against the current file on
disk. When the anchors were in different regions, the edits composed under
`naive`.

That is why the hardened tasks force stale whole-file writes. This does not mean
I believe production agents always rewrite whole files. It means I wanted a
clean probe for the lost-update failure mode.

**Fair claim:** coordination value is selective. It appears on hard race cells,
and it also appears as wasted time when a mechanism over-fires on safe work.

**Unfair claim:** the tasks are invalid because `naive` works on the benign
half. That is intentional. The benign half is how RaceBench measures
over-coordination.

### Exploratory peer-negotiation extension

After the main grid, I tested a more agent-like idea: instead of only locking
files, can agents negotiate when their work overlaps?

This is inspired by automated negotiation protocols such as POANCD, but
RaceBench does not implement POANCD. The idea I borrowed is smaller: agents can
exchange intent and constraints before risky edits land.

I tested two Level A strategies:

| Strategy | Idea |
|----------|------|
| `peer_contract` | Voluntary negotiation. Agents declare edit intent and ACK compatible peer work. |
| `peer_broker` | Forced negotiation. The runtime detects an overlap and asks affected peers for a decision. |

These runs are post-grid extensions, not part of the 480-trial headline table.
The first targeted smokes used five high-signal tasks: `t02`, `t03`, `t04`,
`rw_d`, and `rw_e`.

The version names are conceptual. V1 is `peer_contract`. V2.x is the
`peer_broker` family. V3 is reserved for a future protocol that would let
external runtimes expose read and write intent events.

The early result favored the voluntary protocol. `peer_contract` reached **5/5**
on the targeted slice, while `peer_broker` reached **3/5**. Contract was also
cheaper: **85s vs 119s** mean wall time, **153k vs 170k** mean tokens, and
**2.6 vs 4.8** mean stalls.

The broker still taught us something useful. Its `ack_with_constraints` path
helped recover hard cases such as `t03_fetch_clobber` and `rw_e_cascade`. The
problem was that it asked for negotiation too often and created retry loops.

V2.4, stored under the raw `v4` result folder, narrowed the trigger and
clarified the decision language. A conflict now means "no final implementation
can satisfy both subtasks," not merely "two agents touched the same function."

That helped correctness, but not process health. In V2.4, both strategies
reached **4/5**, yet `peer_contract` was still cleaner: **79s vs 122s** mean
wall time, **155k vs 237k** mean tokens, **2.2 vs 4.6** mean stalls, and **1.6
vs 5.6** refused writes.

The clearest warning was `rw_e_cascade`. Broker passed the oracle, but the run
took **376s**, used **898k** tokens, had **17** stalls, and all three agents hit
`max_turns`. That is technically correct, but not a healthy coordination
mechanism.

V2.5, stored under the raw `v5` result folder, made broker less wasteful. It
records `ack_with_constraints` as a cached obligation instead of refusing the
write immediately. It also uses adaptive-lease semantic resources to avoid
asking peers about every broad read/write overlap.

On the targeted slice, V2.5 looked much better. `peer_broker` reached **5/5**,
mean wall time fell from **122s** to **71s**, mean tokens fell from **237k** to
**140k**, and refused writes fell from **5.6** to **0.6**. On `rw_e_cascade`, it
dropped from **376s / 898k tokens / 17 stalls / 22 refused writes** to **124s /
303k tokens / 5 stalls / 0 refused writes**.

The full extension grid changed the interpretation. In
`results/grid-v1-plus-extensions/`, `peer_broker` scored **51/80** (**63.8%**).
That is below `naive` at **56/80** (**70.0%**) and far below `peer_contract` at
**67/80** (**83.8%**).

The weak cells are especially worrying because they include tasks where
negotiation should help or at least stay out of the way: `t05_cross_file`
(**20%**), `t12_split_view` (**20%**), `rw_c_benign_overlap` (**60%**),
`t04_cascade` (**20%**), and `t11_irreversible` (**20%**).

The honest conclusion is that `peer_broker` is not a headline success. It is a
useful ablation. It falsifies the tempting idea that agents should always be
forced to negotiate when they overlap.

The better future design is hybrid: use adaptive semantic leases first, call the
broker only for ambiguous conflicts, require a re-read after negotiation, and
cap the exchange to one compact decision per peer.

### Exploratory adaptive-lease extension

The peer runs raised a practical question: can we keep the safety of
`file_lock` without locking whole files whenever a smaller unit would be safe?

`adaptive_lease` is my first answer. It is an experimental Level A strategy
added after the main 480-trial grid. It is not part of the headline table yet.

V1 was conservative. It used symbol leases for precise function or class edits.
If the edit was broad or uncertain, it fell back to a file lease. It also
refused stale whole-file overwrites when the file had changed after the agent's
last read.

On a six-task targeted slice (`t01`, `t02`, `t03`, `t04`, `rw_d`, `rw_e`), V1
went **3/6**. It passed the stale/clobber and benign-overlap probes, but missed
the cascade and semantic-dependency tasks.

That failure was useful. It showed that file and symbol leases help with
destructive writes, but they do not capture application concepts such as tag
normalization or article summary schema drift.

V2 adds a small semantic-resource layer. Agents can declare resources such as
`tag.normalization`, `article.summary.schema`, `api.fetch.signature`, or
`datasource.parse_dataset.public_api`. The strategy can also infer some of these
resources from paths, changed symbols, and code text.

This is not a general program-semantics engine. It is a small, inspectable
resource catalog used to test a narrower idea: can file-lock safety become more
granular if we add a little application-level knowledge?

The first V2 targeted run was **6/6** correct, with **0** false-positive stalls,
**56.0s** mean wall time, **104.7k** mean tokens, and **1.5** stalls per trial.

I then ran `adaptive_lease` in the full post-grid extension. That gives broader
evidence than the targeted slice, but it is still not a new headline winner.

Across the full extension grid, `adaptive_lease` scored **63/80** (**78.8%**).
That is better than `naive` (**56/80**), `ast_scope` (**49/80**), and `ast_dep`
(**48/80**), but below `file_lock` (**72/80**), `git_hash` (**68/80**), and
`peer_contract` (**67/80**).

The fair claim is now stronger than the original targeted-run conclusion.
Semantic leases beat the two AST strategies in the broader extension run and
remain a promising hybrid. The fair claim is still not "adaptive lease replaces
file lock," because file locks remain more correct overall on this grid.

## 4. Constraints

Cost shaped the benchmark. The runner enforces a **$25 / 40M-token** guardrail
and supports idempotent resume, so existing logs are skipped instead of rerun.

Every trial logs token counts at `trial_end`. The report command derives USD
from committed price tables in `run_meta.json` or `runner/config.example.yaml`.
For gpt-5-mini, the configured rates are $0.25/M input tokens and $2/M output
tokens.

The main `grid-v1` run spent about **$13.56** and used about **37.7M tokens**
across **480** trials, under the budget cap.

Calibration also limits wasted spend. Before a concurrency cell enters the grid,
one solo agent must solve the task under `naive` with more than 80% pass rate.
Lock waits are bounded, timeouts are logged, and every trial uses a throwaway
git workspace.

## 5. Honesty & Trajectory

### Extensibility

| Level | What plugs in | Status |
|-------|---------------|--------|
| **A: Strategy** | `_coordinate_read` / `_coordinate_write` under our agent loop | Shipped |
| **B: Task** | `tasks/<name>/` repo, oracle, collision map | Shipped |
| **C: External system** | Third-party multi-agent product; RaceBench owns workspace + oracle | Shipped (C1 bridges) |

Levels A and B are the clean benchmark. They produce the apples-to-apples
strategy table because the task, tools, logs, and metrics stay fixed. Only the
coordination mechanism changes.

For example, `git_hash` is MegaAgent-style optimistic concurrency. It is not a
run of MegaAgent's repository.

Level C is different. It asks whether an external agent runtime can edit the
RaceBench workspace and pass the oracle. That is useful, but it scores the whole
runtime, not just a coordination mechanism.

Level C does not produce comparable false-positive stall or read-set metrics
unless the adapter emits RaceBench-style events. A read set is simply the set of
files an agent observed before writing. I split Level C into two labeled
sub-modes:

| Mode | Shape | Status |
|------|-------|--------|
| **C1: Harness-swap** | Fixed RaceBench split; external worker edits | Shipped |
| **C2: Single-goal emergent** | One seed prompt; runtime chooses whether to parallelize | Deliberately unbuilt |

**C1** keeps the same task split as Level A. RaceBench still decides which agent
gets which brief. The external runtime only supplies the worker loop that edits
the files.

This means C1 is not measuring a product's full orchestrator. It does not test
Cursor's multitask planner or MegaAgent's CEO-style recruitment. It tests how a
foreign worker stack behaves under RaceBench's fixed split.

On shared-isolation tasks, the vendor agents share one working directory and can
overwrite each other. On worktree tasks, each agent gets its own directory from
`paths.json`, and RaceBench merges the result.

**Purpose of C1.** C1 is closest to Level A `naive` plus a foreign worker stack.
The tools, loop, and often model are different, but RaceBench still provides the
split. That makes C1 an external-validity check, not a strategy column:

- If a hard race (e.g. hardened t01/t03) that fails under Level A `naive` also
  fails under Cursor C1, the collision is not an artifact of our toy tool API.
- If Cursor C1 passes where `naive` fails, the interesting claim is capability /
  edit granularity / re-read habit, not "Cursor coordinated the agents."
- Strategy rankings, false-positive stalls, and read-set metrics stay in Level
  A. To vary the model with full visibility, swap the model under Level A; do
  not bolt RaceBench strategies onto native Cursor tools.

C1 cells are exploratory and stay off the Level A comparison table. Hard tasks
are the most useful C1 smokes. Easy cells where `naive` already passes 100% add
little signal.

**Preliminary Cursor C1 smoke (`results/ext-cursor/`, n=1 per cell, rep=0).**
One composer-2.5 pass across 16 tasks: **15/16** oracle-correct. The sole miss is
**t03_fetch_clobber** (3/5; `fetch()` signature missing `timeout` / kwargs not
accepted). Notable vs Level A `naive` on the same tasks (gpt-5-mini, 5 reps):

| Task | Level A `naive` | Cursor C1 (1 pass) |
|------|-----------------|---------------------|
| `t01_stale_clobber` | 0/5 | pass (6/6) |
| `t03_fetch_clobber` | 0/5 | fail (3/5) |
| `rw_e_cascade` | 0/5 | pass (3/3) |
| `t04_cascade` | 4/5 | pass (7/7) |

Cursor uses many more prompt tokens than a Level A trial, often **10-50x** more.
For example, t02 is about 93k tokens in Cursor C1 versus about 14k in one Level
A trial. t11 is about 1.08M versus about 30k.

That is consistent with a heavier worker loop that reads and edits more. It is
not evidence that RaceBench injected coordination into Cursor.

**How to read this.** Comparing Level A `naive` to Cursor C1 is harness versus
harness. It compares RaceBench's instrumented tools and gpt-5-mini against
Cursor's local agent loop and composer model.

A Cursor pass where Level A `naive` fails does not prove coordination is
unnecessary. It may mean Cursor's worker is better at avoiding or recovering
from that seeded race. A Cursor fail on t03 shows the collision can still bite a
stronger stack.

These cells are exploratory external validity checks, not headline evidence.
The core contribution remains Level A/B: same harness, vary mechanism.

If stronger agent stacks keep clearing hardened cells in one pass, the right
response is to add harder collision seeds in a future suite, not to fold C1 into
the strategy table.

I also shipped a MegaAgent vendor bridge (`adapters/megaagent/`) and a Cursor C1
adapter (`--adapter cursor`).

MegaAgent's early trials hit integration and alignment limits. On t02 it timed
out at 900s with zero file writes after CEO recruitment. On t04 it ran about
887s and about 2M input tokens, but the CEO ignored the RaceBench brief and
recruited a Gobang demo team.

I document those as adapter and alignment limits, not as evidence that MegaAgent
"failed" the RaceBench oracle. I do not patch MegaAgent upstream.

**C2 is deliberately unbuilt.** In C2, RaceBench would give one seed prompt and
let the product decide whether to split the work. That mostly measures planning
and decomposition, not coordination under a known collision.

A fair C2 would need to treat "did the product parallelize?" as its own outcome.
Otherwise a product that solves the task with one agent would look like it
failed a coordination test, which would be misleading.

That is a different benchmark design, and it is out of scope for this window.

**MegaAgent orchestration vs RaceBench task shape.** MegaAgent's headline claim
is dynamic org design. One CEO prompt recruits agents, decomposes work, and
scales the team without a predefined SOP.

RaceBench deliberately does the opposite. Every task names fixed `agent-*`
roles, fixed briefs, a seeded repo, and a hidden oracle. That is what keeps the
strategy comparison deterministic and replayable.

So Level C1 on RaceBench cannot fairly score dynamic role allocation or
open-ended decomposition. It only tests whether an external multi-agent runtime
can edit the RaceBench repo under contention and pass the oracle.

### Incident: t12 worktree merge (fixed)

**Symptom.** First real-model pass on `t12_split_view`: **0%** every strategy,
including cells where both agents finished and the log reported `worktree_merge`
`ok: true`, `conflicts: []`, `message: "clean"`. Oracle still missing `greet`.
A "clean" merge that still misses an agent's change means the harness lied about
integration.

**Root cause.** I was using fake worktrees: copied directories plus a shared git
index. Edits did not land on `agent/<id>` branches reliably, `.racebench_git`
was sometimes tracked, and the conflict path could fall back to last-writer-wins
whole-tree overwrite.

No coordination strategy can save a task if the final merge step is broken.

**Response.** I archived the invalid logs under
`results/grid-v1/_archive_t12_pre_worktree_fix/` and
`results/grid-v1-calibration/_archive_t12_pre_worktree_fix/`.

Then I fixed the merge path with per-agent indexes, `commit-tree` /
`update-ref`, per-file 3-way merge, an AST method-union helper, regression
tests, and worktree-specific prompts.

After the fix, t12 solo calibration was **5/5**, and the naive smoke was **2/2**.
Pre-fix t12 numbers must not appear in the comparison table.

The AST union is only a benchmark merge helper. It is not a production CRDT or
operational-transform integrator.

### Other limits

1. t01-t12 are small isolated tasks. Each focuses on one failure mode, so they
   do not reflect the full complexity of real-world repositories. Conduit adds
   more structure, but it is still not a full Newman/Postgres/live-server
   benchmark.
2. Strategy columns are simplified, inspired implementations of the mechanism
   classes. They are not direct runs of the original paper systems.
3. Roles and agent counts are predefined. This keeps the comparison stable, but
   it does not measure dynamic role allocation or adaptive team sizing.
4. Symbol granularity is top-level functions/classes only. Methods inside a
   class are treated as one class-level symbol, so `ast_scope` and `ast_dep`
   cannot distinguish two agents editing different methods of the same class.
   t06 shows this class-level logging on `cache/core.py`, although the task
   still passes in the main grid.
5. Scripted trials only check that the harness behaves as expected. The main
   benchmark claims come from JSONL logs produced by real model runs.
6. Solo calibration is a sanity check. If one agent usually fails a task even
   without concurrent edits, then a parallel failure should not be blamed mainly
   on coordination.
7. `ast_dep` builds an approximate dependency map from Python imports and
   top-level symbols. It can miss dependencies that require full type inference,
   dynamic imports, or runtime behavior.
8. Older timeout paths sometimes missed `trial_end` token totals. The validator
   reports fallback token accounting instead of hiding it.
9. `grep`, `glob`, and `list_files` bypass the strategy. Full read-set
   visibility applies to `read_file`, not every possible information channel.

### Next steps

The Level A/B grid for gpt-5-mini is shipped in `results/grid-v1/`. That is the
core comparison table.

The remaining work is optional extension work. I would prioritize it by expected
value rather than by how easy it is to add.

#### Priority 1: highest yield

1. **Hybrid adaptive lease plus peer fallback.** This is the strongest next
   strategy idea. `adaptive_lease` has better granularity than `file_lock`, while
   `peer_contract` is useful when two agents must preserve each other's intended
   behavior. The next version should try semantic leases first, call a peer only
   for ambiguous conflicts, require a re-read before commit, and keep short
   obligations such as "preserve timeout behavior" visible until `done`. This
   follows the open items in
   [`docs/adaptive-lease-strategy-plan.md`](../docs/adaptive-lease-strategy-plan.md)
   and
   [`docs/peer-contract-strategy-plan.md`](../docs/peer-contract-strategy-plan.md).

2. **Harder benchmark tasks.** The current suite isolates race modes well, but
   many tasks are still small. Cursor C1 passing some cells where Level A
   `naive` fails suggests that stronger worker loops may need harder seeds.
   Good additions would include 5-8 agent chains, fan-in/fan-out migrations,
   generated-client schema drift, and cases where one correct patch invalidates
   another agent's previously passing tests.

3. **One mediated Level C adapter.** Level C is currently black-box scoring
   unless an adapter emits RaceBench-compatible read, write, and coordination
   events. Implementing one adapter with `on_read`, `on_write_intent`,
   `decision`, `on_write_committed`, and `on_agent_done` would turn the external
   runtime story from "we can score products" into "we can compare a product's
   coordination boundary when it exposes the right hooks." See
   [`docs/adding-an-external-runtime.md`](../docs/adding-an-external-runtime.md).

#### Priority 2: useful, but not essential

4. **Agnes full grid.** The targeted Agnes sensitivity run is already enough to
   say the main baseline/high-signal conclusions were checked against a second
   OpenAI-compatible provider. A full 480-trial Agnes grid would be nice, but it
   is lower value than improving the strategy or task suite, and it does not need
   to include `peer_contract`, `peer_broker`, or `adaptive_lease`.

5. **More Cursor C1 repetitions.** The `results/ext-cursor/` cells are useful
   external-validity smoke checks, not strategy rankings. More reps on t01, t03,
   and rw_e would make the C1 story more stable if budget allows.

6. **Level C adapter hardening.** The MegaAgent bridge runs, but it is not
   production-ready. Useful fixes include upstream HTTP timeouts, live streaming
   of `log.txt`, fail-fast checks when agents go off-brief, and optional
   deterministic recruitment from RaceBench briefs.

#### Priority 3: nice to have or deferred

7. **Claude Code C1 adapter.** This would follow the same harness-swap pattern as
   Cursor: N headless `claude -p` processes, one brief each, with cwd from
   `paths.json`. Useful, but not required for the core contribution.

8. **C2 single-goal track.** Keep this named but unbuilt for now. A single-goal
   product run mostly measures planning and single-agent capability unless the
   runtime exposes coordination hooks.

9. **Cascade at 8+ agents.** This would be interesting, but it is cost-heavy.
   `t04` and `rw_e` already test smaller dependency chains at n=4 and n=3.

10. **Lite CRDT column.** Still deferred because it overlaps with `git_hash` on
    compose-heavy tasks and would need honest `always_merge` labeling.

---

*Appendix: metric definitions live in `analysis/metrics.py`; collision maps live
in `tasks/*/collision_map.yaml`. Replay tables, confidence intervals, plots, and
`report.html` are generated with
`python -m analysis.make_report results/<run_id>`. Archived material includes
invalid t12 logs, truncated `rw_e` / `t04` n=2 logs, and v1 t01/t03 probes.*
