# Adding an external runtime (Level C)

RaceBench has three plug-in levels:

| Level | What plugs in | Status |
|-------|---------------|--------|
| **A: Strategy** | Coordination under *our* agent loop | Shipped; see [adding-a-strategy.md](adding-a-strategy.md) |
| **B: Task** | `tasks/<name>/` repo + oracle + collision map | Shipped |
| **C: External system** | Someone else's multi-agent product edits the workspace; RaceBench scores | **This doc** |

Level C is Terminal-Bench / Harbor-inspired: the benchmark owns the **environment
and verifier**; you bring the agent system. It measures **system + oracle**
(correctness, wall clock). It does **not** produce apples-to-apples false-positive
stall or read-set-visibility numbers unless your adapter emits RaceBench
`read` / `write` / `coord` events (not required for v1).

Do **not** mix `mode: external` cells into the Level A strategy comparison table
without filtering; they are a different experiment axis.

## C1 vs C2

| Mode | Shape | Status |
|------|-------|--------|
| **C1: Harness-swap** | Fixed RaceBench roles + briefs; vendor worker loops edit the workspace | Shipped (`scripted`, `shell`, `megaagent`, `cursor`) |
| **C2: Single-goal emergent** | One seed prompt; product decides whether/how to parallelize | Deliberately unbuilt |

C1 answers: given an identical task split, does this product's *agent loop* handle
contested edits? On shared isolation, N agents share one cwd (unmediated concurrent
writers). On worktree tasks, each agent gets its own cwd from `paths.json` and the
harness merges. C1 does **not** measure product orchestration (Cursor multitask,
MegaAgent CEO recruitment, Claude Code subagent dispatch).

C2 is unbuilt on purpose: without an induced split it mostly measures single-agent
capability (SWE-bench-like). See `writeup/writeup.md` §5.

## Quick start

```bash
# Offline scripted adapter (no API key): t02 and t12
python -m runner.run_external --task t02_benign_overlap --adapter scripted \
  --out results/ext-smoke

python -m runner.run_external --task t12_split_view --adapter scripted \
  --out results/ext-smoke

# Your own process
python -m runner.run_external --task t02_benign_overlap --adapter shell \
  --command 'python my_multi_agent.py' --out results/ext-smoke

# MegaAgent vendor bridge (clone + API key in their config.py)
python -m runner.run_external --task t02_benign_overlap --adapter megaagent \
  --megaagent-root /path/to/MegaAgent --out results/ext-megaagent

# Cursor C1 (CURSOR_API_KEY; one Agent.prompt per fixed brief)
pip install -e '.[cursor]'
export CURSOR_API_KEY=cursor_...
python -m runner.run_external --task t02_benign_overlap --adapter cursor \
  --out results/ext-cursor
python -m runner.run_external --task t12_split_view --adapter cursor \
  --out results/ext-cursor
# optional: --cursor-model composer-2.5
```

## Instruction pack

Before your runtime runs, the harness writes `.racebench_instructions/` next to
the trial workspace:

```
.racebench_instructions/
  task.json          # name, isolation, agent_ids
  paths.json         # root + per-agent cwd
  agents/<id>.md     # subtask prompt + rules
```

Shell adapter env vars:

| Variable | Meaning |
|----------|---------|
| `RACEBENCH_INSTRUCTION_DIR` | path to the pack above |
| `RACEBENCH_ROOT` | shared workspace root (oracle runs here after merge) |
| `RACEBENCH_TASK` | task name |
| `RACEBENCH_TIMEOUT_S` | timeout hint |

For `isolation: worktree`, edit each agent's tree from `paths.json` → `agents.<id>`.
The harness merges into `main` before the oracle (same as Level A t12).

## Implementing a runtime

```python
from harness.external import ExternalContext, ExternalOutcome

class MyRuntime:
    name = "my_system"

    async def run(self, ctx: ExternalContext) -> ExternalOutcome:
        # read ctx.instruction_dir / paths.json; edit agent trees
        return ExternalOutcome(
            ok=True,
            agent_statuses={s.id: "done" for s in ctx.agent_specs},
        )
```

Register in `harness/external_runtimes/__init__.py` (`_RUNTIMES` dict), then:

```bash
python -m runner.run_external --task ... --adapter my_system
```

Or call `run_external_trial(task, cfg, runtime, log_path)` from Python.
Use `strategy=external_strategy_id(runtime.name)` (e.g. `ext_scripted`) so log
filenames stay unique.

## Built-in adapters

| Name | Role |
|------|------|
| `scripted` | Applies known-good edits for `t02_benign_overlap` and `t12_split_view` |
| `shell` | Runs `--command` with the env vars above; exit 0 = ok |
| `megaagent` | Vendor bridge to [Xtra-Computing/MegaAgent](https://github.com/Xtra-Computing/MegaAgent) |
| `cursor` | C1: parallel Cursor SDK `Agent.prompt` (one per brief / cwd) |

## Cursor C1 adapter

Requires `CURSOR_API_KEY` and `pip install -e '.[cursor]'` (`cursor-sdk`).

For each RaceBench agent id the runtime:

1. Reads `agents/<id>.md` as the prompt
2. Sets `local.cwd` from `paths.json` → `agents.<id>`
3. Calls `Agent.prompt` in parallel (thread pool under asyncio)
4. Honors the trial timeout; marks agents `timeout` if exceeded

**Honesty:** this measures Cursor **worker loops** on fixed RaceBench splits, not
Cursor multitask / product orchestration. Shared-isolation cells are unmediated
concurrent writers. Keep exploratory Cursor cells out of the Level A strategy table.

```bash
pip install -e '.[cursor]'
export CURSOR_API_KEY=cursor_...
python -m runner.run_external --task t02_benign_overlap --adapter cursor \
  --out results/ext-cursor
```

Offline unit tests mock the SDK (`tests/test_cursor_adapter.py`); they do not call
the Cursor API.

## MegaAgent vendor adapter

MegaAgent’s public entrypoint is `config.py` prompts + `main.py` writing under
`files/` (CEO recruits agents dynamically). RaceBench’s bridge:

1. Builds CEO prompts from the instruction pack (`adapters/megaagent/prompt.py`)
2. Wipes MegaAgent `files/`, seeds the RaceBench workspace, runs their agent loop
   (`adapters/megaagent/run_bridge.py`)
3. Copies results back (drops `todo_*.txt` / `status_*.txt` / `.git`)

**Limits:** shared isolation only (not `t12` worktree). Early trials can drift
(Gobang demo prior) or time out; we document that rather than patching upstream
MegaAgent. Measures **MegaAgent-the-system** on RaceBench oracles, not the Level A
`git_hash` reimplementation. Put your API key in the MegaAgent checkout’s
`config.py` (upstream expectation).

```bash
# 1. MegaAgent checkout (ignored under vendor/ if cloned in-repo)
git clone https://github.com/Xtra-Computing/MegaAgent.git vendor/MegaAgent
export MEGAAGENT_ROOT=$PWD/vendor/MegaAgent
# edit $MEGAAGENT_ROOT/config.py: set api_key and model

# 2. Bridge imports MegaAgent in the RaceBench venv; install its deps once:
pip install -e '.[megaagent]'

python -m runner.run_external --task t02_benign_overlap --adapter megaagent \
  --megaagent-root "$MEGAAGENT_ROOT" --out results/ext-megaagent
```

If the bridge exits immediately with `ModuleNotFoundError: chromadb`, you skipped
step 2. The harness now fails fast with the same install hint before spawning.

Level A `git_hash` remains the apples-to-apples **mechanism-class** column.

## Metrics honesty

| Metric | Level C v1 |
|--------|------------|
| Oracle correctness | yes |
| Wall clock | yes |
| Token / USD | only if adapter fills `ExternalOutcome` token fields |
| FP stalls / read-set visibility | **no** (no Strategy mediation) |
| Product orchestration / dynamic hiring | **no** (C1 forces fixed briefs) |

## Related

- Level A strategies: [adding-a-strategy.md](adding-a-strategy.md)
- Scoring helpers: `harness/trial.py` (`merge_and_score`, `finish_trial`)
- External API: `harness/external.py`
- MegaAgent bridge: `adapters/megaagent/`
- Cursor C1 runtime: `harness/external_runtimes/cursor.py`
