# Running experiments

Operational cookbook for re-running grids, sensitivity checks, and combined
reports. For a first install and smoke test, see the [README quickstart](../README.md#quickstart).

## Frozen result folders

The frozen submission evidence stays at the top level of `results/`:

| Folder | Role |
|---|---|
| `results/grid-v1/` | Main 6-strategy baseline, 480 trials |
| `results/grid-v1-extensions/` | Three post-grid strategies, 240 trials |
| `results/grid-v1-plus-extensions/` | Combined 9-strategy report, 720 trials |
| `results/grid-v1-calibration/` | Solo-agent calibration |
| `results/grid-v1-agnes-sensitivity/` | Second-provider sensitivity check |
| `results/cross-run-analysis/` | Provider and solo-versus-parallel dashboard |
| `results/ext-cursor/` | Level C Cursor black-box smoke check |
| `results/grid-v1-toolarg-rerun/` | Tool-argument audit rerun |

Older targeted iterations, scripted smoke outputs, and incomplete external
debug runs are archived locally under `results/_archive/nonofficial-runs/`.

## Headline baseline

```bash
python -m analysis.validate_logs results/grid-v1 --expect-trials 480
# optional: treat nested tool-call argument schema drift as validation errors
# python -m analysis.validate_logs results/grid-v1 --expect-trials 480 --strict-tool-args
python -m analysis.make_report results/grid-v1
# optional: pass the runner config that holds prices:
# python -m analysis.make_report results/<run_id> --prices-config runner/configs/config.example.yaml
```

## Tool argument audit rerun

Strict tool-argument validation can flag old logs where the model omitted a
required tool field. Do a surgical rerun before deciding whether any headline
claim needs a note or replacement cell. This keeps the original result folders
unchanged and writes only the flagged missing-field cells from `grid-v1` and
`grid-v1-extensions`.

```bash
python -m runner.run_grid --config runner/configs/config.toolarg-rerun.yaml
python -m analysis.validate_logs results/grid-v1-toolarg-rerun \
  --expect-trials 16 --strict-tool-args
python -m analysis.make_report results/grid-v1-toolarg-rerun \
  --prices-config runner/configs/config.toolarg-rerun.yaml
```

The strict validator also reports older `must_preserve` string-vs-array drift in
some peer-contract logs. Those are useful audit warnings, but this minimal rerun
targets missing required fields first because those are most likely to affect
correctness. A strict audit can still print warnings when a malformed model
attempt was followed by `tool_arg_invalid`; that means the runtime rejected the
call before execution and asked the agent to retry.

## Adaptive lease (targeted)

`adaptive_lease` is an experimental Level A hybrid. Use the offline smoke first,
then the targeted live config only if you want a cheap one-rep signal. Historical
targeted logs are archived under `results/_archive/nonofficial-runs/`; rerunning
the config will recreate `results/grid-v1-adaptive-lease-targeted-v2/`.

```bash
python -m runner.run_grid --config runner/configs/config.smoke.yaml
python -m runner.run_grid --config runner/configs/config.adaptive-lease-targeted.yaml
python -m analysis.validate_logs results/grid-v1-adaptive-lease-targeted-v2
python -m analysis.make_report results/grid-v1-adaptive-lease-targeted-v2 \
  --prices-config runner/configs/config.adaptive-lease-targeted.yaml
```

See also [`strategies.md`](strategies.md) and
[`adaptive-lease-strategy-plan.md`](adaptive-lease-strategy-plan.md).

## Peer negotiation (targeted)

`peer_contract` and `peer_broker` are experimental Level A strategies. Use the
targeted config first because it spends real model tokens and focuses only on
tasks where peer negotiation should matter.

The current target folder keeps the raw run label `v5`, but the docs refer to
that broker refinement as conceptual V2.5 so V3 can remain reserved for the
future external mediation protocol. Historical targeted peer logs are archived
under `results/_archive/nonofficial-runs/`; rerunning the config will recreate
`results/grid-v1-peer-targeted-v5/`.

```bash
python -m runner.run_grid --config runner/configs/config.peer-targeted.yaml
python -m analysis.validate_logs results/grid-v1-peer-targeted-v5
python -m analysis.make_report results/grid-v1-peer-targeted-v5 \
  --prices-config runner/configs/config.peer-targeted.yaml
```

See also [`peer-contract-strategy-plan.md`](peer-contract-strategy-plan.md).

## Extension grid (9 strategies)

After the targeted runs look stable, run the three experimental Level A
strategies across the same 16 tasks and 5 reps as `grid-v1`. This keeps the
original baseline folder stable and writes a separate 240-trial extension run.

```bash
python -m runner.run_grid --config runner/configs/config.extensions.yaml
python -m analysis.validate_logs results/grid-v1-extensions --expect-trials 240
python -m analysis.make_report results/grid-v1-extensions \
  --prices-config runner/configs/config.extensions.yaml

# combined 9-strategy explorer, preserving both source result folders
python -m analysis.make_report results/grid-v1 results/grid-v1-extensions \
  --out results/grid-v1-plus-extensions \
  --prices-config runner/configs/config.example.yaml
```

## Agnes model sensitivity

```bash
# second-provider sensitivity check, 144 trials
# echo 'AGNES_API_KEY=sk-...' >> .env
python -m runner.run_grid --config runner/configs/config.agnes-sensitivity.yaml --parallel 1
python -m analysis.validate_logs results/grid-v1-agnes-sensitivity --expect-trials 144
python -m analysis.make_report results/grid-v1-agnes-sensitivity \
  --prices-config runner/configs/config.agnes-sensitivity.yaml

# optional full Agnes grid, 480 trials, only if credits/time allow
python -m runner.run_grid --config runner/configs/config.agnes-full.yaml --parallel 1
python -m analysis.validate_logs results/grid-v1-agnes --expect-trials 480
python -m analysis.make_report results/grid-v1-agnes \
  --prices-config runner/configs/config.agnes-full.yaml
```

Use `results/grid-v1-agnes-sensitivity/` as a model-sensitivity check, not as a
replacement for the Level A OpenAI grid. If the sensitivity ranking agrees with
`grid-v1`, the writeup can claim the main coordination conclusions were checked
against a second OpenAI-compatible model provider. The Agnes run is intentionally
scoped to the baseline/high-signal strategy set. It does not need to rerun
`peer_contract`, `peer_broker`, or `adaptive_lease`, since those are post-grid
exploratory strategies and the marginal value of a second-provider rerun is lower
than finishing the primary analysis.

The Agnes configs include a conservative request-per-minute cap and rerun
temporary provider-error logs so `429` throttles are not counted as benchmark
failures. They use a published list-rate estimate for analytical cost comparison
(`$0.03 / 1M` input tokens and `$0.15 / 1M` output tokens for `agnes-2.0-flash`).
Actual out-of-pocket spend may be `$0` under hackathon or free credits, but the
reports and dashboards keep that separate from model cost.

## Cross-run analysis

After the Agnes sensitivity run has enough completed logs, compare it against
the OpenAI grid and the solo calibration run:

```bash
python -m analysis.compare_runs \
  --provider-runs results/grid-v1 results/grid-v1-agnes-sensitivity \
  --solo-run results/grid-v1-calibration \
  --parallel-run results/grid-v1 \
  --out results/cross-run-analysis
```

This writes provider/model tables for overlapping Level A cells, plus
solo-versus-parallel tables and a static dashboard at
`results/cross-run-analysis/dashboard.html`. The provider comparison answers
whether strategy rankings are stable across model providers. The solo comparison
answers whether a task fails because of coordination races or because one agent
could not solve the task even without concurrency. The dashboard also exposes
turn and event diagnostics such as LLM calls, tool calls, reads, writes,
searches, coordination events, tokens per turn, and estimated USD per trial.

Direction matters. Provider advantage means the later provider run is compared
against the first provider run. With the command above, that is
`results/grid-v1-agnes-sensitivity` versus `results/grid-v1`. Parallel advantage
means `--parallel-run` versus `--solo-run`, so the command above compares
`results/grid-v1` versus `results/grid-v1-calibration`. The CSV/Markdown tables
include a `direction` column, and the `delta_*` columns should be read as
direction-aware advantage scores, not raw subtraction in every case. For
lower-is-better metrics such as tokens, runtime, and turns, the sign is flipped
before coloring so green means the first named run is better.

`analysis.make_report` also writes `event_profile_by_strategy.*`,
`event_profile_by_task_strategy.*`, and `agent_activity.*`. These tables are
diagnostics: they explain where a result came from by showing event mix, turn
count, and which agent read, wrote, searched, or spent tokens. Keep them
separate from Level C external-runtime comparisons unless the adapter emits the
same RaceBench event schema.

## Level C external smokes

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

Built-in adapters: `scripted`, `shell`, MegaAgent (`adapters/megaagent/`), and
Cursor (C1 via `cursor-sdk`). Full API, C1/C2 framing, and metrics:
[`adding-an-external-runtime.md`](adding-an-external-runtime.md).
