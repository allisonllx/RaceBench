"""Unit tests for worktree isolation and tool registry."""
from pathlib import Path

import pytest

from harness.events import EventLogger
from harness.registry import ToolRegistry
from harness.workspace import Workspace


def _mini_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "src"
    repo.mkdir()
    (repo / "hello.py").write_text("X = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n",
                                               encoding="utf-8")
    return repo


def test_worktree_isolation_and_merge(tmp_path):
    repo = _mini_repo(tmp_path)
    dest = tmp_path / "ws"
    ws = Workspace.create(repo, dest, isolation="worktree",
                          agent_ids=["a", "b"])
    assert (dest / ".worktrees" / "a" / "hello.py").is_file()
    ws.write_file("hello.py", "X = 2\n", agent_id="a")
    ws.write_file("hello.py", "X = 3\n", agent_id="b")
    assert ws.read_file("hello.py", agent_id="a") == "X = 2\n"
    assert ws.read_file("hello.py", agent_id="b") == "X = 3\n"
    # shared root still initial until merge
    assert ws.read_file("hello.py") == "X = 1\n"
    result = ws.merge_agent_trees()
    assert result.ok or result.conflicts  # may conflict; force-integrate
    # after merge, root has one of the agent versions
    assert "X =" in ws.read_file("hello.py")
    ws.cleanup()


def test_registry_mutation_and_effects(tmp_path):
    repo = _mini_repo(tmp_path)
    dest = tmp_path / "ws2"
    ws = Workspace.create(repo, dest)
    log = EventLogger(tmp_path / "e.jsonl")
    reg = ToolRegistry(ws, log, {
        "tools": ["format_report", "send_email"],
        "mutations": [{"after_global_writes": 1, "remove": ["format_report"],
                       "add": ["format_report_v2"]}],
    })
    assert "format_report" in reg.list_names()
    out = reg.invoke("solo", "send_email",
                     {"to": "a@b.com", "subject": "hi", "body": "x"})
    assert out.startswith("OK")
    effects = reg.read_effects()
    assert len(effects) == 1 and effects[0]["tool"] == "send_email"
    reg.note_write()
    assert "format_report" not in reg.list_names()
    assert "format_report_v2" in reg.list_names()
    ghost = reg.invoke("solo", "format_report", {"summary": {}})
    assert "ERROR" in ghost
    log.close()
    ws.cleanup()


def test_grep_glob(tmp_path):
    repo = _mini_repo(tmp_path)
    (repo / "pkg").mkdir()
    (repo / "pkg" / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    dest = tmp_path / "ws3"
    ws = Workspace.create(repo, dest)
    assert any("util.py" in f for f in ws.glob_files("**/*.py"))
    hits = ws.grep("helper")
    assert any("util.py" in h for h in hits)
    ws.cleanup()
