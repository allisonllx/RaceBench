# RaceBench: A Neutral Benchmark for Multi-Agent Coordination

## 1. Problem

Parallel coding agents are easy to launch but hard to trust. When two or more agents edit the same repository, they can clobber each other's work, read stale state, coordinate too much, or waste tokens. Existing proposals usually report gains inside one system or task distribution, making it hard to tell whether the mechanism helped or the product simply gave it easier work.

RaceBench asks: given the same repository, prompts, models, task pairs, and oracles, which coordination policies reduce race failures, and when do they create avoidable stalls? The tasks are seeded for **contention**, not convenience: solo calibration checks whether agents can do the work alone; parallel cells measure what coordination adds on top. It also tests new coordination ideas by asking whether they improve correctness or merely add stalls, tokens, latency, or hidden overcoordination. My pre-grid criteria were: replay fixed race tasks, compare against naive, report correctness, wall time, tokens, wasted work, stalls, and false-positive stalls, and preserve auditable logs.

The novelty is not just measuring failures. It is also measuring overcoordination. False-positive stalls, where a strategy blocks safe parallelism, are rarely foregrounded in prior multi-agent coordination work, but they matter in practice because a safe agent team that serializes everything is not very useful.

## 2. Approach

RaceBench is a small, instrumented benchmark harness. Each trial runs two to four agents on a seeded coding task. The harness records reads and writes, applies a coordination strategy, runs the oracle, and writes JSONL logs plus aggregate tables. The headline grid uses 16 tasks and 6 Level A strategies: `naive`, `file_lock`, `notify`, `git_hash`, `ast_scope`, and `ast_dep`. Post-grid extensions ([`peer_contract` / `peer_broker`](#peer-broker-v25-iteration), [`adaptive_lease`](#adaptive-lease-iteration)) are appendix-only for this submission.

I ruled out three broader approaches. An auto-merge editor would confound coordination with merge quality. A full CoAgent or MTPO-style saga layer needs inverse operations beyond this benchmark. Direct comparison with products like Claude Code or Cursor without shared mediation hooks mostly measures each product's hidden planner, not a reusable policy.

I chose an instrumented [Level A](#level-a-to-c) harness for cleanest attribution: fixed task, model, oracle, and prompts; only the coordination mechanism changes. [Level C](#level-a-to-c) black-box runtime checks stay separate unless a runtime emits RaceBench-compatible events.

## 3. Evidence

The main run, `results/grid-v1`, contains 480 replayable trials: 16 tasks, 6 strategies, 5 repetitions. The pooled pass rate was 74.4 percent, with about $13.56 spent and 37.7M tokens recorded. JSONL logs record reads, writes, stalls, and coordination events so claims trace to trajectories, not demos alone. The report pipeline validates log structure, then generates aggregate tables, bootstrap confidence intervals, and a [static HTML explorer](#full-results).

The baseline is intentionally simple. `naive` gives the floor for "just run both agents." On hard clobber cases, the floor collapses: in `t01_stale_clobber` and `t03_fetch_clobber`, naive went 0/5 while `file_lock` went 5/5. That supports the modest claim that coordination is necessary for destructive overlap. On `rw_d_tag_antidependency`, naive went 1/5 while `notify` went 5/5, showing that lightweight notification can help when the issue is stale reads rather than simultaneous writes.

The evidence also shows trade-offs. In `t02_benign_overlap`, `file_lock` stayed correct but averaged 1.0 false-positive stall per trial on benign parallel work. That is why RaceBench tracks stalls separately from correctness. A strategy can pass tests and still destroy concurrency.

## 4. Constraints

The biggest constraint was cost. I kept the grid small and reused the same logs for the final report instead of buying a larger sweep. I did run a [scoped Agnes sensitivity check](#cross-run-findings), but not a full second-provider grid.

Coordination also has a latency price. On pooled n=2 cells, parallel `notify` averaged 51.8s and 72.7k tokens while `file_lock` averaged 174.2s with heavy benign-overlap blocking. Safety and throughput are not the same metric. There are also realism constraints: RaceBench uses a local Conduit-style in-process setup, fixed task pairs, and deterministic oracles. That keeps trials reproducible and cheap, but it does not capture long-horizon planning, changing requirements, flaky external services, or heterogeneous agent products.

## 5. Honesty & Trajectory

RaceBench is not a plug-and-play benchmark for arbitrary existing agents. A black-box runtime such as Cursor, MegaAgent, or another orchestrated system can be scored as [Level C](#level-a-to-c), but without read/write intent hooks it collapses toward a naive external check from RaceBench's perspective. A true external strategy needs a mediation protocol around `on_read`, `on_write_intent`, `decision`, `on_write_committed`, and `on_agent_done`.

Known failure modes are specific. The AST merge strategy is still too coarse for many real refactors. The dependency graph strategy depends on simplified static observations and can miss dynamic behavior. The task suite is small enough that strategies can accidentally fit it. The benchmark mostly studies two-agent races, not larger teams. It also rewards strategies implemented inside the harness more directly than external products, which is why I separate Level A and Level C throughout the docs and report.

With two more weeks, I would prioritize hybrid coordination (adaptive leases plus broker only on ambiguous conflicts), harder multi-agent probes, and one mediated Level C adapter that emits read/write intent events. More Cursor repetitions and a full Agnes grid are useful, but secondary. The claim stays modest: RaceBench is a reusable benchmark for coordination mechanisms, plus a task and oracle suite for black-box runtime checks.

Full evidence and long-form reasoning: [`writeup/writeup.md`](writeup.md). Interactive results: [`results/grid-v1/report.html`](../results/grid-v1/report.html).

---

## Appendix: Links And Level Guide

This appendix is supporting material and is not part of the five-pillar 1000-word body.

### Full Results

- Static results explorer: [`results/grid-v1/report.html`](../results/grid-v1/report.html)
- Combined 9-strategy explorer: [`results/grid-v1-plus-extensions/report.html`](../results/grid-v1-plus-extensions/report.html)
- Cross-run dashboard: [`results/cross-run-analysis/dashboard.html`](../results/cross-run-analysis/dashboard.html)
- Main result logs and tables: [`results/grid-v1/`](../results/grid-v1/)
- Post-grid extension logs and tables: [`results/grid-v1-extensions-full/`](../results/grid-v1-extensions-full/)
- Cursor C1 exploratory logs: [`results/ext-cursor/`](../results/ext-cursor/)
- Report generator code: [`analysis/html_report.py`](../analysis/html_report.py)

### Reproduction Commands

```bash
python -m analysis.validate_logs results/grid-v1 --expect-trials 480
python -m analysis.make_report results/grid-v1
```

### Suggested Screenshots From `report.html`

Judges spot-check the repo; these views best match the write-up claims. Save PNGs under `writeup/figures/` and link them here if you embed images in the PDF.

1. **Summary metrics bar** (top: 480 trials, 74.4% pass, spend/tokens). Establishes scale at a glance.
2. **Task x Strategy heatmap** (`correct_rate`, unfiltered). Shows selective strategy value across failure modes, not one winner everywhere.
3. **Heatmap filtered to `t02_benign_overlap`** with metric **false-positive stalls** or **stalls per trial**. Best single shot for the overcoordination claim (`file_lock` hot, `notify`/`naive` cool).
4. **Heatmap or grid row for `t01_stale_clobber` and `t03_fetch_clobber`**. Shows `naive` 0% vs `file_lock`/`git_hash` passing (hard-race baseline).
5. **Observable Event Replay** for one `t02_benign_overlap` + `file_lock` trial vs one `notify` trial. Proves trajectories exist (stall vs no stall), not just aggregate tables.
6. **Optional:** Strategy Comparison chart with **mean wall clock** or **mean tokens** selected. Supports the latency/cost trade-off in §4.

Skip: Pass/Fail donut alone (redundant with heatmap), Level C section unless you foreground Cursor C1, and extension-only `grid-v1-plus-extensions` unless you claim post-grid strategies in the 1000-word body.

### Cross-Run Findings

This note is appendix material, not part of the 1000-word body.

On the eight overlapping Agnes sensitivity tasks, `agnes-2.0-flash` scored 69.4 percent versus 57.9 percent for gpt-5-mini on the same Level A cells. It used fewer tokens on average but much more wall time. The broad ranking stayed recognizable: `file_lock` remained top or tied at the top, `git_hash` stayed strong, `notify` improved under Agnes, and AST strategies stayed in the lower half.

Solo calibration passed 96.2 percent of trials, while parallel correctness dropped under every strategy. Solo also averaged 45.7s and 44.5k tokens. Parallel `notify` was 51.8s / 72.7k tokens, `naive` was 57.1s / 78.3k, `git_hash` was 63.0s, and `file_lock` was 174.2s. That is useful because it shows the benchmark captures the real tradeoff: parallelism can add risk, tokens, or waiting if the coordination policy does not fit the failure mode.

### Level A To C

- **Level A: Strategy benchmark.** Built-in RaceBench strategies run under the same harness, tools, prompts, tasks, and oracles. These are the apples-to-apples strategy comparisons. See [`docs/adding-a-strategy.md`](../docs/adding-a-strategy.md).
- **Level B: Task and oracle suite.** The reusable task layer: seeded repos, agent briefs, collision maps, and hidden verifiers. This is what lets the same race be replayed across strategies and runtimes.
- **Level C: External runtime checks.** External systems such as Cursor or MegaAgent edit the workspace and RaceBench scores the result. These are black-box correctness and wall-clock checks unless the adapter emits RaceBench-compatible read, write, and coordination events. See [`docs/adding-an-external-runtime.md`](../docs/adding-an-external-runtime.md) and [`docs/external-coordination-protocol.md`](../docs/external-coordination-protocol.md).

In short: use Level A for strategy rankings, Level B for reusable benchmark tasks, and Level C for external-validity checks against real agent stacks.

### Agnes Sensitivity Scope

This note is appendix material, not part of the 1000-word body.

The Agnes run is intentionally a small provider-sensitivity check, not a second full strategy grid. Its purpose is to ask whether the broad baseline findings survive another OpenAI-compatible model provider on selected high-signal cells. I do not need to rerun `peer_contract`, `peer_broker`, or `adaptive_lease` on Agnes for the current submission because those strategies are post-grid extensions and still being interpreted. The main comparison remains the full gpt-5-mini Level A grid.

### Strategy Class Framing

This note is appendix material, not part of the 1000-word body.

The committed `grid-v1` headline table uses six baseline Level A strategies. The post-grid extensions add three more: `peer_contract`, `peer_broker`, and `adaptive_lease`. Together, RaceBench covers nine mechanism classes: no coordination, coarse pessimistic locking, optimistic merge, syntactic scope, static dependency scope, advisory notification, voluntary negotiation, forced negotiation, and semantic adaptive locking. I kept it at nine because each row answers a distinct coordination question; adding a tenth only for symmetry would make the taxonomy less crisp.

### Adaptive Lease Iteration

This note is appendix material, not part of the 1000-word body.

After the main grid, I tried `adaptive_lease` as a Level A extension. The goal was to keep the safety of `file_lock` while avoiding its tendency to block benign same-file work.

V1 used symbol leases for precise function/class edits, file leases for broad or uncertain edits, and stale-overwrite refusal for risky whole-file writes. On a six-task targeted slice (`t01`, `t02`, `t03`, `t04`, `rw_d`, `rw_e`), V1 went 3/6. It passed the stale/clobber and benign-overlap tasks, but failed the cascade and semantic dependency tasks. That showed that file/symbol leases were useful, but still too syntactic.

V2 added declared and inferred semantic-resource leases. Agents can call `declare_scope` for resources such as `tag.normalization`, `article.summary.schema`, `article.summary.feed_output`, `api.fetch.signature`, or `datasource.parse_dataset.public_api`. The strategy also infers a small seed catalog from paths, changed symbols, and code text. This is not a general semantics engine. It is an inspectable prototype for testing whether application-level resources can make locking more granular.

The first V2 targeted run was 6/6 correct with 0 false-positive stalls, 56.0s mean wall time, 104.7k mean tokens, and 1.5 stalls per trial. The later full extension grid gives broader evidence: `adaptive_lease` scored 63/80, or 78.8 percent. That beats `naive`, `ast_scope`, and `ast_dep`, but stays below `file_lock`, `git_hash`, and `peer_contract`. The honest claim is "promising hybrid", not "new winner". The next step is an obligation-carrying V3 and focused fixes for weak cells such as `t08`, `rw_b`, and `rw_d`.

### Peer Broker V2.5 Iteration

This note is appendix material, not part of the 1000-word body.

The peer-negotiation experiments tested two Level A strategies: voluntary `peer_contract` and forced `peer_broker`. V2.4 showed why raw forced negotiation can be expensive. `peer_broker` reached 4/5, but its `rw_e_cascade` pass took 376s, used 898k tokens, produced 17 stalls, and refused 22 writes. The oracle passed, but the process was unhealthy.

V2.5 changed `ack_with_constraints` from "refuse and retry" into "record a persistent obligation". It also reused adaptive-lease semantic-resource inference so broker sessions are triggered by resources such as `article.summary.*`, `tag.normalization`, `api.fetch.*`, and `datasource.parse_dataset.public_api`, rather than every broad overlap.

The V2.5 targeted run improved `peer_broker` from 4/5 to 5/5. Mean wall time fell from 122s to 71s, mean tokens from 237k to 140k, stalls from 4.6 to 2.4, and refused writes from 5.6 to 0.6. On `rw_e_cascade`, V2.5 dropped to 124s, 303k tokens, 5 stalls, and 0 refused writes.

The full 16-task extension grid changed the interpretation. In `results/grid-v1-plus-extensions/`, `peer_broker` scored 51/80, or 63.8 percent, below `naive` at 56/80 and far below `peer_contract` at 67/80. Its weakest cells were exactly the worrying ones: `t04_cascade`, `t05_cross_file`, `t11_irreversible`, `t12_split_view`, and `rw_c_benign_overlap`.

The honest conclusion is that peer broker should not be a headline success. It is a useful failed ablation: forcing agents to negotiate on broad overlap can convert easy work into stale obligations. The likely next design is hybrid: adaptive semantic leases first, peer broker only when an ambiguous conflict needs agent judgment, followed by a mandatory re-read before commit.

### Harder Task Suite Extension

This note is appendix material, not part of the 1000-word body.

The current task suite is still useful because it separates destructive races, benign overlap, antidependencies, cascades, and black-box runtime checks. If I had more time, I would add harder probes rather than just more repetitions: 5-8 agent dependency chains, fan-in/fan-out migrations, generated-client schema drift, and cases where one agent's correct patch invalidates another agent's previously passing tests. Those tasks would test whether the benchmark still separates strategies when coordination pressure is closer to real multi-agent development.
