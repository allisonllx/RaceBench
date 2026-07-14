# Adding your coordination strategy

RaceBench is designed so **the coordination layer is swappable**. Your strategy
is the only path between agents and the shared workspace for `read_file` /
`edit_file` / `write_file`. Every trial logs a JSONL event stream; the same
metrics pipeline runs regardless of strategy.

Use this guide for Level A strategy columns. If you want to score an external
product such as Cursor, MegaAgent, or a shell script, use
[`adding-an-external-runtime.md`](adding-an-external-runtime.md) instead.

## Quick checklist

1. Create `harness/strategies/<your_strategy>.py`
2. Subclass `Strategy` from `harness/strategies/base.py`
3. Set `name = "<your_strategy>"` (this string goes in runner configs)
4. Implement `_coordinate_read` and `_coordinate_write`
5. Decorate the class with `@register`
6. Import the module in `harness/strategies/__init__.py` (registration is import-time)
7. Add `"<your_strategy>"` to `strategies:` in a runner YAML config
8. Validate offline: `pytest tests/test_trials_scripted.py` and a smoke grid run

## Minimal template

`naive` is the smallest working example (~20 lines):

```python
from harness.strategies.base import Mutation, Strategy, WriteOutcome, register


@register
class MyStrategy(Strategy):
    name = "my_strategy"

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath, agent_id=agent_id):
            return None
        return self.ws.read_file(relpath, agent_id=agent_id)

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        return await self._apply_to_current(relpath, mutation, agent_id=agent_id)
```

Register it in `harness/strategies/__init__.py`:

```python
from harness.strategies import (  # noqa: F401
    naive, file_lock, git_hash, ast_scope, ast_dep, notify, my_strategy,
)
```

Run a single offline trial:

```bash
# Copy runner/config.smoke.yaml, set strategies: [my_strategy, naive]
python -m runner.run_grid --config runner/config.my_strategy.yaml
```

## Interface reference

One `Strategy` instance is shared by all agents in a trial.

| Method | Required? | Purpose |
|--------|-----------|---------|
| `_coordinate_read(agent_id, relpath)` | **yes** | Return file content or `None` if missing/unreadable |
| `_coordinate_write(agent_id, relpath, mutation)` | **yes** | Apply or refuse a write; return `WriteOutcome` |
| `_release(agent_id)` | optional | Drop claims/locks when an agent calls `done` |
| `drain_notifications(agent_id)` | optional | Messages injected before the agent's next LLM turn |

Public `read()` / `write()` wrappers on the base class handle event logging. Call
the `_coordinate_*` hooks from your logic, not the disk directly (except via helpers).

### Mutations

Agents emit two mutation kinds (see `Mutation` in `base.py`):

- **`overwrite`**: full file replace (`write_file` tool)
- **`replace`**: single anchored string swap (`edit_file` tool); fails with
  `edit_failed` if `old_string` is not in current content

Use `_apply_to_current(relpath, mutation, agent_id=...)` for atomic apply against
current disk content. It populates `WriteOutcome.changed` with the touched symbol set.

### Write outcomes

| `status` | Meaning | Counts as success (`outcome.ok`)? |
|----------|---------|-----------------------------------|
| `applied` | Write landed | yes |
| `merged` | Write merged with concurrent edit | yes |
| `conflict` | Merge/conflict surfaced to agent | no |
| `edit_failed` | Stale anchor / cannot apply | no |
| `lock_timeout` | Blocked too long (see `lock_timeout_s`) | no |

Refused writes feed **wasted-work** metrics; successful writes with `changed` feed
**false-positive stall** detection.

### Coordination events (for stalls)

If your strategy blocks or delays agents, log `coord` events so stall metrics work:

```python
self.log.log("coord", strategy=self.name, action="blocked",
             agent=agent_id, path=relpath, holder=other_agent)
```

Recognized stall actions (see `analysis/metrics.py`): `blocked`, `lock_timeout`,
`merge_conflict`.

### Notifications

Notification-based strategies override `drain_notifications` and return strings that
the agent loop appends as user messages before the next model call (see `notify.py`).

## Worktree isolation

Tasks with `isolation: worktree` (e.g. `t12_split_view`) give each agent a private
tree under `.worktrees/<agent_id>/`. Always pass `agent_id` into:

- `self.ws.exists` / `read_file` / `write_file`
- `_apply_to_current(..., agent_id=agent_id)`

Shared-isolation tasks (`isolation: shared`, the default) use the same tree for
everyone; `agent_id` still works but is optional for disk access.

## What flows through your strategy

| Agent tool | Goes through strategy? |
|------------|------------------------|
| `read_file` | **yes**: `strategy.read()` |
| `edit_file` / `write_file` | **yes**: `strategy.write()` |
| `glob` / `grep` / `list_files` | **no**: workspace directly |
| `run_tests` / registry tools | **no** |

Read-set visibility in metrics is 1.0 for `read_file` by construction. Discovery
via grep/glob is not intercepted (documented limitation).

## Testing

**Offline scripted trials**: no API key:

```python
from harness.trial import TrialConfig, run_trial
from harness.models import ScriptedModel
from harness.scripts import get_script
from harness.task import load_task

async def test_my_strategy_on_t2(tmp_path):
    task = load_task("t02_benign_overlap")
    cfg = TrialConfig(strategy="my_strategy", n_agents=2, rep=0,
                      model_name="scripted", max_turns=12)
    log = tmp_path / "trial.jsonl"

    def factory(spec):
        return ScriptedModel(script=get_script("t02_benign_overlap", spec.id, "edit"))

    result = await run_trial(task, cfg, factory, log)
    assert result.correct
```

**Direct strategy unit test**: drive read/write without an LLM (see
`tests/test_trials_scripted.py::test_ast_dep_blocks_cross_file_claim_deterministic`).

**Full grid slice**: copy `runner/config.smoke.yaml`, swap in your strategy,
run `python -m runner.run_grid --config ...`, then
`python -m analysis.make_report results/<run_id>`.

## Swapping other pieces

| Change | Where |
|--------|-------|
| New strategy | `harness/strategies/` (this doc) |
| New task | `tasks/<name>/`: `task.yaml`, `repo/`, `oracle_tests/`, `collision_map.yaml` |
| External multi-agent system | Level C: [adding-an-external-runtime.md](adding-an-external-runtime.md) |
| Different LLM | Implement `ModelClient` in `harness/models.py`; wire `make_model_factory` in `runner/run_grid.py` |
| Agent tools / loop | `harness/agent.py`, `harness/tools.py` (not pluggable via config today) |

## Examples in-tree

| Strategy | File | Good for learning |
|----------|------|-------------------|
| `naive` | `naive.py` | Minimal pass-through |
| `file_lock` | `file_lock.py` | Blocking, `_release`, `coord` events, timeouts |
| `git_hash` | `git_hash.py` | Read snapshots, merge, `merged` / `conflict` outcomes |
| `ast_scope` | `ast_scope.py` | Symbol claims, AST diff |
| `ast_dep` | `ast_dep.py` | Cross-file dependency graph |
| `notify` | `notify.py` | Read sets, `drain_notifications` |
