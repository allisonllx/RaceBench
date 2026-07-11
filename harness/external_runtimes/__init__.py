"""Built-in Level C external runtimes."""
from __future__ import annotations

from harness.external import ExternalRuntime
from harness.external_runtimes.megaagent import MegaAgentRuntime
from harness.external_runtimes.scripted import ScriptedExternalRuntime
from harness.external_runtimes.shell import ShellExternalRuntime

_RUNTIMES: dict[str, type] = {
    "scripted": ScriptedExternalRuntime,
    "shell": ShellExternalRuntime,
    "megaagent": MegaAgentRuntime,
}


def get_runtime(name: str, **kwargs) -> ExternalRuntime:
    if name not in _RUNTIMES:
        raise KeyError(
            f"unknown external runtime {name!r}; "
            f"known: {sorted(_RUNTIMES)}"
        )
    return _RUNTIMES[name](**kwargs)


def list_runtimes() -> list[str]:
    return sorted(_RUNTIMES)
