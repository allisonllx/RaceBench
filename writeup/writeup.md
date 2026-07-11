# RaceBench: a neutral benchmark for multi-agent coding coordination

> Submission write-up, structured by the five judging pillars.
> Draft length is intentionally above the usual ~1k-word target while we
> document incidents and reasoning; trim before final submit.
> Numbers marked [TBD] are filled from `results/grid-v1/comparison_table.md`
> after the real-model grid completes. Cost (USD) is derived at report time from
> committed `trial_end` token counts — old JSONL logs do not need re-running.

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
pluggable coordination strategy** (Level A extensibility — see §5) — which
gives 100% read-set visibility by construction (CoAgent's related work reports
HTTP-sniffing sees only ~26% of reads on SWE-bench workloads).

Strategies (each ~100 lines, labeled "X-style" — our reimplementations, not
the authors' systems): `naive` (floor), `file_lock`, `git_hash`
(MegaAgent-style read-snapshot + 3-way merge + surfaced conflicts),
`ast_scope` (same-file symbol claims via AST diff), `ast_dep` (same claims
plus a workspace import/use dep graph so t4/t5/t7 cross-file races become
visible), and `notify` (CoAgent-lite: unblocked writes plus advisory
notifications to readers whose read set the write intersects — without
serialization pre-order or saga inverses). The AST idea is prior art — Grit,
Phantom, Weave, and arXiv:2603.24284 — but none has been measured against
alternatives on fixed tasks; that neutral measurement is our contribution.
We keep `ast_scope` and `ast_dep` as separate columns so the grid measures
the incremental value of the dep graph. Lock-on-write-only file locks and
`git_hash`+worktree hybrids were considered and skipped as redundant with
existing axes.

### How we landed on the task suite

We started from the failure-mode taxonomy in arXiv:2606.17182 / CoAgent and
asked what minimal repos would *isolate* each mode so a coordination column
could be attributed rather than confounded with “the app is hard.” That
produced **t1–t12**: small collision-seeded trees, each with a collision map,
hidden pytest oracle, and reference solution.

| Mode | Task | Why it exists |
|------|------|---------------|
| Stale read / lost update | `t1_stale_clobber` | Whole-file rewrite race (hardened; v1 archived) |
| **Benign overlap** | t2 | Correct coordination is *do nothing* (FP stalls) |
| Write–write clobber | `t3_fetch_clobber` | Whole-`fetch` rewrite race (hardened; v1 archived) |
| Causal cascade | t4 | 4-agent dependency chain |
| Cross-file interface | t5 | Invisible to file-scoped locks / same-file AST |
| Feature pair | t6 | CooperBench-style coupled features |
| Antidependency / rw-canary | t7 | Read–write ordering hazard |
| Lock livelock | t8 | Coordination thrash under contention |
| Overhead confound | t9 | Disjoint packages — cost without benefit |
| Phantom tool / registry | t10 | Harness-extension: tool surface drifts |
| Irreversible effects | t11 | Ordering of non-rewindable side effects |
| Split-view worktrees | t12 | Isolation until end merge |

t1–t12 are intentionally **probes**, not stand-ins for production codebases.
The original compose-friendly `t1_stale_read` / `t3_ww_clobber` trees live under
`tasks/_archive/` for audit: live gpt-5-mini `edit_file` composed under naive
(100% on those v1 cells), so we replaced them with hardened siblings that
**require whole-file `write_file`** from the last read. Gate smoke
(`results/adversarial-gate/`): naive **0/5** on both hardened probes; file_lock
**5/5**. Solo calibration remained **5/5**.

After running early cells we judged that a suite of tiny synthetic packages
does not reflect the shape of today’s agent targets: multi-module apps,
layered imports, shared schemas, serializers sitting between routes and DB.
We therefore added a second track later — a trimmed **RealWorld-inspired
Conduit** app (FastAPI + SQLite + Pydantic) with seeded races: `rw_c`
(benign same-file), `rw_b` (signature / interface drift), `rw_d` (tag
filter vs count antidependency), `rw_e` (3-agent cascade). Same harness, same
strategies, denser import graph and more realistic file layout. `rw_d` gate
smoke: naive **1/5**, notify **5/5**.

**Conduit track limits (deliberate).** We did *not* stand up Newman + Postgres
+ bind-to-port servers. Oracles use FastAPI `TestClient` against an in-process
app and SQLite; agents do not `pip install` arbitrary deps or spin listeners
during a trial. Those choices keep trials reproducible inside a throwaway git
workspace and inside the token/USD budget, but they mean Conduit improves
*structural* external validity (packages, layers, cross-file edges) without
claiming full deployment fidelity. Collision maps may list `critical_paths`;
metrics report `critical_paths_read_fraction` from the event log.

The real-model grid (`results/grid-v1/`, gpt-5-mini) covers t1–t12 + `rw_*`;
offline scripted tests validate mechanics on every expansion.

**Ruled out and why:** a full CRDT substrate (Yjs infrastructure exceeds the
window; CodeCRDT's own results are confounded by 82–189% code-volume
inflation); CoAgent's full MTPO (saga inverses beyond our effect loggers);
8+ agents (cost). CooperBench (arXiv:2601.13295) already covers the
*communication* axis with 652 tasks; we hold communication at zero and vary
the *mechanism* — complementary, not competing.

## 3. Evidence

Mechanics are pinned by automated tests plus deterministic scripted-agent
trials (no API needed, committed under `results/smoke-*`):

- naive + stale whole-file writes silently loses one agent's feature
  (oracle 3/6) — the textbook lost update, reproduced;
- git_hash on identical writes: merged, 6/6, **zero silent losses**;
- benign overlap: file_lock stalls (1 FP stall/trial), ast_scope / ast_dep
  zero stalls; the FP classifier correctly labels t1's same-symbol stalls
  as true positives;
- t5 cross-file race: `ast_scope` stays blind (0 blocks); `ast_dep` stalls
  on the claimed def↔use edge and still completes after release.

Real-model grid (gpt-5-mini, 15 tasks × 6 strategies × `{2,3,4}` agents as
gated by each task’s `min_agents` / agent count × 5 reps; see
`results/grid-v1/comparison_table*.md`): overall correctness is high across
strategies (pooled by-strategy rates roughly **0.70–0.84**). On
`t2_benign_overlap`, `file_lock` averages **1.0 FP stall/trial** while
`ast_scope`, `ast_dep`, and `notify` average **0** — the classifier behaves as
designed. Headline metric: **false-positive stall rate** — coordination events
between agents whose applied writes changed disjoint symbol sets. No prior
paper reports this number; Weave self-reports a ~95% false-conflict reduction
but has never been independently measured.

**Reading a strong `naive` column.** Pooled correctness under `naive` can still
look competitive when many cells are benign / easily composed. That is *not*
evidence the suite is “badly designed so naive never breaks.” The suite is
deliberately mixed: benign / overhead probes (`t2`, `rw_c`, `t9`) are meant to
pass under naive — their job is to expose false-positive stalls and cost, not
lost updates. Hard races *can* break naive: scripted smoke reproduces
whole-file lost updates, and after hardening, live gpt-5-mini also fails
`t1_stale_clobber` / `t3_fetch_clobber` under naive (0/5) while file_lock
recovers (5/5); `rw_d_tag_antidependency` shows naive 1/5 vs notify 5/5. The
archived v1 `t1`/`t3` probes under-triggered because models preferred anchored
`edit_file` against *current* disk — disjoint anchors compose under naive
without anyone “seeing” the peer, and a failed anchor triggers re-read/retry.

**Why whole-file / same-region races are in scope.** Parallel coding agents do
not continuously track peer edits in real time: they snapshot, plan, then
write. Between read and write the file can change — the classical stale-read /
lost-update. Fine-grained `edit_file` only saves you when anchors land in
*different* regions; real work often hits the same function, config block, or
“rewrite this module cleanly,” where a second agent overwrites from an older
snapshot. We do **not** claim production agents always rewrite whole files —
they often patch — which is why the benign/disjoint half stays in the suite.
The hardened cells exist so the comparison table also measures the mode where
anchors collide or agents emit a full-file write from a stale read, not only
the lucky compose path. Fair claim: coordination value is **selective** —
visible on hardened WW / antidependency cells and as stall / wall-clock cost
when mechanisms over-fire — not a suite-wide naive cliff. Unfair claim: the
tasks are ill-designed because naive works on the benign half.

## 4. Constraints

Cost is a first-class design constraint: the runner enforces a hard **$25 /
40M-token** budget and resumes idempotently (existing logs are skipped), so a
run killed by the budget guard loses nothing. Every trial logs prompt and
completion token counts on `trial_end`; `python -m analysis.make_report`
derives **USD from those counts** plus a committed price table (`run_meta.json`
or `runner/config.example.yaml` defaults: gpt-5-mini at $0.25/M input, $2/M
output). **Committed spend to date: $5.24** (~13.6M tokens across 207
completed trials; full grid projected <$25). Per-cell **`mean_usd`** and
**`mean_tokens`** land in `comparison_table.csv`. A calibration mode (one solo
agent doing all subtasks, naive strategy) gates the grid: we require >80% solo
pass rate per task before spending on the concurrency cells, so weak-model
noise cannot masquerade as coordination failure. Lock waits are bounded and
timeouts logged (deadlock becomes a datum, not a hang); trials are wall-clock
capped; every trial runs in a throwaway git workspace.

## 5. Honesty & Trajectory

**Suite in one line.** Probe taxonomy t1–t12 (see §2) plus Conduit `rw_*`
added after we decided synthetic probes alone understate today’s multi-module
repos — with the TestClient/SQLite limits above.

### Extensibility: what “usable” means today

We separate three plug-in levels so MegaAgent-open-source and Terminal-Bench–
style “bring your agent” requests are not confused with each other.

| Level | What plugs in | Status |
|-------|---------------|--------|
| **A — Strategy** | `_coordinate_read` / `_coordinate_write` under *our* agent loop | **Shipped** (`docs/adding-a-strategy.md`) |
| **B — Task** | `tasks/<name>/` (repo, oracle, collision map) | **Shipped** |
| **C — External system** | Someone else’s multi-agent product drives the trial; RaceBench supplies workspace + oracle (+ optional event bridge) | **Not shipped** — planned |

Levels A/B are what make the comparison table apples-to-apples: same agent
tools, same event log, same metrics, only the coordination mechanism changes.
That is why `git_hash` is labeled MegaAgent-**style** — it is a reimplementation
of the *mechanism class*, not a run of MegaAgent’s repository. MegaAgent (and
similar systems) are full products: orchestration, roles, tools, their own
workspace story. Dropping their tree into RaceBench without an adapter would
measure *their whole stack*, not the concurrency claim, and would usually break
100% read-set visibility (our logging assumes reads/writes go through
`Strategy`).

Terminal Bench / Harbor inspire **Level C**, not a replacement for Level A:
they fix the task environment and verifier and let authors implement a thin
agent adapter (`setup` / `run` against an env). A RaceBench Level C would look
similar — “installed” or “external” runtime on a RaceBench task package —
while keeping Level A for mechanism-class columns. Until C exists, open-source
upstream systems are evaluated only via reimplementation or a future shim that
still implements `Strategy`.

### Incident: t12 worktree merge was broken (then fixed)

**What we observed.** During the first real-model pass over `t12_split_view`
(`isolation: worktree`), **every strategy scored 0%** — including cells where
both agents finished (`agent_statuses: done`), wrote `lib/api.py` and their
call sites, and the log reported `worktree_merge` with `ok: true` /
`conflicts: []` / `message: "clean"`. The oracle still failed with missing
`greet` (or equivalent). That pattern is a red flag: if the merge is
“clean” but the final tree is still the task baseline, the harness is lying
about integration, not measuring coordination.

**Root cause (harness, not model / not strategy).** Agent “worktrees” were
implemented as **shutil copies** plus a named branch tip, with a single
shared git index under `.racebench_git` and alternating `GIT_WORK_TREE`.
That is not a real `git worktree`. Consequences:

1. **Edits never reliably landed on `agent/<id>`.** Commits fought over one
   index; `HEAD` and branch tips drifted (we reproduced ideal greet+farewell
   edits where `merge` returned clean while `main:lib/api.py` stayed at the
   initial `ping`-only content).
2. **`.racebench_git` lived inside the work tree** and was sometimes
   *tracked* by `git add -A`, corrupting trees further.
3. **On conflict, “force-integrate” copied one agent’s entire tree over
   `main`** (last-writer-wins). Even after commits worked, that path erased
   the other agent’s method — so a *correct* split-view failure mode
   (merge drops a side) was mixed with a *harness* failure mode (merge
   never applied either side).

Mid-trial coordination strategies were largely irrelevant for this bug:
agents cannot see each other under worktree isolation, so t12’s oracle
depends almost entirely on **end-of-trial merge**. A broken merge makes
every strategy look identical (and useless).

**Why this matters for honesty.** Early grid cells for t12 were **invalid
measurements**. Treating them as evidence that “no strategy handles split
view” would have been a false claim. We archived pre-fix logs under
`results/grid-v1/_archive_t12_pre_worktree_fix/` and
`results/grid-v1-calibration/_archive_t12_pre_worktree_fix/` rather than
deleting them silently, so the mistake remains auditable.

**What we changed (and why).**

1. **Private per-agent indexes + `commit-tree` / `update-ref`** onto
   `agent/<id>`, then merge into `main` — commits actually contain agent
   edits.
2. **`.gitignore` for `.racebench_git/` and `.worktrees/`** so the git store
   is never part of the tree.
3. **On merge conflict: per-file 3-way `git merge-file`**, not whole-tree
   overwrite — disjoint line edits (greet above `ping`, farewell below) can
   both survive.
4. **If line merge is unclean on `.py` files: AST method-union**, preferring
   a real method body over a `raise NotImplementedError` stub. We needed
   this because real gpt-5-mini runs often *implement their own method
   correctly* and *stub the other agent’s method* (against the prompt). A
   naive “prefer theirs” union then kept the stub and dropped the good
   implementation — again looking like a strategy failure when it was a
   merge heuristic interacting with model behavior.
5. **Regression tests:** ideal edits pass the oracle; docstring-conflict
   rewrites still keep both methods; disjoint file edits merge clean.
6. **System prompt:** worktree tasks now tell agents they are isolated
   until end merge (the shared-repo prompt was actively misleading for t12).

**Re-validation.** After the fix: solo calibration for t12 is **5/5**
oracle pass; a multi-agent `naive` smoke trial is **correct=True (2/2)**.
We are re-running the full t12 grid cells on the fixed harness; pre-fix
t12 numbers must not be cited in the comparison table.

**What this does *not* claim.** The AST union is a **benchmark merge
helper**, not a proposed production CRDT/OT. Preferring non-stub methods is
a deliberate bias toward “keep working implementations when both sides
touched the same symbol.” Strategies still do not coordinate across
worktrees mid-trial. Shared-isolation tasks (t1–t11, `rw_*`) do not use
this path and were not invalidated by the fix.

### Other known limits

(1) t1–t12 remain probes; Conduit improves layout/import realism but is not
Newman+Postgres+listening servers, and trials do not allow on-the-fly package
install or port binding — see §2. (2) Strategy columns are mechanism-class
reimplementations, not upstream systems (Level A vs Level C above).
(3) Symbol granularity is top-level only (a class is one symbol), so
`ast_scope` / `ast_dep` over-serialize within classes — visible in t6 and
reported, not hidden. (4) Scripted-agent results validate mechanics only;
all headline claims come from real-model trials with the event logs
committed. (5) The solo-calibration ceiling means results say little about
tasks models can't do alone. (6) Split-view integration is sequential
branch merge plus per-file 3-way / AST union on conflict — not a
production CRDT/OT integrator; see incident above. (7) `ast_dep`'s import
resolver is best-effort (package re-exports + submodule scan); it is not a
full type checker. (8) Trial-timeout paths previously zeroed
`trial_end` token totals even when `llm_usage` events existed (empty
`asyncio.gather` results); we recover counters from live agents going
forward and backfill reports from `llm_usage` for old timed-out logs.
(9) We considered a lite CRDT column but deferred it: non-overlapping
compose already overlaps `git_hash`, and a truthful “always converge”
column is a post-hackathon addition if labeled honestly
(`always_merge` / `crdt_lite`), not as CodeCRDT. (10) Grep/glob/list_files
bypass the strategy (documented in the strategy guide); read-set visibility
is 1.0 only for `read_file`. (11) High pooled `naive` correctness on early grid cells did **not** mean the
suite failed to seed races — see §3 “Reading a strong `naive` column”. We
archived compose-friendly v1 `t1`/`t3` and shipped hardened whole-file
siblings plus `rw_d` after an adversarial gate smoke
(`results/adversarial-gate/`). (12) Cascade tasks require the full agent chain (`min_agents`; e.g.
`rw_e_cascade` at n=3, `t4_cascade` at n=4). Truncating drops later consumers
and makes the oracle unreachable regardless of strategy; those cells were
archived, not cited.

**Next:** finish the paid grid on t1–t12 + `rw_*` with valid t12 cells;
prototype **Level C** (external-system adapter inspired by Terminal Bench /
Harbor) starting with a MegaAgent-shaped path if factorable, otherwise a
documented black-box agent adapter with honest metric gaps; then a second
model family and cascade at 8 agents.
---

*Appendix pointers (not counted): metric definitions in `analysis/metrics.py`
docstring; per-task collision maps in `tasks/*/collision_map.yaml`; replay any
number in the tables from the committed JSONL logs via
`python -m analysis.make_report results/<run_id>` (USD backfilled from
`trial_end` token counts; prices in `results/<run_id>/run_meta.json`; also
emits across-task `comparison_table_overall` and
`comparison_table_by_strategy`). Archived invalid t12 logs:
`results/grid-v1/_archive_t12_pre_worktree_fix/` and
`results/grid-v1-calibration/_archive_t12_pre_worktree_fix/`. Archived
truncated `rw_e_cascade` n=2 cells and prior calib:
`results/_archive/rw_e_cascade/`. Archived truncated `t4_cascade` n=2 cells:
`results/_archive/t4_cascade_n2/`. Archived compose-friendly v1 probes and
their grid logs: `tasks/_archive/{t1_stale_read,t3_ww_clobber}/`,
`results/_archive/t1_stale_read_v1/`, `results/_archive/t3_ww_clobber_v1/`.
Adversarial gate smoke for hardened siblings + `rw_d`:
`results/adversarial-gate/` and `results/adversarial-gate-calibration/`.*
