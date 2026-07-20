"""Validation for tool-call argument payloads.

This intentionally implements only the small JSON Schema subset RaceBench tool
schemas use: type, properties, required, items, and enum. The source of truth is
the same OpenAI-style function schemas exposed to agents where possible.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from harness.strategies.adaptive_lease import DECLARE_SCOPE_SCHEMA
from harness.strategies.peer_contract import ACK_CONTRACT_SCHEMA, DECLARE_INTENT_SCHEMA
from harness.tools import FILE_TOOL_SCHEMAS


def _parameters(schema: dict[str, Any]) -> dict[str, Any]:
    return dict(schema.get("function", {}).get("parameters") or {})


REGISTRY_TOOL_PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    "list_tools": {"type": "object", "properties": {}, "required": []},
    "invoke_tool": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "arguments": {"type": "object"},
        },
        "required": ["name"],
    },
    "send_email": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    "deploy": {
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "version": {"type": "string"},
        },
        "required": ["service", "version"],
    },
    "charge": {
        "type": "object",
        "properties": {
            "customer": {"type": "string"},
            "amount": {"type": "number"},
        },
        "required": ["customer", "amount"],
    },
    "format_report": {
        "type": "object",
        "properties": {"summary": {"type": "object"}},
        "required": ["summary"],
    },
    "format_report_v2": {
        "type": "object",
        "properties": {
            "summary": {"type": "object"},
            "title": {"type": "string"},
        },
        "required": ["summary", "title"],
    },
}


BASE_TOOL_PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    schema["function"]["name"]: _parameters(schema)
    for schema in [
        *FILE_TOOL_SCHEMAS,
        DECLARE_INTENT_SCHEMA,
        ACK_CONTRACT_SCHEMA,
        DECLARE_SCOPE_SCHEMA,
    ]
}


TOOL_PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    **BASE_TOOL_PARAMETER_SCHEMAS,
    **REGISTRY_TOOL_PARAMETER_SCHEMAS,
}


def tool_schema_map(tool_schemas: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a parameter-schema map from OpenAI-style tool definitions."""
    schemas: dict[str, dict[str, Any]] = {}
    for tool_schema in tool_schemas:
        function = tool_schema.get("function") or {}
        name = function.get("name")
        if isinstance(name, str):
            schemas[name] = dict(function.get("parameters") or {})
    return schemas


def validate_tool_arguments(
    tool: str,
    args: Any,
    tool_schemas: Iterable[dict[str, Any]] | None = None,
    *,
    unknown_is_issue: bool = True,
) -> list[str]:
    """Return human-readable schema issues for a tool-call args object."""
    schemas = (
        tool_schema_map(tool_schemas)
        if tool_schemas is not None
        else TOOL_PARAMETER_SCHEMAS
    )
    schema = schemas.get(tool)
    if schema is None:
        if unknown_is_issue:
            return [f"tool {tool!r} has no local parameter schema"]
        return []

    issues = _validate_value(args, schema, "args")
    if tool == "invoke_tool" and isinstance(args, dict):
        target = args.get("name")
        if isinstance(target, str) and target in REGISTRY_TOOL_PARAMETER_SCHEMAS:
            target_args = args.get("arguments") if "arguments" in args else {}
            for issue in _validate_value(
                target_args,
                REGISTRY_TOOL_PARAMETER_SCHEMAS[target],
                "args.arguments",
            ):
                issues.append(f"invoke_tool target {target!r}: {issue}")
    return issues


def _validate_value(value: Any, schema: dict[str, Any], loc: str) -> list[str]:
    issues: list[str] = []
    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        issues.append(
            f"{loc}: expected {_type_label(expected)}, got {_value_type(value)}"
        )
        return issues

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        allowed = ", ".join(repr(item) for item in enum)
        issues.append(f"{loc}: expected one of {allowed}, got {value!r}")

    if expected == "object" and isinstance(value, dict):
        required = schema.get("required") or []
        for field in required:
            if field not in value:
                issues.append(f"{loc}.{field}: missing required field")
        properties = schema.get("properties") or {}
        for field, field_schema in properties.items():
            if field in value:
                issues.extend(_validate_value(value[field], field_schema,
                                              f"{loc}.{field}"))

    if expected == "array" and isinstance(value, list):
        item_schema = schema.get("items") or {}
        for index, item in enumerate(value):
            issues.extend(_validate_value(item, item_schema, f"{loc}[{index}]"))

    return issues


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _type_label(expected: Any) -> str:
    if isinstance(expected, list):
        return " or ".join(str(item) for item in expected)
    return str(expected)


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__
