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

Parallel LLM coding agents are a shipping product category (Cursor background
agents, Claude Code subagents, Devin). When two agents mutate the same
repository they inherit classical concurrency failures (lost updates, stale
reads, write-write clobbers) plus agent-specific ones.

Several coordination mechanisms have been proposed: CRDT convergence (CodeCRDT,
arXiv:2510.18893), git-hash optimistic concurrency (MegaAgent, arXiv:2408.09955),
and LLM-advisory notifications (CoAgent, arXiv:2606.15376). Each is evaluated
*by its own authors, on its own task suite, with its own metrics*. The formal
taxonomy paper (arXiv:2606.17182) states directly that "the present generation
of agent benchmarks does not stress-test inter-agent shared state under
contention."

**Success criteria (defined before building):**

1. One harness runs at least four coordination strategies unchanged on the same tasks.
2. Every metric is computed from a committed, replayable event log.
3. The suite contains at least one task where correct coordination is *doing
   nothing*, so over-coordination is measurable, not only under-coordination.

## 2. Approach

We are deliberately the baseline paper, not a new mechanism. RaceBench is a
minimal instrumented agent loop where **every read and write flows through a
pluggable coordination strategy** (Level A; see §5). That gives 100% read-set
visibility by construction. CoAgent's related work reports HTTP-sniffing sees
only ~26% of reads on SWE-bench workloads.

### Coordination strategies

Each strategy is ~100 lines and labeled "X-style" (our reimplementations, not
the authors' systems):

| Strategy | Mechanism |
|----------|-----------|
| `naive` | Direct writes; last writer wins (floor) |
| `file_lock` | File-level lock on first touch, held until agent finishes |
| `git_hash` | MegaAgent-style read snapshot + 3-way merge + surfaced conflicts |
| `ast_scope` | Same-file symbol claims via AST diff |
| `ast_dep` | `ast_scope` plus import/use dep graph (cross-file races on t04/t05/t07) |
| `notify` | CoAgent-lite: writes land immediately; advisory notices to intersecting readers |

AST-level claims are prior art (Grit, Phantom, Weave, arXiv:2603.24284), but
none has been measured against alternatives on fixed tasks. That neutral
measurement is our contribution. We keep `ast_scope` and `ast_dep` as separate
columns to measure the incremental value of the dependency graph.

### Task suite: how we built it

We started from the failure-mode taxonomy in arXiv:2606.17182 / CoAgent and
asked what minimal repos would *isolate* each mode so a coordination column
could be attributed rather than confounded with "the app is hard." That produced
**t01 through t12**: small collision-seeded trees, each with a collision map,
hidden pytest oracle, and reference solution.

| Mode | Task | Why it exists |
|------|------|---------------|
| Stale read / lost update | `t01_stale_clobber` | Whole-file rewrite race (hardened; v1 archived) |
| **Benign overlap** | `t02_benign_overlap` | Correct coordination is *do nothing* (FP stalls) |
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

**Hardening t01 and t03.** The original compose-friendly `t01_stale_read` /
`t03_ww_clobber` trees are archived under `tasks/_archive/`. Live gpt-5-mini
`edit_file` composed under naive (100% on those v1 cells), so we replaced them
with siblings that **require whole-file `write_file`** from the last read.
Pre-grid gate smoke: naive **0/5** on both hardened probes; `file_lock` **5/5**.
Solo calibration remained **5/5**.

**Conduit track (added later).** After early grid cells we judged that tiny
synthetic packages understate today's multi-module repos (layered imports,
shared schemas, serializers between routes and DB). We added a trimmed
RealWorld-inspired **Conduit** app (FastAPI + SQLite + Pydantic) with seeded
races: `rw_c` (benign same-file), `rw_b` (signature drift), `rw_d` (tag filter
vs count antidependency), `rw_e` (3-agent cascade). Same harness, same
strategies, denser layout. `rw_d` gate smoke: naive **1/5**, notify **5/5**.

**Conduit limits (deliberate).** No Newman, Postgres, or bind-to-port servers.
Oracles use FastAPI `TestClient` and in-process SQLite. Agents do not `pip
install` arbitrary deps or spin listeners during a trial. That keeps trials
reproducible and inside the token/USD budget. Conduit improves *structural*
external validity without claiming full deployment fidelity.

**Ruled out:** full CRDT substrate (Yjs exceeds the window; CodeCRDT confounded
by 82-189% code-volume inflation); CoAgent's full MTPO (saga inverses beyond our
effect loggers); 8+ agents (cost). CooperBench (arXiv:2601.13295) covers the
*communication* axis; we hold communication at zero and vary the *mechanism*.

The real-model grid (`results/grid-v1/`, gpt-5-mini) covers t01-t12 + four
`rw_*` Conduit tasks. Offline scripted tests validate mechanics on every expansion.

## 3. Evidence

### Scripted mechanics (no API)

Committed under `results/smoke-*`:

- `naive` + stale whole-file writes silently loses one agent's feature (oracle
  3/6): textbook lost update, reproduced.
- `git_hash` on identical writes: merged, 6/6, **zero silent losses**.
- Benign overlap: `file_lock` stalls (1 FP stall/trial); `ast_scope` / `ast_dep`
  zero stalls; classifier labels t01 same-symbol stalls as true positives.
- t05 cross-file race: `ast_scope` blind (0 blocks); `ast_dep` stalls on the
  claimed def-use edge and completes after release.

### Real-model grid (complete)

gpt-5-mini; **480 trials** committed under `results/grid-v1/`: 16 tasks x 6
strategies x 5 reps, with agent count gated by each task's `min_agents` (14
tasks at n=2, `rw_e_cascade` at n=3, `t04_cascade` at n=4). Regenerate tables
and the static explorer with `python -m analysis.make_report results/grid-v1`;
validate log integrity with
`python -m analysis.validate_logs results/grid-v1 --expect-trials 480`.

**Spend and pass rate.** ~**$13.56** and ~**37.7M tokens** total (under the $25 /
40M-token guardrail). Pooled oracle pass rate **74.4%** (357/480). At n=2,
by-strategy correctness ranges **0.64** (`ast_dep`) to **0.94** (`file_lock`).
The report command now also emits bootstrap confidence-interval tables and
`results/grid-v1/report.html` for quick inspection.

**Headline finding on t02.** `file_lock` averages **1.0 FP stall/trial** while
`ast_scope`, `ast_dep`, and `notify` average **0**. All six strategies pass the
oracle on t02 (5/5 each); the signal is stall cost, not correctness. The
classifier behaves as designed.

**t12 after the worktree fix.** Post-fix cells are in the main grid (pre-fix logs
archived). All six strategies **5/5** on `t12_split_view` at n=2.

**Headline metric:** **false-positive stall rate**: coordination events between
agents whose applied writes changed disjoint symbol sets. No prior paper reports
this number. Weave self-reports ~95% false-conflict reduction but has never
been independently measured on a fixed suite.

### Reading a strong `naive` column

High pooled `naive` correctness does **not** mean the suite fails to seed races.
The suite is deliberately mixed:

- **Benign / overhead probes** (`t02`, `rw_c`, `t09`) should pass under naive.
  Their job is to expose false-positive stalls and cost, not lost updates.
- **Hard races** can break naive: hardened `t01`/`t03` show naive **0/5** vs
  `file_lock` **5/5**; `rw_d` shows naive **1/5** vs notify **5/5**.

The archived v1 t01/t03 probes under-triggered because models preferred anchored
`edit_file` on *current* disk. Disjoint anchors compose under naive without
anyone seeing the peer; a failed anchor triggers re-read/retry.

**Why whole-file races stay in scope.** Agents snapshot, plan, then write. Between
read and write the file can change. Fine-grained `edit_file` only helps when
anchors land in different regions; real work often hits the same function or
emits a full-file write from a stale read. We do not claim production agents
always rewrite whole files. The benign half measures over-coordination; the
hardened half measures stale-read / WW modes.

**Fair claim:** coordination value is *selective* (visible on hardened cells and
as stall/wall-clock cost when mechanisms over-fire).

**Unfair claim:** the tasks are ill-designed because naive works on the benign half.

### Exploratory peer-negotiation extension

After the main grid, we added two new Level A strategies to test A2A-style
coordination inspired by automated negotiation protocols such as POANCD. These
are **not** part of the 480-trial headline table yet. They are a 10-trial
targeted smoke (`results/grid-v1-peer-targeted-v2/`): five high-signal tasks
(`t02`, `t03`, `t04`, `rw_d`, `rw_e`) x two strategies x one rep.

`peer_contract` is voluntary: agents can declare edit intent and ACK a compact
contract before overlapping writes. `peer_broker` is forced: the runtime detects
an overlapping write, opens a private broker decision with affected peers, and
allows ACK, ACK-with-constraints, or conflict.

Preliminary result: `peer_contract` was **5/5** correct; `peer_broker` was
**3/5**. Broker improved after adding `ack_with_constraints`: it passed
`t03_fetch_clobber` and `rw_e_cascade`, where an earlier hard-veto broker loop
failed. But it still cost more: mean wall clock **119s vs 85s**, mean tokens
**170k vs 153k**, stalls **24 vs 13**, coordination events **176 vs 88**.

Interpretation: forced negotiation is not automatically better. The broker's
remaining problem is trigger precision. A full-file read can make a peer look
dependent on many symbols, so the broker negotiates even on benign or weakly
related overlap. Voluntary `peer_contract` often gives the system a sharper
intent signal earlier. RaceBench therefore exposed a second design question:
not just **how** agents negotiate, but **when** the runtime should invoke
negotiation at all.

## 4. Constraints

Cost is a first-class constraint. The runner enforces **$25 / 40M-token** with
idempotent resume (existing logs are skipped). Every trial logs tokens on
`trial_end`; `python -m analysis.make_report` derives USD from committed price
tables (`run_meta.json` or `runner/config.example.yaml`: gpt-5-mini at $0.25/M
input, $2/M output). **Grid-v1 spend: ~$13.56** (~37.7M tokens across **480**
trials), under the $25 / 40M-token budget cap.

Calibration gates the grid: one solo agent per task, naive strategy, >80% pass
required before concurrency cells. Lock waits are bounded; timeouts are logged;
every trial uses a throwaway git workspace.

## 5. Honesty & Trajectory

### Extensibility

| Level | What plugs in | Status |
|-------|---------------|--------|
| **A: Strategy** | `_coordinate_read` / `_coordinate_write` under our agent loop | Shipped |
| **B: Task** | `tasks/<name>/` repo, oracle, collision map | Shipped |
| **C: External system** | Third-party multi-agent product; RaceBench owns workspace + oracle | Shipped (C1 bridges) |

Levels A/B produce the apples-to-apples comparison table: same agent tools,
same event log, same metrics; only the mechanism changes. `git_hash` is
MegaAgent-*style* (mechanism class), not a run of MegaAgent's repository.

Level C (Terminal Bench / Harbor inspired) scores **system + oracle**
(correctness, wall clock). It does not produce comparable FP-stall or read-set
metrics unless the adapter emits RaceBench events. We split Level C into two
honestly labeled sub-modes:

| Mode | Shape | Status |
|------|-------|--------|
| **C1: Harness-swap** | Fixed RaceBench roles + briefs; vendor *worker* loops edit the workspace | Shipped (`scripted`, `shell`, MegaAgent bridge, Cursor SDK) |
| **C2: Single-goal emergent** | One seed prompt; product decides whether/how to parallelize | Deliberately unbuilt (see below) |

**C1** keeps the same collision maps and oracles as Level A so a difference can
still be attributed to "this product's agent loop under a known split," not to
invented decomposition. On shared isolation, N vendor agents share one cwd
(unmediated concurrent writers). On worktree tasks, each agent gets its own cwd
from `paths.json` and the harness merges. C1 does **not** claim to measure a
product's full orchestrator (Cursor multitask, MegaAgent CEO recruitment, etc.).

**Purpose of C1 (why run it at all).** RaceBench does the split; the vendor does
not orchestrate. Shared-isolation C1 is therefore closest to Level A `naive`
plus a foreign worker stack (different tools, loop, and often model). That is
still useful as an **external-validity check on the uncoordinated floor**, not as
a coordination column:

- If a hard race (e.g. hardened t01/t03) that fails under Level A `naive` also
  fails under Cursor C1, the collision is not an artifact of our toy tool API.
- If Cursor C1 passes where `naive` fails, the interesting claim is capability /
  edit granularity / re-read habit, not "Cursor coordinated the agents."
- Strategy rankings, FP stalls, and read-set metrics stay in Level A. To vary
  the model with full visibility, swap the model under Level A; do not bolt
  RaceBench strategies onto native Cursor tools.

C1 cells are exploratory and stay off the Level A comparison table. Prefer hard
tasks for Cursor/MegaAgent smokes; easy cells where `naive` already passes 100%
add little signal.

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

Prompt tokens per Cursor cell are typically **~10–50×** higher than a single Level
A trial (e.g. t02 ~93k vs ~14k; t11 ~1.08M vs ~30k), with wall clock often
longer too. That is consistent with a heavier tool loop (more reads/edits per
agent), not with RaceBench injecting coordination.

**How to read this.** Comparing Level A `naive` to Cursor C1 is **harness vs
harness** (our instrumented tools + gpt-5-mini vs Cursor's local agent loop +
composer), not a new row in the strategy table. A strong Cursor pass on a cell
where our `naive` never passes does **not** mean coordination is unnecessary in
production; it may mean the foreign worker is better at avoiding or recovering
from the seeded race on one try. A Cursor fail on t03 while still beating our
`naive` rate on the same task shows the collision can still bite a stronger stack.

We treat these as **exploratory external validity**, not headline evidence. The
core contribution remains Level A/B: same harness, vary mechanism. If stronger
agent stacks keep clearing hardened cells in one pass, that argues for **harder
or harness-agnostic collision seeds** in a future suite revision, not for folding
C1 into the strategy comparison.

We shipped a MegaAgent vendor bridge (`adapters/megaagent/`) and a Cursor C1
adapter (`--adapter cursor`). MegaAgent early trials hit integration limits: t02
timed out at 900s with zero file writes after CEO recruitment; t04 ran ~887s and
~2M input tokens but the CEO ignored the RaceBench brief and recruited a Gobang
demo team. We document those as adapter and alignment limits, not as evidence
that MegaAgent "failed" the oracle. We do not patch MegaAgent upstream.

**C2 is deliberately unbuilt.** A seed prompt without a forced split mostly
measures whether a product's autonomous planner chooses to parallelize at all,
closer to general SWE-bench-style capability than to coordination-mechanism
comparison. A fair C2 would need to *induce* a split (or treat "did it
parallelize?" as a first-class outcome separate from correctness) so a
no-parallelize trial is a valid data point, not a failed one. That is a
different, larger benchmark design than C1, and out of scope for this window.

**MegaAgent orchestration vs RaceBench task shape.** MegaAgent's headline claim is
dynamic org design: one CEO prompt recruits agents, decomposes work, and scales
the team without a predefined SOP. RaceBench deliberately does the opposite. Every
task names fixed `agent-*` roles, fixed subtask briefs, a seeded repo, and a hidden
oracle. That keeps collision maps, calibration gates, and Level A strategy columns
deterministic and replayable. Level C1 on RaceBench therefore cannot fairly score
dynamic role allocation or open-ended task decomposition; it tests whether an
external multi-agent *runtime* can edit our repo under contention and pass our
oracle. We state that explicitly rather than treating Level C cells as comparable
to Level A `git_hash` mechanism columns.

### Incident: t12 worktree merge (fixed)

**Symptom.** First real-model pass on `t12_split_view`: **0%** every strategy,
including cells where both agents finished and the log reported `worktree_merge`
`ok: true`, `conflicts: []`, `message: "clean"`. Oracle still missing `greet`.
A "clean" merge on an unchanged baseline means the harness lied about
integration.

**Root cause (harness).** Fake worktrees (shutil copies + shared git index), not
real `git worktree`. Edits did not land on `agent/<id>`; `.racebench_git` was
sometimes tracked; conflict path used last-writer-wins whole-tree overwrite.
Mid-trial strategies cannot save a broken end merge under worktree isolation.

**Response.** Archived invalid logs (`results/grid-v1/_archive_t12_pre_worktree_fix/`,
`results/grid-v1-calibration/_archive_t12_pre_worktree_fix/`). Fixed with
per-agent indexes, `commit-tree` / `update-ref`, per-file 3-way merge, AST
method-union preferring non-stub bodies, regression tests, and worktree-specific
prompts. Re-validation: t12 solo calib **5/5**; naive smoke **2/2**. Pre-fix t12
numbers must not appear in the comparison table.

The AST union is a **benchmark merge helper**, not a production CRDT/OT integrator.

### Other limits

1. t01-t12 are probes; Conduit adds structure but not Newman/Postgres/live servers.
2. Strategy columns are mechanism-class reimplementations (Level A), not upstream products (Level C).
3. **Predefined roles and agent counts.** Tasks fix who does what (`agent-datasource`,
   `agent-pipeline`, …) and gate concurrency with `min_agents`. We do not measure
   dynamic role allocation or adaptive team sizing (systems that add or drop workers
   from task complexity). That is a deliberate benchmark limit: without fixed briefs
   and oracle targets, attribution across strategies and reps would not be stable.
4. Symbol granularity is top-level only; `ast_scope` / `ast_dep` over-serialize within classes (visible on t06).
5. Scripted trials validate mechanics; headline claims use real-model JSONL logs.
6. Solo-calibration ceiling: little signal on tasks models cannot do alone.
7. `ast_dep` import resolver is best-effort, not a type checker.
8. Trial-timeout paths previously zeroed `trial_end` tokens; we recover from live agents and backfill from `llm_usage`.
9. Lite CRDT column deferred: overlaps `git_hash` on compose; would need honest labeling (`always_merge`).
10. `grep` / `glob` / `list_files` bypass the strategy; read-set visibility is 1.0 only for `read_file`.
11. Cascade tasks need full agent chains (`rw_e` at n=3, `t04` at n=4); truncated cells archived.

### Next steps

The Level A/B grid for gpt-5-mini is **shipped** in `results/grid-v1/`. What
remains is optional extension work, not a blocker for the core comparison table.
The submission artifact now includes a static explorer, log validator, practical
decision guide, and an external-coordination protocol documenting why Level C is
black-box runtime scoring unless a product exposes mediation hooks.

1. **Cursor C1 exploratory cells.** Shipped (`results/ext-cursor/`, 15/16 on one
   pass); document as harness-vs-harness smoke, not strategy ranking. Optional:
   more reps on t01/t03/rw_e only if budget allows.

2. **Claude Code C1 adapter.** Same harness-swap pattern as Cursor: N headless
   `claude -p` (or equivalent) processes, one brief each, cwd from `paths.json`.
   Same-pattern follow-on; not required for the core contribution.

3. **C2 (named, unbuilt).** See above. Do not ship a half-built single-goal track
   as a headline result; the confound is already documented.

4. **Second model family.** Every committed grid cell uses gpt-5-mini. Re-running
   the same 480-trial matrix on a stronger or cheaper model would test whether
   coordination rankings and FP-stall gaps hold across capability tiers.

5. **Cascade at 8+ agents.** Deferred for cost; `t04` / `rw_e` already stress
   chains at n=4 and n=3.

6. **Lite CRDT column.** Still deferred: overlaps `git_hash` on compose-heavy
   tasks and would need honest `always_merge` labeling.

7. **Suite hardness vs stronger stacks.** Preliminary Cursor C1 passes on cells
   where Level A `naive` scores 0/5 (e.g. t01, rw_e) suggest the probe suite may
   under-challenge capable foreign worker loops; future tasks could target
   harness-agnostic collisions or higher concurrency if we want C1 to separate stacks.
8. **Level C adapter hardening.** The MegaAgent vendor bridge runs but is not
   production-ready: t02 timed out at 900s with no file writes; t04 burned ~2M
   input tokens on a Gobang demo instead of the cascade repo. Concrete fixes:
   request timeouts on upstream HTTP, stream `log.txt` to the runner terminal,
   fail-fast when the CEO recruits off-brief agents, and optionally deterministic
   recruit from RaceBench briefs (narrower claim, less Gobang drift). Same hygiene
   applies to any future shell adapter.

---

*Appendix: metric definitions in `analysis/metrics.py`; collision maps in
`tasks/*/collision_map.yaml`; replay tables, CI intervals, plots, and
`report.html` via `python -m analysis.make_report results/<run_id>`. Archives:
invalid t12 (`results/grid-v1/_archive_t12_pre_worktree_fix/`, calibration twin);
truncated `rw_e` / `t04` n=2 (`results/_archive/`); v1 t01/t03 probes
(`tasks/_archive/`, `results/_archive/t01_stale_read_v1/`,
`results/_archive/t03_ww_clobber_v1/`).*
