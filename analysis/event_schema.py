"""Pydantic schemas for RaceBench JSONL event records.

The validator is intentionally strict for known RaceBench events and permissive
about extra fields. That lets the analysis pipeline catch broken logs without
making older logs or future strategy-specific metadata unusable.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt


class RaceBenchEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: NonNegativeFloat
    event: str


class TrialStartEvent(RaceBenchEvent):
    event: Literal["trial_start"]
    task: str
    failure_mode: str
    benign: bool
    strategy: str
    n_agents: NonNegativeInt
    rep: NonNegativeInt
    model: str
    agent_ids: list[str]
    isolation: str | None = None
    mode: str = "strategy"
    adapter: str | None = None


class TrialEndEvent(RaceBenchEvent):
    event: Literal["trial_end"]
    correct: bool
    oracle_passed: NonNegativeInt
    oracle_total: NonNegativeInt
    wall_clock_s: NonNegativeFloat
    prompt_tokens: NonNegativeInt
    completion_tokens: NonNegativeInt
    agent_statuses: dict[str, str]
    oracle_output: str | None = None


class LlmUsageEvent(RaceBenchEvent):
    event: Literal["llm_usage"]
    agent: str
    turn: int
    prompt_tokens: NonNegativeInt
    completion_tokens: NonNegativeInt
    phase: str | None = None


class ToolCallEvent(RaceBenchEvent):
    event: Literal["tool_call"]
    agent: str
    turn: int
    tool: str
    args: dict[str, Any]


class ToolArgInvalidEvent(RaceBenchEvent):
    event: Literal["tool_arg_invalid"]
    agent: str
    turn: int
    tool: str
    issues: list[str]


class SearchEvent(RaceBenchEvent):
    event: Literal["search"]
    agent: str
    kind: str
    pattern: str
    n: NonNegativeInt


class ReadEvent(RaceBenchEvent):
    event: Literal["read"]
    agent: str
    path: str
    found: bool
    size: NonNegativeInt


class WriteEvent(RaceBenchEvent):
    event: Literal["write"]
    agent: str
    path: str
    kind: str
    status: str
    waited_s: NonNegativeFloat = 0.0
    changed_symbols: list[str] = Field(default_factory=list)
    message: str = ""


class CoordEvent(RaceBenchEvent):
    event: Literal["coord"]
    strategy: str
    action: str


class NotificationDeliveredEvent(RaceBenchEvent):
    event: Literal["notification_delivered"]
    agent: str
    turn: int
    note: str


class RunTestsEvent(RaceBenchEvent):
    event: Literal["run_tests"]
    agent: str
    passed: NonNegativeInt
    failed: NonNegativeInt
    errored: NonNegativeInt


class AgentDoneEvent(RaceBenchEvent):
    event: Literal["agent_done"]
    agent: str
    status: str
    turns: NonNegativeInt
    prompt_tokens: NonNegativeInt
    completion_tokens: NonNegativeInt


class AgentDoneCoordEvent(RaceBenchEvent):
    event: Literal["agent_done_coord"]
    agent: str


class AgentErrorEvent(RaceBenchEvent):
    event: Literal["agent_error"]
    agent: str
    error: str


class TrialTimeoutEvent(RaceBenchEvent):
    event: Literal["trial_timeout"]


class WorktreeMergeEvent(RaceBenchEvent):
    event: Literal["worktree_merge"]
    ok: bool
    conflicts: list[str]
    message: str = ""


class EffectEvent(RaceBenchEvent):
    event: Literal["effect"]
    agent: str
    tool: str
    args: dict[str, Any]


class RegistryMutationEvent(RaceBenchEvent):
    event: Literal["registry_mutation"]
    action: str
    tool: str
    after_writes: NonNegativeInt


class BrokerDecisionEvent(RaceBenchEvent):
    event: Literal["broker_decision"]
    agent: str
    requester: str
    contract_id: str
    path: str
    decision: str
    notes: str = ""
    constraints: list[str] = Field(default_factory=list)
    contract: str = ""


class ExternalEndEvent(RaceBenchEvent):
    event: Literal["external_end"]
    adapter: str
    ok: bool
    message: str = ""
    timed_out: bool = False


class ExternalCursorStartEvent(RaceBenchEvent):
    event: Literal["external_cursor_start"]
    model: str
    n_agents: NonNegativeInt
    isolation: str
    agent_ids: list[str]


class ExternalCursorTimeoutEvent(RaceBenchEvent):
    event: Literal["external_cursor_timeout"]
    timeout_s: NonNegativeFloat


class ExternalCursorEndEvent(RaceBenchEvent):
    event: Literal["external_cursor_end"]
    ok: bool
    agent_statuses: dict[str, str]
    prompt_tokens: NonNegativeInt = 0
    completion_tokens: NonNegativeInt = 0
    message: str = ""


class ExternalShellStartEvent(RaceBenchEvent):
    event: Literal["external_shell_start"]
    command: str


class ExternalShellEndEvent(RaceBenchEvent):
    event: Literal["external_shell_end"]
    exit_code: int
    stdout_tail: str = ""
    stderr_tail: str = ""


class ExternalMegaAgentStartEvent(RaceBenchEvent):
    event: Literal["external_megaagent_start"]
    megaagent_root: str
    bridge: str
    command: list[str]


class ExternalMegaAgentEndEvent(RaceBenchEvent):
    event: Literal["external_megaagent_end"]
    exit_code: int
    stdout_tail: str = ""
    stderr_tail: str = ""


class ExternalScriptedEvent(RaceBenchEvent):
    event: Literal["external_scripted"]
    task: str
    agents: list[str]


EVENT_MODELS: dict[str, type[RaceBenchEvent]] = {
    "agent_done": AgentDoneEvent,
    "agent_done_coord": AgentDoneCoordEvent,
    "agent_error": AgentErrorEvent,
    "broker_decision": BrokerDecisionEvent,
    "coord": CoordEvent,
    "effect": EffectEvent,
    "external_cursor_end": ExternalCursorEndEvent,
    "external_cursor_start": ExternalCursorStartEvent,
    "external_cursor_timeout": ExternalCursorTimeoutEvent,
    "external_end": ExternalEndEvent,
    "external_megaagent_end": ExternalMegaAgentEndEvent,
    "external_megaagent_start": ExternalMegaAgentStartEvent,
    "external_scripted": ExternalScriptedEvent,
    "external_shell_end": ExternalShellEndEvent,
    "external_shell_start": ExternalShellStartEvent,
    "llm_usage": LlmUsageEvent,
    "notification_delivered": NotificationDeliveredEvent,
    "read": ReadEvent,
    "registry_mutation": RegistryMutationEvent,
    "run_tests": RunTestsEvent,
    "search": SearchEvent,
    "tool_call": ToolCallEvent,
    "tool_arg_invalid": ToolArgInvalidEvent,
    "trial_end": TrialEndEvent,
    "trial_start": TrialStartEvent,
    "trial_timeout": TrialTimeoutEvent,
    "worktree_merge": WorktreeMergeEvent,
    "write": WriteEvent,
}


def schema_for_event(event_name: str) -> type[RaceBenchEvent]:
    """Return the schema model for an event name, or the base schema."""
    return EVENT_MODELS.get(event_name, RaceBenchEvent)
