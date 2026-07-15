<div align="center">
  <h1>RaceBench</h1>
  <p><strong>A neutral, reproducible benchmark for multi-agent coding coordination strategies.</strong></p>
  <p>
    Parallel LLM coding agents are a shipping product category, but every proposed
    coordination mechanism is still evaluated by its own authors, on its own task
    suite, with its own metrics. Nobody has published the neutral comparison table.
    RaceBench is that table: a fixed suite of collision-seeded coding tasks, run
    under interchangeable coordination strategies, with per-mechanism cost accounting.
  </p>
</div>

## Start here

If you are new to the repo, use this path:

1. Open the static explorer: [`results/grid-v1/report.html`](results/grid-v1/report.html)
   (regenerate with `python -m analysis.make_report results/grid-v1`)
2. Read the practical takeaways: [`docs/coordination-decision-guide.md`](docs/coordination-decision-guide.md)
3. Read the external-runtime boundary: [`docs/external-coordination-protocol.md`](docs/external-coordination-protocol.md)
4. Read the benchmark claim and limits: [`writeup/writeup.md`](writeup/writeup.md)
5. Run validation locally:

```bash
python -m analysis.validate_logs results/grid-v1 --expect-trials 480
python -m analysis.make_report results/grid-v1
```

## What it measures

| Metric | Why it matters |
|---|---|
| Correctness | hidden oracle test pass rate per trial |
| Wall-clock / total tokens | the price of coordination |
| Wasted-work rate | tokens burned on blocked, conflicted, or failed actions |
| **False-positive stall rate** | coordination triggered on provably-disjoint edits (nobody reports this today) |
| Read-set visibility | fraction of agent reads the coordination layer can observe |

The headline comparison table (Levels A and B below) holds agent tools, tasks, and
event logging fixed and swaps only the coordination mechanism.

## Extensibility

RaceBench has three plug-in levels. **A and B** are the apples-to-apples axis used
for the strategy grid. **C** is separate: it scores a whole external multi-agent
product on the same tasks and oracles.

| Level | What you plug in | Status | Guide |
|---|---|---|---|
| **A: Strategy** | `_coordinate_read` / `_coordinate_write` under our agent loop | Shipped | [`docs/adding-a-strategy.md`](docs/adding-a-strategy.md) |
| **B: Task** | `tasks/<name>/` repo, collision map, hidden oracle | Shipped | `tasks/` layout below |
| **C: External runtime** | Third-party multi-agent system edits the workspace; we score | Shipped (bridge) | [`docs/adding-an-external-runtime.md`](docs/adding-an-external-runtime.md) |

Level C is Terminal-Bench / Harbor-inspired. RaceBench owns the **environment and
verifier**; you bring the agent system. Level C reports correctness and wall
clock only unless your adapter emits RaceBench `read` / `write` / `coord` events.
Do **not** mix Level C cells into the Level A strategy table without filtering.
They answer a different question.

**C1 (harness-swap)** forces fixed RaceBench roles and briefs onto a vendor worker
loop (what `megaagent` and `cursor` do today). **C2
(single-goal emergent)** would give one seed prompt and let the product choose
whether to parallelize; that mode is deliberately unbuilt (see `writeup/writeup.md`
§5). Note that tasks fix named `agent-*` roles so collision maps stay deterministic; C1 therefore measures contested edits under a known split, not open-ended
decomposition or product orchestration.

**Purpose of C1.** RaceBench fixes who does what; the vendor runs each brief with
its own tools and does not use our coordination layer. That is closest to Level A
`naive`, but with a real product worker stack (e.g. Cursor + composer) instead of
our harness. C1 answers a narrow question: on the same tasks and splits, do
seeded races still show up when a shipping agent edits the repo, or were failures
mostly due to our toy tool API? Treat those numbers as **harness vs
harness**, not as a strategy ranking.
Early one-pass smokes (`results/ext-cursor/`) are documented in `writeup/writeup.md`
§5. Details there also cover why strategy rankings stay in Level A.

### Level A: Built-in strategies

All strategies implement the same interface (`harness/strategies/base.py`) and are
labeled "X-style": faithful-but-minimal reimplementations, not the original authors'
systems.

1. `naive`: direct writes, last write wins. The floor.
2. `file_lock`: file-level lock on first touch, held until the agent finishes.
3. `git_hash`: MegaAgent-style optimistic concurrency: record content at read, 3-way
   merge on write, surface conflicts back to the agent.
4. `ast_scope`: symbol-level write claims via Python AST diff (Grit/Phantom/Weave-style,
   see prior art below): two agents editing disjoint functions in the same file never stall.
5. `ast_dep`: `ast_scope` plus a workspace import/use dependency graph: stalls when a
   write races a claimed cross-file definition or use-site.
6. `notify`: CoAgent-lite advisory notifications: writes land immediately; agents whose
   read set intersects a landed write get a notice injected into context and self-judge.

**Adding your strategy (Level A).** Implement two methods, register with `@register`,
import in `harness/strategies/__init__.py`, add the name to `strategies:` in a runner
config, and smoke-test with `runner/config.smoke.yaml` (scripted agents, no API key).
Full checklist: [`docs/adding-a-strategy.md`](docs/adding-a-strategy.md).

**Out of scope for the hackathon window** (reasons in `writeup/`): full CRDT substrate,
CoAgent's full MTPO with serialization pre-order and saga inverses, 8+ agent scale;
lock-on-write-only `file_lock` and `git_hash`+worktree hybrids (redundant with
`ast_scope` / task-level `isolation: worktree`).

### Level C: External runtimes

```bash
# Offline scripted adapter (no API key)
python -m runner.run_external --task t02_benign_overlap --adapter scripted \
  --out results/ext-smoke

# Your own process
python -m runner.run_external --task t02_benign_overlap --adapter shell \
  --command 'python my_multi_agent.py' --out results/ext-smoke

# MegaAgent vendor bridge (clone + API key in their config.py)
pip install -e '.[megaagent]'
python -m runner.run_external --task t02_benign_overlap --adapter megaagent \
  --megaagent-root /path/to/MegaAgent --out results/ext-megaagent

# Cursor C1 (CURSOR_API_KEY; one Agent.prompt per fixed brief)
pip install -e '.[cursor]'
python -m runner.run_external --task t02_benign_overlap --adapter cursor \
  --out results/ext-cursor
```

Built-in adapters: `scripted`, `shell`, **MegaAgent** (`adapters/megaagent/`,
shared isolation only), and **Cursor** (C1 via `cursor-sdk`, shared + worktree).
Before each trial the harness writes `.racebench_instructions/` (task metadata,
paths, per-agent briefs). Full API and metrics table:
[`docs/adding-an-external-runtime.md`](docs/adding-an-external-runtime.md).

## Tasks (Level B)

Twelve purpose-built mini-repos in `tasks/` (probe suite) plus a **FastAPI
Conduit external-validity track** (`rw_*`). Each has a collision map, hidden
pytest oracle, and reference solution.

| Task | Failure mode | Agents | Notes |
|---|---|---|---|
| `t01_stale_clobber` | stale read / lost update (whole-file rewrite) | 2 | hardened; v1 in `tasks/_archive/` |
| `t02_benign_overlap` | disjoint functions, same file (FP probe) | 2 | `benign: true` |
| `t03_fetch_clobber` | write-write on the same function (whole-fetch rewrite) | 2 | hardened; v1 in `tasks/_archive/` |
| `t04_cascade` | causal cascade across a dependency chain | 4 | multi-module |
| `t05_cross_file` | cross-file symbol dependency | 2 | multi-module |
| `t06_feature_pair` | CooperBench-style feature pair | 2 | multi-module |
| `t07_rw_canary` | antidependency / silent invalidation | 2 | |
| `t08_livelock` | lock wait-cycle / livelock stress | 2 | opposite edit order |
| `t09_overhead` | overhead-masks-benefit (disjoint pkgs) | 2 | `benign: true` |
| `t10_phantom_tool` | tool-registry drift | 2 | needs `list_tools` |
| `t11_irreversible` | external-effect reordering | 2 | `.effects.jsonl` order |
| `t12_split_view` | worktree divergence | 2 | `isolation: worktree` |
| `rw_c_benign_overlap` | benign same-file on Conduit | 2 | FastAPI+SQLite+Pydantic |
| `rw_b_signature_drift` | stale-read / signature drift | 2 | Conduit `format_article` |
| `rw_d_tag_antidependency` | tag filter vs count silent invalidation | 2 | Conduit tags |
| `rw_e_cascade` | 3-agent causal cascade | 3 | Conduit Article.summary |

The Conduit base lives in `tasks/_conduit_base/` (shared source). Host deps
include `fastapi`, `httpx`, and `pydantic`; reinstall with
`pip install -e ".[dev]"` after pull. Oracles use FastAPI `TestClient` (no
live server / Newman / Postgres).

## Tools

Agents get instrumented file tools (`read_file`, `write_file`, `edit_file`,
`list_files`, `run_tests`, `done`) plus `grep` / `glob`. Tasks with a
`registry:` block also expose `list_tools` / `invoke_tool` and irreversible
effect tools (`send_email`, `deploy`, `charge`). Workspace isolation is
`shared` (default) or `worktree` (per-agent trees merged before the oracle).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# harness self-test (scripted agents, no API key needed)
pytest

# single trial with scripted agents (offline demo)
python -m runner.run_grid --config runner/config.smoke.yaml

# real grid (needs OPENAI_API_KEY in .env or your shell)
# echo 'OPENAI_API_KEY=sk-...' > .env
python -m runner.run_grid --config runner/config.example.yaml
# optional: override concurrent trials (config default: parallel: 4)
# python -m runner.run_grid --config runner/config.example.yaml --parallel 8

# validate replay logs, then regenerate tables, CI intervals, plots, and report.html
python -m analysis.validate_logs results/grid-v1 --expect-trials 480
python -m analysis.make_report results/grid-v1
# optional: pass the runner config that holds prices:
# python -m analysis.make_report results/<run_id> --prices-config runner/config.example.yaml
```

If you do not activate the virtualenv, replace `python` with `.venv/bin/python`.

## Repo layout

```
harness/     agent loop, coordination layer, strategies/, event log
tasks/       one dir per task: task.yaml, repo/, oracle_tests/, collision_map.yaml
runner/      grid configs, orchestrator, cost guardrails
analysis/    metrics computation, plots, report notebook
adapters/    Level C vendor bridges (e.g. megaagent/)
docs/        contributor guides (adding-a-strategy, adding-an-external-runtime)
results/     committed JSONL event logs (the reproducibility artifact)
writeup/     five-pillar write-up + demo video script
```

## Prior art and attribution

- CodeCRDT: arXiv:2510.18893 (CRDT coordination; motivates the confound metrics)
- CoAgent / MTPO: arXiv:2606.15376 (notification-based advisory control)
- MegaAgent: arXiv:2408.09955 (git-hash + mutex; basis of `git_hash`)
- Verified Detection of Concurrency Anomalies: arXiv:2606.17182 (failure-mode taxonomy)
- CooperBench: arXiv:2601.13295 (collaborative coding tasks; complementary axis:
  it varies communication, we vary the coordination mechanism)
- Specification Gap: arXiv:2603.24284, and the tools Grit, Phantom, Weave
  (prior art for AST-level conflict detection; `ast_scope` is our neutral
  reimplementation for measurement, not a novel mechanism)
