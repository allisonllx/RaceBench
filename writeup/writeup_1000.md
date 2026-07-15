# RaceBench: A Neutral Benchmark for Multi-Agent Coordination

## 1. Problem

Parallel coding agents are easy to launch but hard to trust. When two agents edit the same repository, they can clobber each other's work, read stale state, coordinate too much, or waste tokens. Existing proposals usually report gains inside one system or task distribution, making it hard to tell whether the mechanism helped or the product simply gave it easier work.

RaceBench asks a narrower question: given the same repository, prompts, models, task pairs, and oracles, which coordination policies actually reduce race failures, and when do they create avoidable stalls? My success criteria were set before building the final grid: the benchmark should replay fixed race tasks, compare strategies against a naive baseline, record correctness, wall time, token use, wasted work, stalls, and false-positive stalls, and preserve enough logs for another person to audit each trial.

The novelty is not just measuring failures. It is also measuring overcoordination. False-positive stalls, where a strategy blocks safe parallelism, are rarely foregrounded in prior multi-agent coordination work, but they matter in practice because a safe agent team that serializes everything is not very useful.

## 2. Approach

RaceBench is a small, instrumented benchmark harness. Each trial runs two agents on a seeded coding task. The harness records read and write events, applies a coordination strategy, runs the task oracle, and writes JSONL logs plus aggregate tables. The current suite has 16 tasks and 6 Level A strategies: `naive`, `file_lock`, `notify`, `optimistic`, `ast_merge`, and `dependency_graph`.

I considered three broader approaches and ruled them out for this submission. First, I could have built a full CRDT-like editing substrate. That would mix coordination quality with the engineering quality of a large merge system. Second, I could have implemented a full CoAgent or MTPO-style saga layer. That is valuable, but requires inverse operations and workflow semantics beyond this coding benchmark. Third, I could have compared commercial or open-source agent products directly. Without shared mediation hooks, that mostly measures each product's hidden planner, not a reusable coordination policy.

I chose an instrumented Level A harness because it gives the cleanest attribution. The task, model, oracle, and prompts stay fixed, while only the coordination mechanism changes. I still support Level C black-box runtime checks, but I label them separately because they are correctness and wall-clock checks, not apples-to-apples strategy comparisons unless the runtime emits RaceBench-compatible events.

## 3. Evidence

The main run, `results/grid-v1`, contains 480 replayable trials: 16 tasks, 6 strategies, 5 repetitions. The pooled pass rate was 74.4 percent, with about $13.56 spent and 37.7M tokens recorded. The report pipeline now includes `python -m analysis.validate_logs results/grid-v1 --expect-trials 480` for JSONL validation, required event checks, token-accounting fallbacks, and external-mode tagging. `python -m analysis.make_report results/grid-v1` generates aggregate CSV/Markdown tables, deterministic bootstrap confidence intervals, and a static `report.html` explorer.

The baseline is intentionally simple. `naive` gives the floor for "just run both agents." On hard clobber cases, the floor collapses: in `t01_same_line` and `t03_fetch_clobber`, naive went 0/5 while `file_lock` went 5/5. That supports the modest claim that coordination is necessary for destructive overlap. On `rw_d` antidependency cases, naive went 1/5 while `notify` went 5/5, showing that lightweight notification can help when the issue is stale reads rather than simultaneous writes.

The evidence also shows trade-offs. In `t02_disjoint`, `file_lock` stayed correct but produced 5/5 false-positive stalls on benign parallel work. That is why RaceBench tracks stalls separately from correctness. A strategy can pass tests and still destroy concurrency. The five repetitions per cell are not enough to claim universal statistical truth, but they are enough to catch consistent directional effects and to expose failure classes for follow-up runs.

## 4. Constraints

The biggest constraint was cost. I intentionally kept the grid small and reused the same logs for the final report instead of buying a larger sweep. I also did not run a second model family because of API and token limits. My prediction is that the relative shape of the results, for example file locks helping hard clobbers but overblocking disjoint work, would remain similar across models because those effects come from repository state and strategy semantics. Still, that is a hypothesis, not proven evidence.

There are also realism constraints. RaceBench currently uses a local Conduit-style in-process setup, fixed task pairs, and deterministic oracles. That makes the benchmark reproducible and cheap, but it does not capture long-horizon planning, changing user requirements, flaky external services, or heterogeneous agent products. Token accounting sometimes requires fallback fields, so the validator reports those cases rather than hiding them.

## 5. Honesty & Trajectory

RaceBench is not a plug-and-play benchmark for arbitrary existing agents. A black-box runtime such as Cursor, MegaAgent, or another orchestrated system can be scored as Level C, but without read/write intent hooks it collapses toward a naive external check from RaceBench's perspective. A true external strategy needs a mediation protocol around `on_read`, `on_write_intent`, `decision`, `on_write_committed`, and `on_agent_done`.

Known failure modes are specific. The AST merge strategy is still too coarse for many real refactors. The dependency graph strategy depends on simplified static observations and can miss dynamic behavior. The task suite is small enough that strategies can accidentally fit it. The benchmark mostly studies two-agent races, not larger teams. It also rewards strategies implemented inside the harness more directly than external products, which is why I separate Level A and Level C throughout the docs and report.

With two more weeks, I would add a sentinel second-model run on the highest-signal tasks instead of rerunning the full grid, expand Level C smoke tests for real external runtimes, implement the external mediation protocol for at least one adapter, and improve AST/dependency granularity to distinguish top-level file conflicts from safe symbol-level edits. The claim would still stay modest: RaceBench is a reusable, auditable benchmark for coordination mechanisms, plus a task and oracle suite for black-box runtime checks.
