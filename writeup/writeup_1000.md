# RaceBench: A Neutral Benchmark for Multi-Agent Coordination

## 1. Problem

Parallel coding agents are easy to launch but hard to trust. When two agents edit the same repository, they can clobber each other's work, read stale state, coordinate too much, or waste tokens. Existing proposals usually report gains inside one system or task distribution, making it hard to tell whether the mechanism helped or the product simply gave it easier work.

RaceBench asks a narrower question: given the same repository, prompts, models, task pairs, and oracles, which coordination policies actually reduce race failures, and when do they create avoidable stalls? My success criteria were set before building the final grid: the benchmark should replay fixed race tasks, compare strategies against a naive baseline, record correctness, wall time, token use, wasted work, stalls, and false-positive stalls, and preserve enough logs for another person to audit each trial.

The novelty is not just measuring failures. It is also measuring overcoordination. False-positive stalls, where a strategy blocks safe parallelism, are rarely foregrounded in prior multi-agent coordination work, but they matter in practice because a safe agent team that serializes everything is not very useful.

## 2. Approach

RaceBench is a small, instrumented benchmark harness. Each trial runs two to four agents on a seeded coding task. The harness records read and write events, applies a coordination strategy, runs the task oracle, and writes JSONL logs plus aggregate tables. The current suite has 16 tasks and 6 Level A strategies: `naive`, `file_lock`, `notify`, `optimistic`, `ast_merge`, and `dependency_graph`.

I considered three broader multi-agent coordination approaches and ruled them out for this submission. First, an auto-merge editor that rewrites two agents' patches into one final patch. I ruled it out because a pass or fail would depend on both the coordination rule and the **merge algorithm**, so the result would be harder to interpret. Second, a full CoAgent or MTPO-style saga layer. That is valuable, but requires inverse operations and workflow semantics beyond this coding benchmark. Third, direct comparison with commercial or open-source agent products like Claude Code and Cursor. However, without shared mediation hooks (e.g. tool call usage), that mostly measures each product's hidden planner, not a reusable coordination policy.

I chose an instrumented Level A harness because it gives the cleanest attribution. The task, model, oracle, and prompts stay fixed, while only the coordination mechanism changes. I still support Level C black-box runtime checks, but I label them separately because they are correctness and wall-clock checks, not apples-to-apples strategy comparisons unless the runtime emits RaceBench-compatible events.

## 3. Evidence

The main run, `results/grid-v1`, contains 480 replayable trials: 16 tasks, 6 strategies, 5 repetitions. The pooled pass rate was 74.4 percent, with about $13.56 spent and 37.7M tokens recorded. The report pipeline validates JSONL structure, required events, token-accounting fallbacks, and external-mode tagging, then generates aggregate tables, deterministic bootstrap confidence intervals, and a static HTML explorer.

The baseline is intentionally simple. `naive` gives the floor for "just run both agents." On hard clobber cases, the floor collapses: in `t01_same_line` and `t03_fetch_clobber`, naive went 0/5 while `file_lock` went 5/5. That supports the modest claim that coordination is necessary for destructive overlap. On `rw_d` antidependency cases, naive went 1/5 while `notify` went 5/5, showing that lightweight notification can help when the issue is stale reads rather than simultaneous writes.

The evidence also shows trade-offs. In `t02_disjoint`, `file_lock` stayed correct but produced 5/5 false-positive stalls on benign parallel work. That is why RaceBench tracks stalls separately from correctness. A strategy can pass tests and still destroy concurrency. The five repetitions per cell are not enough to claim universal statistical truth, but they are enough to catch consistent directional effects and to expose failure classes for follow-up runs.

## 4. Constraints

The biggest constraint was cost. I intentionally kept the grid small and reused the same logs for the final report instead of buying a larger sweep. I also did not run a second model family because of API and token limits. My prediction is that the relative shape of the results, for example file locks helping hard clobbers but overblocking disjoint work, would remain similar across models because those effects come from repository state and strategy semantics. Still, that is a hypothesis, not proven evidence.

There are also realism constraints. RaceBench currently uses a local Conduit-style in-process setup, fixed task pairs, and deterministic oracles. That makes the benchmark reproducible and cheap, but it does not capture long-horizon planning, changing user requirements, flaky external services, or heterogeneous agent products.

## 5. Honesty & Trajectory

RaceBench is not a plug-and-play benchmark for arbitrary existing agents. A black-box runtime such as Cursor, MegaAgent, or another orchestrated system can be scored as Level C, but without read/write intent hooks it collapses toward a naive external check from RaceBench's perspective. A true external strategy needs a mediation protocol around `on_read`, `on_write_intent`, `decision`, `on_write_committed`, and `on_agent_done`.

Known failure modes are specific. The AST merge strategy is still too coarse for many real refactors. The dependency graph strategy depends on simplified static observations and can miss dynamic behavior. The task suite is small enough that strategies can accidentally fit it. The benchmark mostly studies two-agent races, not larger teams. It also rewards strategies implemented inside the harness more directly than external products, which is why I separate Level A and Level C throughout the docs and report.

With two more weeks, I would add a small second-model run on the highest-signal tasks, rerun the existing Cursor C1 smoke with more repetitions, add read/write intent hooks for one external adapter so it can be compared as a true strategy, and improve AST/dependency granularity. The claim would still stay modest: RaceBench is a reusable, auditable benchmark for coordination mechanisms, plus a task and oracle suite for black-box runtime checks.

---

## Appendix: Links And Level Guide

This appendix is supporting material and is not part of the five-pillar 1000-word body.

### Full Results

- Static results explorer: [`results/grid-v1/report.html`](../results/grid-v1/report.html)
- Main result logs and tables: [`results/grid-v1/`](../results/grid-v1/)
- Cursor C1 exploratory logs: [`results/ext-cursor/`](../results/ext-cursor/)
- Report generator code: [`analysis/html_report.py`](../analysis/html_report.py)

### Reproduction Commands

```bash
python -m analysis.validate_logs results/grid-v1 --expect-trials 480
python -m analysis.make_report results/grid-v1
```

### Level A To C

- **Level A: Strategy benchmark.** Built-in RaceBench strategies run under the same harness, tools, prompts, tasks, and oracles. These are the apples-to-apples strategy comparisons. See [`docs/adding-a-strategy.md`](../docs/adding-a-strategy.md).
- **Level B: Task and oracle suite.** The reusable task layer: seeded repos, agent briefs, collision maps, and hidden verifiers. This is what lets the same race be replayed across strategies and runtimes.
- **Level C: External runtime checks.** External systems such as Cursor or MegaAgent edit the workspace and RaceBench scores the result. These are black-box correctness and wall-clock checks unless the adapter emits RaceBench-compatible read, write, and coordination events. See [`docs/adding-an-external-runtime.md`](../docs/adding-an-external-runtime.md) and [`docs/external-coordination-protocol.md`](../docs/external-coordination-protocol.md).

In short: use Level A for strategy rankings, Level B for reusable benchmark tasks, and Level C for external-validity checks against real agent stacks.
