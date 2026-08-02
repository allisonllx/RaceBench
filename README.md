<div align="center">
  <h1>RaceBench</h1>
  <p><strong>A neutral, reproducible benchmark for multi-agent coding coordination strategies.</strong></p>
  <p>
    Parallel LLM coding agents are a shipping product category, but every proposed
    coordination mechanism is still evaluated by its own authors, on its own task
    suite, with its own metrics. Nobody has published the neutral comparison table.
  </p>
  <p>
    RaceBench is that table: a fixed suite of collision-seeded coding tasks, run
    under interchangeable coordination strategies, with per-mechanism cost accounting.
  </p>
  <p>
    <img
      src="assets/fig-metrics-bar.png"
      alt="RaceBench static results explorer with metric cards, filters, and strategy comparison charts"
      width="860"
    >
  </p>
  <p>
    <img
      src="assets/fig-heatmap-correctness.png"
      alt="RaceBench task by strategy heatmap showing correctness by strategy"
      width="860"
    >
  </p>
</div>

---

## Start here

1. Open the headline explorer: [`results/grid-v1/report.html`](results/grid-v1/report.html)
   (480 trials, 6 Level A strategies; regenerate with `python -m analysis.make_report results/grid-v1`)
2. Read the practical takeaways: [`docs/coordination-decision-guide.md`](docs/coordination-decision-guide.md)
3. Read the external-runtime boundary: [`docs/external-coordination-protocol.md`](docs/external-coordination-protocol.md)
4. Read the submission write-up: [`writeup/writeup_1000.md`](writeup/writeup_1000.md)
5. Optional: 9-strategy post-grid explorer:
   [`results/grid-v1-plus-extensions/report.html`](results/grid-v1-plus-extensions/report.html)
6. Validate locally:

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
| **False-positive stall rate** | coordination triggered on provably-disjoint edits |
| Read-set visibility | fraction of agent reads the coordination layer can observe |
| Event / turn profile | LLM / tool / read / write / search / coord diagnostics |

The headline Level A table holds agent tools, tasks, and event logging fixed and
swaps only the coordination mechanism.

## Levels A / B / C

| Level | What you plug in | Guide |
|---|---|---|
| **A: Strategy** | `_coordinate_read` / `_coordinate_write` under our agent loop | [`docs/adding-a-strategy.md`](docs/adding-a-strategy.md) |
| **B: Task** | `tasks/<name>/` repo, collision map, hidden oracle | [`docs/tasks.md`](docs/tasks.md) |
| **C: External runtime** | Third-party multi-agent system edits the workspace; we score | [`docs/adding-an-external-runtime.md`](docs/adding-an-external-runtime.md) |

**A and B** are the apples-to-apples strategy grid. **C** scores a whole external
product on the same tasks and oracles (correctness and wall clock unless the
adapter emits RaceBench events). Do not mix Level C cells into the Level A table.
C1 (harness-forced role split) vs C2 (product-chosen parallelization) are
documented in the external-runtime guide.

## Strategies (Level A)

Six baseline strategies in `grid-v1`, plus three post-grid extensions:

1. `naive` — last writer wins (floor)
2. `file_lock` — file-level lock until agent done
3. `git_hash` — optimistic snapshot + 3-way merge
4. `ast_scope` — same-file symbol claims
5. `ast_dep` — symbol claims plus import/use deps
6. `notify` — advisory notices to intersecting readers
7. `peer_contract` — voluntary peer negotiation *(extension)*
8. `peer_broker` — forced broker negotiation *(extension)*
9. `adaptive_lease` — symbol / file / semantic leases *(extension)*

Details: [`docs/strategies.md`](docs/strategies.md). Claim narrative:
[`writeup/writeup_1000.md`](writeup/writeup_1000.md#strategy-catalog).

## Tasks (Level B)

16 collision-seeded tasks (t01–t12 probe suite + four Conduit `rw_*` races), each
with fixed briefs, a collision map, and a hidden pytest oracle. Full table and
tool notes: [`docs/tasks.md`](docs/tasks.md).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                                          # harness self-test (no API key)
python -m runner.run_grid --config runner/configs/config.smoke.yaml   # offline smoke

# real grid (needs OPENAI_API_KEY)
# echo 'OPENAI_API_KEY=sk-...' > .env
python -m runner.run_grid --config runner/configs/config.example.yaml

python -m analysis.validate_logs results/grid-v1 --expect-trials 480
python -m analysis.make_report results/grid-v1
```

If you do not activate the virtualenv, replace `python` with `.venv/bin/python`.
Extension grids, Agnes sensitivity, cross-run analysis, and Level C smokes:
[`docs/running-experiments.md`](docs/running-experiments.md).

## Repo layout

```
harness/     agent loop, coordination layer, strategies/, event log
tasks/       one dir per task: task.yaml, repo/, oracle_tests/, collision_map.yaml
runner/      grid configs, orchestrator, cost guardrails
analysis/    metrics, plots, HTML report
adapters/    Level C vendor bridges
docs/        guides (strategies, tasks, experiments, external runtimes)
results/     committed JSONL event logs
writeup/     five-pillar write-up + demo video script
```

## Docs

- [`docs/coordination-decision-guide.md`](docs/coordination-decision-guide.md) — when to use which strategy
- [`docs/strategies.md`](docs/strategies.md) — Level A mechanism catalog
- [`docs/tasks.md`](docs/tasks.md) — task suite table
- [`docs/running-experiments.md`](docs/running-experiments.md) — grids, Agnes, cross-run, Level C smokes
- [`docs/adding-a-strategy.md`](docs/adding-a-strategy.md) — add a Level A strategy
- [`docs/adding-an-external-runtime.md`](docs/adding-an-external-runtime.md) — Level C adapters (C1/C2)
- [`docs/external-coordination-protocol.md`](docs/external-coordination-protocol.md) — mediation boundary
- [`docs/prior-art.md`](docs/prior-art.md) — citations and attribution
- [`docs/adaptive-lease-strategy-plan.md`](docs/adaptive-lease-strategy-plan.md) / [`docs/peer-contract-strategy-plan.md`](docs/peer-contract-strategy-plan.md) — extension design notes

## Prior art

RaceBench reimplements mechanism classes for neutral measurement; it does not
claim to invent them. Full list: [`docs/prior-art.md`](docs/prior-art.md).
