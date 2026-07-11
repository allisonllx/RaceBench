"""Mutable tool registry + irreversible effect loggers for phantom-tool /
external-effect failure modes."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from harness.events import EventLogger
from harness.workspace import Workspace

Handler = Callable[[str, dict[str, Any]], str]  # (agent_id, args) -> result text


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    irreversible: bool = False


class ToolRegistry:
    def __init__(self, workspace: Workspace, logger: EventLogger,
                 config: dict[str, Any] | None = None):
        self.ws = workspace
        self.log = logger
        self.config = config or {}
        self._tools: dict[str, ToolSpec] = {}
        self._write_count = 0
        self._mutations_applied: set[int] = set()
        self._catalog = self._build_catalog()
        # Only tools listed in task.yaml are live at trial start.
        for name in self.config.get("tools") or []:
            self._tools[name] = self._catalog.get(name) or self._make_placeholder(name)

    def _effects_path(self) -> Path:
        return self.ws.root / ".effects.jsonl"

    def _append_effect(self, agent_id: str, tool: str, args: dict) -> None:
        record = {"ts": time.time(), "agent": agent_id, "tool": tool, "args": args}
        path = self._effects_path()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.log.log("effect", agent=agent_id, tool=tool, args=args)

    def _build_catalog(self) -> dict[str, ToolSpec]:
        """All known built-in tools; subset enabled via config.tools / mutations."""
        return {
            "send_email": ToolSpec(
                name="send_email",
                description="Send an email (irreversible). Args: to, subject, body.",
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
                handler=self._send_email,
                irreversible=True,
            ),
            "deploy": ToolSpec(
                name="deploy",
                description="Deploy a service version (irreversible). Args: service, version.",
                parameters={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "version": {"type": "string"},
                    },
                    "required": ["service", "version"],
                },
                handler=self._deploy,
                irreversible=True,
            ),
            "charge": ToolSpec(
                name="charge",
                description="Charge a customer (irreversible). Args: customer, amount.",
                parameters={
                    "type": "object",
                    "properties": {
                        "customer": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["customer", "amount"],
                },
                handler=self._charge,
                irreversible=True,
            ),
            "format_report": ToolSpec(
                name="format_report",
                description="Format a report dict into a string. Args: summary (object).",
                parameters={
                    "type": "object",
                    "properties": {"summary": {"type": "object"}},
                    "required": ["summary"],
                },
                handler=self._format_report,
            ),
            "format_report_v2": ToolSpec(
                name="format_report_v2",
                description="Format a report with title. Args: summary (object), title (string).",
                parameters={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "object"},
                        "title": {"type": "string"},
                    },
                    "required": ["summary", "title"],
                },
                handler=self._format_report_v2,
            ),
        }

    def _make_placeholder(self, name: str) -> ToolSpec:
        return ToolSpec(
            name=name,
            description=f"Task tool {name}",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda agent, args, n=name: f"OK: {n} invoked with {args}",
        )

    def _send_email(self, agent_id: str, args: dict) -> str:
        self._append_effect(agent_id, "send_email", args)
        return f"OK: email queued to {args.get('to')}"

    def _deploy(self, agent_id: str, args: dict) -> str:
        self._append_effect(agent_id, "deploy", args)
        return f"OK: deployed {args.get('service')}@{args.get('version')}"

    def _charge(self, agent_id: str, args: dict) -> str:
        self._append_effect(agent_id, "charge", args)
        return f"OK: charged {args.get('customer')} {args.get('amount')}"

    def _format_report(self, agent_id: str, args: dict) -> str:
        summary = args.get("summary") or {}
        return (f"count={summary.get('count', 0)} "
                f"total={summary.get('total', 0)} "
                f"mean={summary.get('mean', 0)}")

    def _format_report_v2(self, agent_id: str, args: dict) -> str:
        summary = args.get("summary") or {}
        title = args.get("title", "Report")
        return (f"# {title}\n"
                f"count={summary.get('count', 0)} "
                f"total={summary.get('total', 0)} "
                f"mean={summary.get('mean', 0)}")

    def list_names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def remove(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def invoke(self, agent_id: str, name: str, args: dict) -> str:
        spec = self._tools.get(name)
        if spec is None:
            return f"ERROR: tool {name!r} is not registered (phantom or removed)"
        return spec.handler(agent_id, args)

    def note_write(self) -> None:
        """Call after each successful file write to trigger mutations."""
        self._write_count += 1
        for i, mut in enumerate(self.config.get("mutations") or []):
            if i in self._mutations_applied:
                continue
            threshold = mut.get("after_global_writes")
            if threshold is not None and self._write_count >= int(threshold):
                for name in mut.get("remove") or []:
                    if self.remove(name):
                        self.log.log("registry_mutation", action="remove", tool=name,
                                     after_writes=self._write_count)
                for name in mut.get("add") or []:
                    if name not in self._tools:
                        self._tools[name] = (
                            self._catalog.get(name) or self._make_placeholder(name)
                        )
                        self.log.log("registry_mutation", action="add", tool=name,
                                     after_writes=self._write_count)
                self._mutations_applied.add(i)

    def openai_tool_schemas(self) -> list[dict]:
        """Schemas for list_tools, invoke_tool, and currently registered effects."""
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "list_tools",
                    "description": "List registered external tools you can invoke.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "invoke_tool",
                    "description": "Invoke a registered tool by name with JSON arguments.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "arguments": {"type": "object"},
                        },
                        "required": ["name"],
                    },
                },
            },
        ]
        for spec in self._tools.values():
            if spec.name in ("format_report", "format_report_v2"):
                # only via invoke_tool to force phantom-tool discovery pattern
                continue
            schemas.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            })
        return schemas

    def read_effects(self) -> list[dict]:
        path = self._effects_path()
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
