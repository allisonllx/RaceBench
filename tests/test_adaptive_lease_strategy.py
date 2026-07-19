import asyncio
from pathlib import Path

from analysis.metrics import trial_metrics
from harness.events import EventLogger, read_events
from harness.models import ScriptedModel
from harness.scripts import get_script
from harness.strategies import get_strategy
from harness.strategies.adaptive_lease import AdaptiveLeaseStrategy
from harness.strategies.base import Mutation
from harness.task import load_task
from harness.trial import TrialConfig, run_trial
from harness.workspace import Workspace


async def _run_scripted(task_name, variant, tmp_path):
    task = load_task(task_name)
    cfg = TrialConfig(
        strategy="adaptive_lease",
        n_agents=2,
        rep=0,
        model_name=f"scripted-{variant}",
        lock_timeout_s=0.2,
        trial_timeout_s=120.0,
        workdir=tmp_path / "ws",
    )
    log_path = tmp_path / f"{task_name}__adaptive_lease-{variant}.jsonl"

    def factory(spec):
        return ScriptedModel(script=get_script(task_name, spec.id, variant))

    result = await run_trial(task, cfg, factory, log_path)
    return result, log_path


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "conduit" / "services").mkdir(parents=True)
    (repo / "mod.py").write_text(
        "VALUE = 1\n\n\n"
        "def alpha():\n"
        "    return 'a'\n\n\n"
        "def beta():\n"
        "    return 'b'\n",
        encoding="utf-8",
    )
    (repo / "conduit" / "services" / "articles.py").write_text(
        "def create_article(tag_list):\n"
        "    tags = []\n"
        "    for tag in tag_list:\n"
        "        tags.append(tag)\n"
        "    return tags\n\n\n"
        "def list_articles(tag):\n"
        "    return tag\n",
        encoding="utf-8",
    )
    (repo / "conduit" / "services" / "feed.py").write_text(
        "def tag_article_count(conn, tag):\n"
        "    return conn.count(tag)\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    return repo


def _strategy(tmp_path, agent_ids=("a", "b"), timeout=0.2):
    ws = Workspace.create(_repo(tmp_path), tmp_path / "ws")
    logger = EventLogger(tmp_path / "events.jsonl")
    strategy = AdaptiveLeaseStrategy(ws, logger, list(agent_ids),
                                     lock_timeout_s=timeout)
    return ws, logger, strategy


def _finish(ws, logger):
    logger.close()
    ws.cleanup()


async def test_adaptive_lease_registered():
    assert get_strategy("adaptive_lease") is AdaptiveLeaseStrategy


async def test_adaptive_lease_exposes_declare_scope_and_protocol_note(tmp_path):
    ws, logger, strategy = _strategy(tmp_path)
    try:
        names = {
            schema["function"]["name"]
            for schema in strategy.extra_tool_schemas()
        }
        assert names == {"declare_scope"}
        note = "\n".join(strategy.drain_notifications("a"))
        assert "semantic resources" in note
        assert "tag.normalization" in note
    finally:
        _finish(ws, logger)


async def test_adaptive_lease_no_stall_on_benign_same_file_symbols(tmp_path):
    result, log = await _run_scripted("t02_benign_overlap", "edit", tmp_path)

    assert result.correct
    metrics = trial_metrics(log)
    assert metrics["stall_events"] == 0
    events = read_events(log)
    assert any(
        event.get("event") == "coord"
        and event.get("action") == "lease_acquired"
        and event.get("lease_level") == "symbol"
        for event in events
    )


async def test_adaptive_lease_disjoint_packages_correct_no_stalls(tmp_path):
    result, log = await _run_scripted("t09_overhead", "edit", tmp_path)

    assert result.correct
    metrics = trial_metrics(log)
    assert metrics["stall_events"] == 0


async def test_adaptive_lease_declared_resource_blocks_peer_scope(tmp_path):
    ws, logger, strategy = _strategy(tmp_path, timeout=0.05)
    try:
        response = await strategy.handle_strategy_tool("a", "declare_scope", {
            "resources": ["tag.normalization"],
            "path": "conduit/services/articles.py",
            "symbols": ["create_article"],
            "summary": "lowercase article tags",
        })
        blocked = await strategy.handle_strategy_tool("b", "declare_scope", {
            "resources": ["tag.normalization"],
            "path": "conduit/services/feed.py",
            "symbols": ["tag_article_count"],
            "summary": "count tags consistently",
        })

        assert response is not None and response.startswith("OK:")
        assert blocked is not None and blocked.startswith("ERROR:")
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "scope_declared"
            and event.get("resources") == ["tag.normalization"]
            for event in events
        )
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "scope_timeout"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_adaptive_lease_inferred_resource_blocks_cross_file_write(tmp_path):
    ws, logger, strategy = _strategy(tmp_path, timeout=0.05)
    try:
        await strategy.write(
            "a",
            "conduit/services/articles.py",
            Mutation(
                kind="replace",
                old_string="tags.append(tag)",
                new_string="tags.append(tag.lower())",
            ),
        )
        outcome = await strategy.write(
            "b",
            "conduit/services/feed.py",
            Mutation(
                kind="replace",
                old_string="return conn.count(tag)",
                new_string="return conn.count(tag.lower())",
            ),
        )

        assert not outcome.ok
        assert outcome.status == "lock_timeout"
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "blocked"
            and event.get("lease_level") == "resource"
            and event.get("resources") == ["tag.normalization"]
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_adaptive_lease_semantic_read_notice_on_resource_overlap(tmp_path):
    ws, logger, strategy = _strategy(tmp_path)
    try:
        await strategy.read("b", "conduit/services/articles.py")
        await strategy.write(
            "a",
            "conduit/services/articles.py",
            Mutation(
                kind="replace",
                old_string="tags.append(tag)",
                new_string="tags.append(tag.lower())",
            ),
        )

        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "semantic_read_write_intersection"
            and event.get("resources") == ["tag.normalization"]
            for event in events
        )
        notice = "\n".join(strategy.drain_notifications("b"))
        assert "tag.normalization" in notice
        assert "Re-read affected files" in notice
    finally:
        _finish(ws, logger)


async def test_adaptive_lease_refuses_stale_whole_file_overwrite(tmp_path):
    ws, logger, strategy = _strategy(tmp_path)
    try:
        original = await strategy.read("a", "mod.py")
        await strategy.read("b", "mod.py")
        assert original is not None

        a_version = original.replace("return 'a'", "return 'a1'")
        b_version = original.replace("return 'b'", "return 'b2'")

        first = await strategy.write(
            "a", "mod.py", Mutation(kind="overwrite", content=a_version))
        await strategy.agent_done("a")
        second = await strategy.write(
            "b", "mod.py", Mutation(kind="overwrite", content=b_version))

        assert first.ok
        assert not second.ok
        assert second.status == "conflict"
        assert "changed since your last read" in second.message
        assert "return 'a1'" in ws.read_file("mod.py")
        assert "return 'b2'" not in ws.read_file("mod.py")
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "stale_overwrite_refused"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_adaptive_lease_module_change_blocks_symbol_write(tmp_path):
    ws, logger, strategy = _strategy(tmp_path, timeout=0.05)
    try:
        await strategy.read("a", "mod.py")
        await strategy.write(
            "a",
            "mod.py",
            Mutation(kind="replace", old_string="VALUE = 1", new_string="VALUE = 2"),
        )

        blocked = asyncio.create_task(strategy.write(
            "b",
            "mod.py",
            Mutation(
                kind="replace",
                old_string="def beta():\n    return 'b'\n",
                new_string="def beta():\n    return 'b2'\n",
            ),
        ))
        outcome = await blocked

        assert not outcome.ok
        assert outcome.status == "lock_timeout"
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "blocked"
            and event.get("lease_level") == "symbol"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_adaptive_lease_releases_file_fallback_after_done(tmp_path):
    ws, logger, strategy = _strategy(tmp_path, timeout=0.2)
    try:
        await strategy.read("a", "mod.py")
        first = await strategy.write(
            "a",
            "mod.py",
            Mutation(kind="replace", old_string="VALUE = 1", new_string="VALUE = 2"),
        )
        await strategy.agent_done("a")
        second = await strategy.write(
            "b",
            "mod.py",
            Mutation(
                kind="replace",
                old_string="def beta():\n    return 'b'\n",
                new_string="def beta():\n    return 'b2'\n",
            ),
        )

        assert first.ok
        assert second.ok
        assert "VALUE = 2" in ws.read_file("mod.py")
        assert "return 'b2'" in ws.read_file("mod.py")
    finally:
        _finish(ws, logger)
