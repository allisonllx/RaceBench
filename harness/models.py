"""Model clients: real OpenAI tool-calling, plus a deterministic scripted model
so the harness, strategies, and metrics pipeline can be exercised end-to-end
(and demoed) without an API key."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""


@dataclass
class ModelTurn:
    tool_calls: list[ToolCall]
    text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ModelClient(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn: ...


class OpenAIModel(ModelClient):
    def __init__(self, model: str, temperature: float | None = None):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI()
        self.model = model
        self.temperature = temperature

    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, tools=tools)
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        resp = await self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        calls = []
        for tc in choice.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(name=tc.function.name, arguments=args, call_id=tc.id))
        usage = resp.usage
        return ModelTurn(
            tool_calls=calls,
            text=choice.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


@dataclass
class ScriptedModel(ModelClient):
    """Replays a fixed sequence of tool calls, one per turn.

    Each script step is (tool_name, arguments). Fake token usage is charged per
    turn so wasted-work metrics remain meaningful in offline mode: retried
    turns cost tokens just like real ones.
    """
    script: list[tuple[str, dict]]
    tokens_per_turn: int = 200
    _i: int = field(default=0, init=False)

    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        if self._i >= len(self.script):
            call = ToolCall(name="done", arguments={"summary": "script exhausted"})
        else:
            name, args = self.script[self._i]
            call = ToolCall(name=name, arguments=dict(args))
            self._i += 1
        call.call_id = f"scripted-{self._i}"
        return ModelTurn(tool_calls=[call],
                         prompt_tokens=self.tokens_per_turn,
                         completion_tokens=self.tokens_per_turn // 4)
