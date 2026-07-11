"""Offline tests for the MegaAgent Level C vendor adapter."""
from __future__ import annotations

from pathlib import Path

import pytest

from adapters.megaagent.prompt import build_prompts, load_agent_briefs
from adapters.megaagent.sync import collect_files, seed_files
from harness.external import ExternalContext, ExternalOutcome, write_instruction_pack
from harness.external_runtimes.megaagent import MegaAgentRuntime
from harness.task import load_task
from harness.workspace import Workspace


def test_prompt_builder_includes_t2_subtasks(tmp_path):
    task = load_task("t2_benign_overlap")
    specs = task.agent_subset(2)
    ws = Workspace.create(task.repo, tmp_path / "ws", isolation="shared",
                          agent_ids=[s.id for s in specs])
    inst = tmp_path / "inst"
    write_instruction_pack(inst, task, ws, specs)

    briefs = load_agent_briefs(inst)
    assert {b[0] for b in briefs} == {"agent-slugify", "agent-truncate"}

    initial, additional = build_prompts(inst)
    assert "agent-slugify" in initial
    assert "agent-truncate" in initial
    assert "EXISTING" in initial or "existing" in initial.lower()
    assert "oracle_tests" in additional
    assert "t2_benign_overlap" in initial
    ws.cleanup()


def test_seed_and_collect_round_trip(tmp_path):
    rb = tmp_path / "racebench"
    rb.mkdir()
    (rb / "stringutils.py").write_text("MARKER = 1\n", encoding="utf-8")
    (rb / ".racebench_git").mkdir()
    (rb / ".racebench_git" / "HEAD").write_text("x", encoding="utf-8")
    (rb / "oracle_tests").mkdir()
    (rb / "oracle_tests" / "test_x.py").write_text("pass\n", encoding="utf-8")

    files = tmp_path / "mega_files"
    n = seed_files(rb, files)
    assert n == 1
    assert (files / "stringutils.py").read_text(encoding="utf-8") == "MARKER = 1\n"
    assert not (files / "oracle_tests").exists()
    assert not (files / ".racebench_git").exists()

    (files / "todo_Bob.txt").write_text("do stuff\n", encoding="utf-8")
    (files / "status_Bob.txt").write_text("done\n", encoding="utf-8")
    (files / "stringutils.py").write_text("MARKER = 2\n", encoding="utf-8")
    (files / ".gitkeep").write_text("x", encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()
    n_back = collect_files(files, out)
    assert (out / "stringutils.py").read_text(encoding="utf-8") == "MARKER = 2\n"
    assert not (out / "todo_Bob.txt").exists()
    assert not (out / "status_Bob.txt").exists()
    assert not (out / ".gitkeep").exists()
    assert n_back == 1


@pytest.mark.asyncio
async def test_megaagent_refuses_worktree(tmp_path):
    task = load_task("t12_split_view")
    assert task.isolation == "worktree"
    specs = task.agent_subset(2)
    ws = Workspace.create(
        task.repo, tmp_path / "ws", isolation="worktree",
        agent_ids=[s.id for s in specs],
    )
    from harness.events import EventLogger

    log = EventLogger(tmp_path / "log.jsonl")
    ctx = ExternalContext(
        task=task,
        workspace=ws,
        agent_specs=specs,
        instruction_dir=tmp_path / "inst",
        timeout_s=30.0,
        log=log,
    )
    (tmp_path / "inst").mkdir()
    runtime = MegaAgentRuntime(megaagent_root=tmp_path / "fake_mega")
    (tmp_path / "fake_mega").mkdir()
    (tmp_path / "fake_mega" / "main.py").write_text("# stub\n", encoding="utf-8")

    outcome = await runtime.run(ctx)
    assert isinstance(outcome, ExternalOutcome)
    assert not outcome.ok
    assert "worktree" in outcome.message.lower()
    log.close()
    ws.cleanup()


@pytest.mark.asyncio
async def test_megaagent_missing_root_message(tmp_path):
    task = load_task("t2_benign_overlap")
    specs = task.agent_subset(2)
    ws = Workspace.create(
        task.repo, tmp_path / "ws", isolation="shared",
        agent_ids=[s.id for s in specs],
    )
    from harness.events import EventLogger

    log = EventLogger(tmp_path / "log.jsonl")
    ctx = ExternalContext(
        task=task,
        workspace=ws,
        agent_specs=specs,
        instruction_dir=tmp_path / "inst",
        timeout_s=30.0,
        log=log,
    )
    runtime = MegaAgentRuntime(megaagent_root=None)
    # Ensure env does not accidentally provide a root
    import os
    old = os.environ.pop("MEGAAGENT_ROOT", None)
    try:
        outcome = await runtime.run(ctx)
    finally:
        if old is not None:
            os.environ["MEGAAGENT_ROOT"] = old

    assert not outcome.ok
    assert "MEGAAGENT_ROOT" in outcome.message
    log.close()
    ws.cleanup()
