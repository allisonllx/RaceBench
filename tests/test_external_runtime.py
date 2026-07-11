"""Level C external-runtime trials (no in-process Agent/Strategy)."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.external import external_strategy_id, run_external_trial
from harness.external_runtimes import get_runtime
from harness.scripts import T2_SLUGIFY_NEW, T2_SLUGIFY_OLD, T2_TRUNCATE_NEW, T2_TRUNCATE_OLD
from harness.task import load_task
from harness.trial import TrialConfig


@pytest.mark.asyncio
async def test_scripted_external_t2_passes_oracle(tmp_path):
    task = load_task("t2_benign_overlap")
    runtime = get_runtime("scripted")
    cfg = TrialConfig(
        strategy=external_strategy_id(runtime.name),
        n_agents=2,
        rep=0,
        model_name="external:scripted",
        workdir=tmp_path / "ws",
        trial_timeout_s=60.0,
    )
    log = tmp_path / "t2.jsonl"
    result = await run_external_trial(task, cfg, runtime, log)
    assert result.correct, (
        f"oracle {result.oracle_passed}/{result.oracle_total} "
        f"statuses={result.agent_statuses}"
    )
    assert result.agent_statuses == {
        "agent-slugify": "done",
        "agent-truncate": "done",
    }
    text = log.read_text(encoding="utf-8")
    assert '"mode": "external"' in text
    assert '"adapter": "scripted"' in text
    # Must not go through Strategy / Agent imports in this path's call stack —
    # presence of trial events without read/write strategy events is enough.
    assert '"event": "read"' not in text
    assert '"event": "write"' not in text


@pytest.mark.asyncio
async def test_scripted_external_t12_worktree_passes_oracle(tmp_path):
    task = load_task("t12_split_view")
    assert task.isolation == "worktree"
    runtime = get_runtime("scripted")
    cfg = TrialConfig(
        strategy=external_strategy_id(runtime.name),
        n_agents=2,
        rep=0,
        model_name="external:scripted",
        workdir=tmp_path / "ws",
        trial_timeout_s=60.0,
    )
    log = tmp_path / "t12.jsonl"
    result = await run_external_trial(task, cfg, runtime, log)
    assert result.correct, (
        f"oracle {result.oracle_passed}/{result.oracle_total} "
        f"statuses={result.agent_statuses}"
    )
    text = log.read_text(encoding="utf-8")
    assert '"event": "worktree_merge"' in text


@pytest.mark.asyncio
async def test_shell_external_t2_passes_oracle(tmp_path):
    """Shell adapter runs a small Python snippet that applies t2 edits."""
    task = load_task("t2_benign_overlap")
    # Inline script: read paths.json and apply both replacements on shared root.
    script = tmp_path / "edit_t2.py"
    script.write_text(
        f'''\
import json, os
from pathlib import Path
root = Path(os.environ["RACEBENCH_ROOT"])
inst = Path(os.environ["RACEBENCH_INSTRUCTION_DIR"])
paths = json.loads((inst / "paths.json").read_text())
# shared isolation: all agent cwds are the same root
target = root / "stringutils.py"
text = target.read_text()
text = text.replace({T2_SLUGIFY_OLD!r}, {T2_SLUGIFY_NEW!r}, 1)
text = text.replace({T2_TRUNCATE_OLD!r}, {T2_TRUNCATE_NEW!r}, 1)
target.write_text(text)
''',
        encoding="utf-8",
    )
    runtime = get_runtime("shell", command=f"python {script}")
    cfg = TrialConfig(
        strategy=external_strategy_id(runtime.name),
        n_agents=2,
        rep=0,
        model_name="external:shell",
        workdir=tmp_path / "ws",
        trial_timeout_s=60.0,
    )
    log = tmp_path / "t2_shell.jsonl"
    result = await run_external_trial(task, cfg, runtime, log)
    assert result.correct, (
        f"oracle {result.oracle_passed}/{result.oracle_total} "
        f"statuses={result.agent_statuses}"
    )
    text = log.read_text(encoding="utf-8")
    assert '"adapter": "shell"' in text
    assert '"event": "external_shell_end"' in text
