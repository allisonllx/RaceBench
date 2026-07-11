"""Offline scripted external runtime — applies known-good edits via the filesystem.

Validates the Level C path (workspace + instructions + merge + oracle) without
an LLM or the in-process Agent/Strategy loop. Supported tasks:

- t02_benign_overlap (shared isolation)
- t12_split_view (worktree isolation)
"""
from __future__ import annotations

from pathlib import Path

from harness.external import ExternalContext, ExternalOutcome
from harness.scripts import T2_SLUGIFY_NEW, T2_SLUGIFY_OLD, T2_TRUNCATE_NEW, T2_TRUNCATE_OLD


def _replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"anchor not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _apply_t2(ctx: ExternalContext) -> None:
    for spec in ctx.agent_specs:
        root = ctx.workspace.agent_root(spec.id)
        target = root / "stringutils.py"
        if spec.id == "agent-slugify":
            _replace_in(target, T2_SLUGIFY_OLD, T2_SLUGIFY_NEW)
        elif spec.id == "agent-truncate":
            _replace_in(target, T2_TRUNCATE_OLD, T2_TRUNCATE_NEW)
        else:
            raise ValueError(f"no scripted edits for agent {spec.id!r} on t2")


def _apply_t12(ctx: ExternalContext) -> None:
    core_api = (
        "class Greeter:\n"
        '    """Public greeting API — agents extend this class in separate worktrees."""\n'
        "\n"
        "    def greet(self, name: str) -> str:\n"
        '        return f"hello,{name}"\n'
        "\n"
        "    def ping(self) -> str:\n"
        '        return "pong"\n'
    )
    ext_api = (
        "class Greeter:\n"
        '    """Public greeting API — agents extend this class in separate worktrees."""\n'
        "\n"
        "    def ping(self) -> str:\n"
        '        return "pong"\n'
        "\n"
        "    def farewell(self, name: str) -> str:\n"
        '        return f"bye,{name}"\n'
    )
    for spec in ctx.agent_specs:
        root = ctx.workspace.agent_root(spec.id)
        if spec.id == "agent-core":
            (root / "lib" / "api.py").write_text(core_api, encoding="utf-8")
            (root / "apps" / "cli.py").write_text(
                "from lib.api import Greeter\n\n\n"
                "def welcome(name: str) -> str:\n"
                "    return Greeter().greet(name)\n",
                encoding="utf-8",
            )
        elif spec.id == "agent-ext":
            (root / "lib" / "api.py").write_text(ext_api, encoding="utf-8")
            (root / "services" / "worker.py").write_text(
                "from lib.api import Greeter\n\n\n"
                "def goodbye(name: str) -> str:\n"
                "    return Greeter().farewell(name)\n",
                encoding="utf-8",
            )
        else:
            raise ValueError(f"no scripted edits for agent {spec.id!r} on t12")


_HANDLERS = {
    "t02_benign_overlap": _apply_t2,
    "t12_split_view": _apply_t12,
}


class ScriptedExternalRuntime:
    name = "scripted"

    async def run(self, ctx: ExternalContext) -> ExternalOutcome:
        handler = _HANDLERS.get(ctx.task.name)
        if handler is None:
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=(
                    f"scripted external runtime has no edits for "
                    f"{ctx.task.name!r}; known: {sorted(_HANDLERS)}"
                ),
            )
        try:
            handler(ctx)
        except Exception as exc:  # noqa: BLE001 — surface to trial log
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=str(exc),
            )
        ctx.log.log("external_scripted", task=ctx.task.name,
                    agents=[s.id for s in ctx.agent_specs])
        return ExternalOutcome(
            ok=True,
            agent_statuses={s.id: "done" for s in ctx.agent_specs},
            message="scripted edits applied",
        )
