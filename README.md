# RaceBench

**A neutral, reproducible benchmark for multi-agent coding coordination strategies.**

Every published coordination mechanism for parallel LLM coding agents — CRDT merging
(CodeCRDT), git-hash optimistic concurrency (MegaAgent), notification-based advisory
control (CoAgent) — is evaluated by its own authors, on its own task suite, with its own
metrics. Nobody has published the boring comparison table. ConcurBench is that table:
a fixed suite of collision-seeded coding tasks, run under interchangeable coordination
strategies, with per-mechanism cost accounting.

## What it measures

| Metric | Why it matters |
|---|---|
| Correctness | hidden oracle test pass rate per trial |
| Wall-clock / total tokens | the price of coordination |
| Wasted-work rate | tokens burned on blocked, conflicted, or failed actions |
| **False-positive stall rate** | coordination triggered on provably-disjoint edits (nobody reports this today) |
| Read-set visibility | fraction of agent reads the coordination layer can observe |

## Strategies

All strategies implement the same interface (`harness/strategies/base.py`) and are
labeled "X-style" — they are our faithful-but-minimal reimplementations, not the
original authors' systems.

1. `naive` — direct writes, last write wins. The floor.
2. `file_lock` — file-level lock on first touch, held until the agent finishes.
3. `git_hash` — MegaAgent-style optimistic concurrency: record content at read, 3-way
   merge on write, surface conflicts back to the agent.
4. `ast_scope` — symbol-level write claims via Python AST diff (Grit/Phantom/Weave-style,
   see prior art below): two agents editing disjoint functions in the same file never stall.
5. `notify` — CoAgent-lite advisory notifications: writes land immediately; agents whose
   read set intersects a landed write get a notice injected into context and self-judge.

Ruled out for the hackathon window (with reasons, see `writeup/`): full CRDT substrate,
CoAgent's full MTPO with serialization pre-order and saga inverses, 8+ agent scale.

## Tasks

Six purpose-built mini-repos in `tasks/`, one per failure mode, each with a documented
collision map and a hidden pytest oracle:

| Task | Failure mode | Agents |
|---|---|---|
| `t1_stale_read` | stale read / lost update | 2 |
| `t2_benign_overlap` | disjoint functions, same file (false-positive probe) | 2 |
| `t3_ww_clobber` | write-write on the same function | 2 |
| `t4_cascade` | causal cascade across a dependency chain | 4 |
| `t5_cross_file` | cross-file symbol dependency | 2 |
| `t6_feature_pair` | CooperBench-style realistic feature pair | 2 |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# harness self-test (scripted agents, no API key needed)
pytest

# single trial with scripted agents (offline demo)
python -m runner.run_grid --config runner/config.smoke.yaml

# real grid (needs OPENAI_API_KEY)
export OPENAI_API_KEY=sk-...
python -m runner.run_grid --config runner/config.example.yaml

# report + plots from event logs
python -m analysis.make_report results/<run_id>
```

## Repo layout

```
harness/     agent loop, coordination layer, strategies/, event log
tasks/       one dir per task: task.yaml, repo/, oracle_tests/, collision_map.yaml
runner/      grid configs, orchestrator, cost guardrails
analysis/    metrics computation, plots, report notebook
results/     committed JSONL event logs (the reproducibility artifact)
writeup/     five-pillar write-up + demo video script
```

## Prior art and attribution

- CodeCRDT — arXiv:2510.18893 (CRDT coordination; motivates the confound metrics)
- CoAgent / MTPO — arXiv:2606.15376 (notification-based advisory control)
- MegaAgent — arXiv:2408.09955 (git-hash + mutex; basis of `git_hash`)
- Verified Detection of Concurrency Anomalies — arXiv:2606.17182 (failure-mode taxonomy)
- CooperBench — arXiv:2601.13295 (collaborative coding tasks; complementary axis —
  it varies communication, we vary the coordination mechanism)
- Specification Gap — arXiv:2603.24284, and the tools Grit, Phantom, Weave
  (prior art for AST-level conflict detection; `ast_scope` is our neutral
  reimplementation for measurement, not a novel mechanism)
