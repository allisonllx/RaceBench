import asyncio

from harness.agent import Agent
from harness.events import EventLogger, read_events
from harness.models import ModelClient, ModelTurn, ToolCall
from harness.scripts import T1_TIMEOUT_DEFAULT, T2_SLUGIFY_NEW, T2_SLUGIFY_OLD
from harness.strategies import get_strategy
from harness.strategies.base import Mutation
from harness.strategies.peer_broker import PeerBrokerStrategy
from harness.symbols import MODULE_SYMBOL
from harness.task import load_task
from harness.workspace import Workspace


class BrokerAckModel(ModelClient):
    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        assert tools[0]["function"]["name"] == "broker_decision"
        assert "ack_with_constraints" in tools[0]["function"]["parameters"]["properties"]["decision"]["enum"]
        assert "Brokered write negotiation request" in messages[-1]["content"]
        assert "Proposed write preview" in messages[-1]["content"]
        return ModelTurn(
            tool_calls=[
                ToolCall(
                    name="broker_decision",
                    arguments={
                        "decision": "ack",
                        "notes": "compatible changes",
                        "contract": "preserve public interfaces",
                    },
                )
            ],
            prompt_tokens=17,
            completion_tokens=5,
        )


class BrokerConstraintsModel(ModelClient):
    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        return ModelTurn(
            tool_calls=[
                ToolCall(
                    name="broker_decision",
                    arguments={
                        "decision": "ack_with_constraints",
                        "notes": "compose timeout and retries",
                        "constraints": [
                            "keep timeout=10",
                            "keep retries=3",
                        ],
                        "contract": "final fetch must support timeout and retries",
                    },
                )
            ],
            prompt_tokens=23,
            completion_tokens=7,
        )


def _broker_workspace(tmp_path, task_name, agent_ids, timeout=1.0):
    task = load_task(task_name)
    ws = Workspace.create(task.repo, tmp_path / "ws")
    logger = EventLogger(tmp_path / "events.jsonl")
    strategy = PeerBrokerStrategy(
        ws, logger, agent_ids, lock_timeout_s=timeout)
    return ws, logger, strategy


def _finish(ws, logger):
    logger.close()
    ws.cleanup()


async def test_peer_broker_registered_without_public_contract_tools(tmp_path):
    ws, logger, strategy = _broker_workspace(
        tmp_path, "t02_benign_overlap", ["agent-a", "agent-b"])
    try:
        assert get_strategy("peer_broker") is PeerBrokerStrategy
        assert strategy.extra_tool_schemas() == []
    finally:
        _finish(ws, logger)


async def test_peer_broker_forces_private_ack_on_overlap(tmp_path):
    ws, logger, strategy = _broker_workspace(
        tmp_path, "t01_stale_clobber", ["agent-timeout", "agent-retries"],
        timeout=1.0,
    )
    try:
        await strategy.read("agent-retries", "config.py")

        async def ack(request):
            assert request["writer"] == "agent-timeout"
            assert request["path"] == "config.py"
            return {"decision": "ack", "notes": "timeout and retries compose"}

        strategy.register_negotiator("agent-retries", ack)
        outcome = await strategy.write(
            "agent-timeout",
            "config.py",
            Mutation(kind="replace", old_string='    "port": 8080,\n}',
                     new_string=T1_TIMEOUT_DEFAULT),
        )

        assert outcome.ok
        events = read_events(logger.path)
        actions = [
            event.get("action") for event in events
            if event.get("event") == "coord"
        ]
        assert "broker_triggered" in actions
        assert "broker_request" in actions
        assert "broker_decision" in actions
        assert "broker_write_allowed" in actions
    finally:
        _finish(ws, logger)


async def test_peer_broker_conflict_refuses_overlapping_write(tmp_path):
    ws, logger, strategy = _broker_workspace(
        tmp_path, "t01_stale_clobber", ["agent-timeout", "agent-retries"],
        timeout=1.0,
    )
    try:
        await strategy.read("agent-retries", "config.py")

        async def conflict(request):
            return {"decision": "conflict", "notes": "same module block"}

        strategy.register_negotiator("agent-retries", conflict)
        outcome = await strategy.write(
            "agent-timeout",
            "config.py",
            Mutation(kind="replace", old_string='    "port": 8080,\n}',
                     new_string=T1_TIMEOUT_DEFAULT),
        )

        assert not outcome.ok
        assert outcome.status == "conflict"
        assert "same module block" in outcome.message
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "broker_conflict"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_peer_broker_constraints_request_revision_not_hard_conflict(tmp_path):
    ws, logger, strategy = _broker_workspace(
        tmp_path, "t01_stale_clobber", ["agent-timeout", "agent-retries"],
        timeout=1.0,
    )
    try:
        await strategy.read("agent-retries", "config.py")

        async def revise(request):
            assert "write_preview" in request
            assert "timeout" in request["write_preview"]
            return {
                "decision": "ack_with_constraints",
                "notes": "compose config additions",
                "constraints": ["preserve retries key"],
                "contract": "DEFAULTS must include timeout and retries",
            }

        strategy.register_negotiator("agent-retries", revise)
        outcome = await strategy.write(
            "agent-timeout",
            "config.py",
            Mutation(kind="replace", old_string='    "port": 8080,\n}',
                     new_string=T1_TIMEOUT_DEFAULT),
        )

        assert not outcome.ok
        assert outcome.status == "conflict"
        assert "revise before writing" in outcome.message
        assert "preserve retries key" in outcome.message
        assert "timeout and retries" in outcome.message
        events = read_events(logger.path)
        assert any(
            event.get("event") == "coord"
            and event.get("action") == "broker_revision_requested"
            for event in events
        )
        assert not any(
            event.get("event") == "coord"
            and event.get("action") == "broker_conflict"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_peer_broker_times_out_without_private_decision(tmp_path):
    ws, logger, strategy = _broker_workspace(
        tmp_path, "t01_stale_clobber", ["agent-timeout", "agent-retries"],
        timeout=0.05,
    )
    try:
        await strategy.read("agent-retries", "config.py")

        async def slow_ack(request):
            await asyncio.sleep(1.0)
            return {"decision": "ack"}

        strategy.register_negotiator("agent-retries", slow_ack)
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
            and event.get("action") == "broker_timeout"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_peer_broker_allows_write_without_active_peer_state(tmp_path):
    ws, logger, strategy = _broker_workspace(
        tmp_path, "t02_benign_overlap", ["agent-slugify", "agent-truncate"],
        timeout=1.0,
    )
    try:
        outcome = await strategy.write(
            "agent-slugify",
            "stringutils.py",
            Mutation(kind="replace", old_string=T2_SLUGIFY_OLD,
                     new_string=T2_SLUGIFY_NEW),
        )

        assert outcome.ok
        events = read_events(logger.path)
        assert not any(
            event.get("event") == "coord"
            and event.get("action") == "broker_triggered"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_agent_private_broker_callback_uses_structured_tool(tmp_path):
    task = load_task("t01_stale_clobber")
    ws = Workspace.create(task.repo, tmp_path / "ws")
    logger = EventLogger(tmp_path / "events.jsonl")
    strategy = PeerBrokerStrategy(ws, logger, ["agent-retries"])
    agent = Agent(
        "agent-retries",
        "Add retry support.",
        BrokerAckModel(),
        strategy,
        ws,
        logger,
        max_turns=1,
    )
    try:
        decision = await strategy.request_negotiation("agent-retries", {
            "contract_id": "contract-9",
            "writer": "agent-timeout",
            "path": "config.py",
            "symbols": [MODULE_SYMBOL],
            "mutation_kind": "replace",
            "summary": "add timeout",
        })

        assert decision["decision"] == "ack"
        assert decision["contract"] == "preserve public interfaces"
        assert agent.prompt_tokens == 17
        assert agent.completion_tokens == 5
        events = read_events(logger.path)
        assert any(
            event.get("event") == "llm_usage"
            and event.get("phase") == "broker"
            for event in events
        )
        assert any(
            event.get("event") == "broker_decision"
            and event.get("decision") == "ack"
            for event in events
        )
    finally:
        _finish(ws, logger)


async def test_agent_private_broker_callback_parses_ack_with_constraints(tmp_path):
    task = load_task("t01_stale_clobber")
    ws = Workspace.create(task.repo, tmp_path / "ws")
    logger = EventLogger(tmp_path / "events.jsonl")
    strategy = PeerBrokerStrategy(ws, logger, ["agent-retries"])
    agent = Agent(
        "agent-retries",
        "Add retry support.",
        BrokerConstraintsModel(),
        strategy,
        ws,
        logger,
        max_turns=1,
    )
    try:
        decision = await strategy.request_negotiation("agent-retries", {
            "contract_id": "contract-10",
            "writer": "agent-timeout",
            "path": "api.py",
            "symbols": ["fetch"],
            "mutation_kind": "replace",
            "summary": "add timeout",
            "write_preview": "def fetch(url, transport, timeout=10): ...",
        })

        assert decision["decision"] == "ack_with_constraints"
        assert decision["constraints"] == ["keep retries=3", "keep timeout=10"]
        assert decision["contract"] == "final fetch must support timeout and retries"
        assert agent.prompt_tokens == 23
        assert agent.completion_tokens == 7
        events = read_events(logger.path)
        assert any(
            event.get("event") == "broker_decision"
            and event.get("decision") == "ack_with_constraints"
            and event.get("constraints") == ["keep retries=3", "keep timeout=10"]
            for event in events
        )
    finally:
        _finish(ws, logger)
