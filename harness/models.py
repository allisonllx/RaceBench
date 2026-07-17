"""Model clients: real OpenAI tool-calling, plus a deterministic scripted model
so the harness, strategies, and metrics pipeline can be exercised end-to-end
(and demoed) without an API key."""
from __future__ import annotations

import asyncio
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


class AsyncRequestRateLimiter:
    """Simple shared request spacer for provider RPM limits."""

    def __init__(self, requests_per_minute: float):
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        self._interval_s = 60.0 / requests_per_minute
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def wait(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            delay = self._next_at - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = loop.time()
            self._next_at = now + self._interval_s


class OpenAIModel(ModelClient):
    def __init__(
        self,
        model: str,
        temperature: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        rate_limiter: AsyncRequestRateLimiter | None = None,
        max_retries: int = 4,
        retry_initial_s: float = 10.0,
        retry_max_s: float = 120.0,
    ):
        from openai import AsyncOpenAI
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)
        self.model = model
        self.temperature = temperature
        self.rate_limiter = rate_limiter
        self.max_retries = max_retries
        self.retry_initial_s = retry_initial_s
        self.retry_max_s = retry_max_s

    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, tools=tools)
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        for attempt in range(self.max_retries + 1):
            if self.rate_limiter is not None:
                await self.rate_limiter.wait()
            try:
                resp = await self.client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if attempt >= self.max_retries or not _is_retryable_api_error(exc):
                    raise
                await asyncio.sleep(_retry_delay_s(
                    exc,
                    attempt=attempt,
                    initial_s=self.retry_initial_s,
                    max_s=self.retry_max_s,
                ))
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


def _is_retryable_api_error(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in {"APIConnectionError", "APITimeoutError", "RateLimitError"}:
        return True
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    return status in {408, 409, 429, 500, 502, 503, 504}


def _retry_delay_s(
    exc: Exception,
    *,
    attempt: int,
    initial_s: float,
    max_s: float,
) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) if response is not None else {}
    retry_after = None
    if headers:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), max_s)
        except ValueError:
            pass
    return min(initial_s * (2 ** attempt), max_s)


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
