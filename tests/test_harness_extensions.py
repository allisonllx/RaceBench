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
    # Same file, incompatible edits → conflict + force-integrate of one side
    assert result.ok or result.conflicts
    assert "X =" in ws.read_file("hello.py")
    ws.cleanup()


def test_worktree_disjoint_edits_merge_clean(tmp_path):
    """Non-overlapping file edits from two agents both land on main."""
    repo = _mini_repo(tmp_path)
    (repo / "a.py").write_text("A = 0\n", encoding="utf-8")
    (repo / "b.py").write_text("B = 0\n", encoding="utf-8")
    dest = tmp_path / "ws_disjoint"
    ws = Workspace.create(repo, dest, isolation="worktree",
                          agent_ids=["a", "b"])
    ws.write_file("a.py", "A = 1\n", agent_id="a")
    ws.write_file("b.py", "B = 2\n", agent_id="b")
    result = ws.merge_agent_trees()
    assert result.ok, result.message
    assert result.conflicts == []
    assert ws.read_file("a.py") == "A = 1\n"
    assert ws.read_file("b.py") == "B = 2\n"
    ws.cleanup()


@pytest.mark.asyncio
async def test_t12_ideal_edits_merge_both_methods(tmp_path):
    """Reference-quality greet + farewell edits must survive merge (oracle)."""
    import shutil
    from harness.task import load_task

    task = load_task("t12_split_view")
    dest = tmp_path / "t12"
    ws = Workspace.create(task.repo, dest, isolation="worktree",
                          agent_ids=["agent-core", "agent-ext"])

    core_api = (
        'class Greeter:\n'
        '    """Public greeting API — agents extend this class in separate worktrees."""\n'
        '\n'
        '    def greet(self, name: str) -> str:\n'
        '        return f"hello,{name}"\n'
        '\n'
        '    def ping(self) -> str:\n'
        '        return "pong"\n'
    )
    ext_api = (
        'class Greeter:\n'
        '    """Public greeting API — agents extend this class in separate worktrees."""\n'
        '\n'
        '    def ping(self) -> str:\n'
        '        return "pong"\n'
        '\n'
        '    def farewell(self, name: str) -> str:\n'
        '        return f"bye,{name}"\n'
    )
    ws.write_file("lib/api.py", core_api, agent_id="agent-core")
    ws.write_file(
        "apps/cli.py",
        'from lib.api import Greeter\n\n\ndef welcome(name: str) -> str:\n'
        '    return Greeter().greet(name)\n',
        agent_id="agent-core",
    )
    ws.write_file("lib/api.py", ext_api, agent_id="agent-ext")
    ws.write_file(
        "services/worker.py",
        'from lib.api import Greeter\n\n\ndef goodbye(name: str) -> str:\n'
        '    return Greeter().farewell(name)\n',
        agent_id="agent-ext",
    )

    result = ws.merge_agent_trees()
    assert result.ok, f"merge failed: {result.message}"
    api = ws.read_file("lib/api.py")
    assert "def greet" in api and "def farewell" in api and "def ping" in api

    oracle_dst = dest / "oracle_tests"
    if oracle_dst.exists():
        shutil.rmtree(oracle_dst)
    shutil.copytree(task.oracle_tests, oracle_dst)
    test = await ws.run_pytest("oracle_tests")
    assert test.all_passed, test.output
    ws.cleanup()

@pytest.mark.asyncio
async def test_t12_conflicting_rewrites_still_keep_both_methods(tmp_path):
    """Whole-class rewrites that only add different methods should 3-way merge."""
    import shutil
    from harness.task import load_task

    task = load_task("t12_split_view")
    dest = tmp_path / "t12b"
    ws = Workspace.create(task.repo, dest, isolation="worktree",
                          agent_ids=["agent-core", "agent-ext"])
    # Simulate LLM-style full-class overwrites (common in logs).
    ws.write_file(
        "lib/api.py",
        'class Greeter:\n'
        '    """Public greeting API — agents extend this class in separate worktrees."""\n\n'
        '    def greet(self, name: str) -> str:\n'
        '        return f"hello,{name}"\n\n'
        '    def ping(self) -> str:\n'
        '        return "pong"\n',
        agent_id="agent-core",
    )
    ws.write_file(
        "apps/cli.py",
        'from lib.api import Greeter\n\n\ndef welcome(name: str) -> str:\n'
        '    return Greeter().greet(name)\n',
        agent_id="agent-core",
    )
    ws.write_file(
        "lib/api.py",
        'class Greeter:\n'
        '    """Public greeting API — agents extend this class in separate worktrees."""\n\n'
        '    def ping(self) -> str:\n'
        '        return "pong"\n\n'
        '    def farewell(self, name: str) -> str:\n'
        '        return f"bye,{name}"\n',
        agent_id="agent-ext",
    )
    ws.write_file(
        "services/worker.py",
        'from lib.api import Greeter\n\n\ndef goodbye(name: str) -> str:\n'
        '    return Greeter().farewell(name)\n',
        agent_id="agent-ext",
    )
    result = ws.merge_agent_trees()
    api = ws.read_file("lib/api.py")
    assert "def greet" in api and "def farewell" in api, api
    oracle_dst = dest / "oracle_tests"
    if oracle_dst.exists():
        shutil.rmtree(oracle_dst)
    shutil.copytree(task.oracle_tests, oracle_dst)
    test = await ws.run_pytest("oracle_tests")
    assert test.all_passed, test.output
    ws.cleanup()


@pytest.mark.asyncio
async def test_t12_docstring_conflict_still_unions_methods(tmp_path):
    """Conflicting class docstring must not drop the other agent's method."""
    import shutil
    from harness.task import load_task

    task = load_task("t12_split_view")
    dest = tmp_path / "t12c"
    ws = Workspace.create(task.repo, dest, isolation="worktree",
                          agent_ids=["agent-core", "agent-ext"])
    ws.write_file(
        "lib/api.py",
        'class Greeter:\n    """core doc"""\n\n'
        '    def greet(self, name: str) -> str:\n'
        '        return f"hello,{name}"\n\n'
        '    def ping(self) -> str:\n'
        '        return "pong"\n',
        agent_id="agent-core",
    )
    ws.write_file(
        "apps/cli.py",
        'from lib.api import Greeter\n\n\ndef welcome(name: str) -> str:\n'
        '    return Greeter().greet(name)\n',
        agent_id="agent-core",
    )
    ws.write_file(
        "lib/api.py",
        'class Greeter:\n    """ext doc"""\n\n'
        '    def ping(self) -> str:\n'
        '        return "pong"\n\n'
        '    def farewell(self, name: str) -> str:\n'
        '        return f"bye,{name}"\n',
        agent_id="agent-ext",
    )
    ws.write_file(
        "services/worker.py",
        'from lib.api import Greeter\n\n\ndef goodbye(name: str) -> str:\n'
        '    return Greeter().farewell(name)\n',
        agent_id="agent-ext",
    )
    ws.merge_agent_trees()
    api = ws.read_file("lib/api.py")
    assert "def greet" in api and "def farewell" in api, api
    oracle_dst = dest / "oracle_tests"
    if oracle_dst.exists():
        shutil.rmtree(oracle_dst)
    shutil.copytree(task.oracle_tests, oracle_dst)
    test = await ws.run_pytest("oracle_tests")
    assert test.all_passed, test.output
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
