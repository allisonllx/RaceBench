"""Offline tests for the Cursor Level C1 adapter (mocked SDK; no API calls)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from harness.events import EventLogger
from harness.external import ExternalContext, write_instruction_pack
from harness.external_runtimes.cursor import (
    INSTALL_HINT,
    CursorExternalRuntime,
    _usage_tokens,
    missing_cursor_deps,
)
from harness.task import load_task
from harness.workspace import Workspace


def test_usage_tokens_from_run_result():
    class Usage:
        input_tokens = 12
        output_tokens = 3

    class Result:
        usage = Usage()

    assert _usage_tokens(Result()) == (12, 3)
    assert _usage_tokens(object()) == (0, 0)


def _make_ctx(tmp_path: Path, task_name: str, n_agents: int | None = None):
    task = load_task(task_name)
    specs = task.agent_subset(n_agents or len(task.agents))
    ws = Workspace.create(
        task.repo,
        tmp_path / "ws",
        isolation=task.isolation,
        agent_ids=[s.id for s in specs],
    )
    inst = tmp_path / "inst"
    write_instruction_pack(inst, task, ws, specs)
    log = EventLogger(tmp_path / "log.jsonl")
    ctx = ExternalContext(
        task=task,
        workspace=ws,
        agent_specs=specs,
        instruction_dir=inst,
        timeout_s=30.0,
        log=log,
    )
    return ctx, ws


@pytest.mark.asyncio
async def test_cursor_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    ctx, ws = _make_ctx(tmp_path, "t02_benign_overlap")
    with patch(
        "harness.external_runtimes.cursor.missing_cursor_deps",
        return_value=[],
    ):
        out = await CursorExternalRuntime().run(ctx)
    assert out.ok is False
    assert "CURSOR_API_KEY" in out.message
    assert all(s == "error" for s in out.agent_statuses.values())
    ws.cleanup()


@pytest.mark.asyncio
async def test_cursor_missing_deps_message(tmp_path, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_test")
    ctx, ws = _make_ctx(tmp_path, "t02_benign_overlap")
    with patch(
        "harness.external_runtimes.cursor.missing_cursor_deps",
        return_value=["cursor-sdk"],
    ):
        out = await CursorExternalRuntime().run(ctx)
    assert out.ok is False
    assert "cursor-sdk" in out.message
    assert INSTALL_HINT in out.message
    ws.cleanup()


@pytest.mark.asyncio
async def test_cursor_parallel_prompts_shared_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_test")
    ctx, ws = _make_ctx(tmp_path, "t02_benign_overlap")

    with (
        patch(
            "harness.external_runtimes.cursor.missing_cursor_deps",
            return_value=[],
        ),
        patch(
            "harness.external_runtimes.cursor._run_one_agent",
            side_effect=lambda **kw: (
                kw["agent_id"],
                "done",
                "",
                100 if kw["agent_id"] == "agent-slugify" else 50,
                20 if kw["agent_id"] == "agent-slugify" else 10,
            ),
        ) as run_one,
    ):
        out = await CursorExternalRuntime(model="composer-2.5").run(ctx)

    assert out.ok is True
    assert out.agent_statuses == {
        "agent-slugify": "done",
        "agent-truncate": "done",
    }
    assert out.prompt_tokens == 150
    assert out.completion_tokens == 30
    assert run_one.call_count == 2
    kw_by_id = {c.kwargs["agent_id"]: c.kwargs for c in run_one.call_args_list}
    assert set(kw_by_id) == {"agent-slugify", "agent-truncate"}
    root = str(ws.root)
    assert kw_by_id["agent-slugify"]["cwd"] == root
    assert kw_by_id["agent-truncate"]["cwd"] == root
    assert "slugify" in kw_by_id["agent-slugify"]["prompt"].lower()
    assert "truncate" in kw_by_id["agent-truncate"]["prompt"].lower()
    assert kw_by_id["agent-slugify"]["model"] == "composer-2.5"
    assert kw_by_id["agent-slugify"]["api_key"] == "cursor_test"
    ws.cleanup()


@pytest.mark.asyncio
async def test_cursor_worktree_distinct_cwds(tmp_path, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_test")
    ctx, ws = _make_ctx(tmp_path, "t12_split_view")
    assert ctx.task.isolation == "worktree"

    with (
        patch(
            "harness.external_runtimes.cursor.missing_cursor_deps",
            return_value=[],
        ),
        patch(
            "harness.external_runtimes.cursor._run_one_agent",
            side_effect=lambda **kw: (kw["agent_id"], "done", "", 0, 0),
        ) as run_one,
    ):
        out = await CursorExternalRuntime().run(ctx)

    assert out.ok is True
    assert run_one.call_count == 2
    cwds = {c.kwargs["agent_id"]: c.kwargs["cwd"] for c in run_one.call_args_list}
    assert cwds["agent-core"] != cwds["agent-ext"]
    assert Path(cwds["agent-core"]).is_dir()
    assert Path(cwds["agent-ext"]).is_dir()
    ws.cleanup()


@pytest.mark.asyncio
async def test_cursor_timeout_marks_agents(tmp_path, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "cursor_test")
    ctx, ws = _make_ctx(tmp_path, "t02_benign_overlap")
    ctx.timeout_s = 0.05

    def slow(**_kw):
        import time

        time.sleep(2.0)
        return ("x", "done", "", 0, 0)

    with (
        patch(
            "harness.external_runtimes.cursor.missing_cursor_deps",
            return_value=[],
        ),
        patch(
            "harness.external_runtimes.cursor._run_one_agent",
            side_effect=slow,
        ),
    ):
        out = await CursorExternalRuntime().run(ctx)

    assert out.ok is False
    assert all(s == "timeout" for s in out.agent_statuses.values())
    assert "timed out" in out.message.lower()
    ws.cleanup()


def test_missing_cursor_deps_detects_absence():
    # May or may not be installed in this env; just ensure the helper returns a list.
    assert isinstance(missing_cursor_deps(), list)
