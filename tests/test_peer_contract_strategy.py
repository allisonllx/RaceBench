import asyncio

from harness.agent import Agent
from harness.events import EventLogger, read_events
from harness.models import ScriptedModel
from harness.scripts import (
    T1_TIMEOUT_DEFAULT,
    T2_SLUGIFY_NEW,
    T2_SLUGIFY_OLD,
)
from harness.strategies import get_strategy
from harness.strategies.base import Mutation
from harness.strategies.peer_contract import PeerContractStrategy
from harness.symbols import MODULE_SYMBOL
from harness.task import load_task
from harness.workspace import Workspace


def _strategy_workspace(tmp_path, task_name, agent_ids, timeout=1.0):
    task = load_task(task_name)
    ws = Workspace.create(task.repo, tmp_path / "ws")
    logger = EventLogger(tmp_path / "events.jsonl")
    strategy = PeerContractStrategy(
        ws, logger, agent_ids, lock_timeout_s=timeout)
    return ws, logger, strategy


def _finish(ws, logger):
    logger.close()
    ws.cleanup()


async def test_peer_contract_registered_and_exposes_strategy_tools(tmp_path):
    ws, logger, strategy = _strategy_workspace(
        tmp_path, "t02_benign_overlap", ["agent-a", "agent-b"])
    try:
        assert get_strategy("peer_contract") is PeerContractStrategy
        names = {
            schema["function"]["name"]
            for schema in strategy.extra_tool_schemas()
        }
        assert names == {"declare_intent", "ack_contract"}
    finally:
        _finish(ws, logger)


async def test_peer_contract_allows_declared_disjoint_same_file_edits(tmp_path):
    ws, logger, strategy = _strategy_workspace(
        tmp_path, "t02_benign_overlap", ["agent-slugify", "agent-truncate"])
    try:
        await strategy.read("agent-slugify", "stringutils.py")
        await strategy.read("agent-truncate", "stringutils.py")
        await strategy.handle_strategy_tool("agent-slugify", "declare_intent", {
            "path": "stringutils.py",
            "symbols": ["slugify"],
            "summary": "implement slugify",
        })
        await strategy.handle_strategy_tool("agent-truncate", "declare_intent", {
            "path": "stringutils.py",
            "symbols": ["truncate"],
            "summary": "implement truncate",
        })

        outcome = await strategy.write(
            "agent-slugify",
            "stringutils.py",
            Mutation(kind="replace", old_string=T2_SLUGIFY_OLD,
                     new_string=T2_SLUGIFY_NEW),
        )

        assert outcome.ok
        events = read_events(logger.path)
        blocked = [
            event for event in events
            if event.get("event") == "coord" and event.get("action") == "blocked"
        ]
        assert blocked == []
    finally:
        _finish(ws, logger)


async def test_peer_contract_waits_for_ack_before_overlapping_write(tmp_path):
    ws, logger, strategy = _strategy_workspace(
        tmp_path, "t01_stale_clobber", ["agent-timeout", "agent-retries"],
        timeout=2.0,
    )
    try:
        await strategy.handle_strategy_tool("agent-timeout", "declare_intent", {
            "path": "config.py",
            "symbols": [MODULE_SYMBOL],
            "summary": "add timeout config",
            "exports": ["DEFAULTS.timeout"],
        })
        await strategy.handle_strategy_tool("agent-retries", "declare_intent", {
            "path": "config.py",
            "symbols": [MODULE_SYMBOL],
            "summary": "add retries config",
            "exports": ["DEFAULTS.retries"],
        })

        write_task = asyncio.create_task(strategy.write(
            "agent-timeout",
            "config.py",
            Mutation(kind="replace", old_string='    "port": 8080,\n}',
                     new_string=T1_TIMEOUT_DEFAULT),
        ))
        await asyncio.sleep(0.05)

        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord" and event.get("action") == "blocked"
            for event in events
        )
        response = await strategy.handle_strategy_tool(
            "agent-retries",
            "ack_contract",
            {"contract_id": "contract-1", "decision": "ack",
             "notes": "timeout and retries can share DEFAULTS"},
        )

        outcome = await write_task
        assert "acknowledged contract-1" in response
        assert outcome.ok
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "contract_write_allowed"
            and event.get("contract_id") == "contract-1"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_peer_contract_conflict_refuses_overlapping_write(tmp_path):
    ws, logger, strategy = _strategy_workspace(
        tmp_path, "t01_stale_clobber", ["agent-timeout", "agent-retries"],
        timeout=2.0,
    )
    try:
        await strategy.handle_strategy_tool("agent-timeout", "declare_intent", {
            "path": "config.py",
            "symbols": [MODULE_SYMBOL],
            "summary": "add timeout config",
        })
        await strategy.handle_strategy_tool("agent-retries", "declare_intent", {
            "path": "config.py",
            "symbols": [MODULE_SYMBOL],
            "summary": "change DEFAULTS differently",
        })

        write_task = asyncio.create_task(strategy.write(
            "agent-timeout",
            "config.py",
            Mutation(kind="replace", old_string='    "port": 8080,\n}',
                     new_string=T1_TIMEOUT_DEFAULT),
        ))
        await asyncio.sleep(0.05)
        await strategy.handle_strategy_tool(
            "agent-retries",
            "ack_contract",
            {"contract_id": "contract-1", "decision": "conflict",
             "notes": "both changes rewrite the same module block"},
        )

        outcome = await write_task
        assert not outcome.ok
        assert outcome.status == "conflict"
        assert "agent-retries" in outcome.message
        assert "same module block" in outcome.message
    finally:
        _finish(ws, logger)


async def test_peer_contract_times_out_without_ack(tmp_path):
    ws, logger, strategy = _strategy_workspace(
        tmp_path, "t01_stale_clobber", ["agent-timeout", "agent-retries"],
        timeout=0.05,
    )
    try:
        await strategy.handle_strategy_tool("agent-timeout", "declare_intent", {
            "path": "config.py",
            "symbols": [MODULE_SYMBOL],
            "summary": "add timeout config",
        })
        await strategy.handle_strategy_tool("agent-retries", "declare_intent", {
            "path": "config.py",
            "symbols": [MODULE_SYMBOL],
            "summary": "add retries config",
        })

        outcome = await strategy.write(
            "agent-timeout",
            "config.py",
            Mutation(kind="replace", old_string='    "port": 8080,\n}',
                     new_string=T1_TIMEOUT_DEFAULT),
        )

        assert not outcome.ok
        assert outcome.status == "lock_timeout"
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "contract_timeout"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_agent_dispatches_peer_contract_strategy_tools(tmp_path):
    task = load_task("t02_benign_overlap")
    ws = Workspace.create(task.repo, tmp_path / "ws")
    logger = EventLogger(tmp_path / "events.jsonl")
    strategy = PeerContractStrategy(ws, logger, ["agent-slugify"])
    script = [
        ("declare_intent", {
            "path": "stringutils.py",
            "symbols": ["slugify"],
            "summary": "implement slugify",
        }),
        ("done", {"summary": "declared intent"}),
    ]
    agent = Agent(
        "agent-slugify",
        "Implement slugify.",
        ScriptedModel(script=script),
        strategy,
        ws,
        logger,
        max_turns=3,
    )
    try:
        result = await agent.run()
        assert result.status == "done"
        events = read_events(logger.path)
        assert any(
            event.get("event") == "tool_call"
            and event.get("tool") == "declare_intent"
            for event in events
        )
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "intent_declared"
            for event in events
        )
    finally:
        _finish(ws, logger)
