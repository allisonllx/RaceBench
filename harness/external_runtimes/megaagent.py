"""MegaAgent vendor runtime (Level C) — bridges RaceBench → upstream files/.

Requires a local clone of https://github.com/Xtra-Computing/MegaAgent
(`MEGAAGENT_ROOT` or constructor arg). Shared isolation only.
"""
from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from adapters.megaagent.deps import INSTALL_HINT, missing_megaagent_deps
from harness.external import ExternalContext, ExternalOutcome

_BRIDGE = (
    Path(__file__).resolve().parents[2] / "adapters" / "megaagent" / "run_bridge.py"
)


def resolve_megaagent_root(explicit: Path | str | None = None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("MEGAAGENT_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return None


@dataclass
class MegaAgentRuntime:
    name: str = "megaagent"
    megaagent_root: Path | str | None = None

    async def run(self, ctx: ExternalContext) -> ExternalOutcome:
        if ctx.task.isolation == "worktree":
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=(
                    "megaagent adapter supports shared isolation only "
                    "(MegaAgent uses a single files/ tree); "
                    f"task {ctx.task.name!r} has isolation=worktree"
                ),
            )

        root = resolve_megaagent_root(self.megaagent_root)
        if root is None or not root.is_dir():
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=(
                    "MEGAAGENT_ROOT not set or missing. Clone "
                    "https://github.com/Xtra-Computing/MegaAgent and pass "
                    "--megaagent-root / export MEGAAGENT_ROOT. "
                    "See docs/adding-an-external-runtime.md."
                ),
            )
        if not (root / "main.py").is_file():
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=f"MEGAAGENT_ROOT={root} missing main.py",
            )
        if not _BRIDGE.is_file():
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=f"bridge script missing: {_BRIDGE}",
            )

        deps_missing = missing_megaagent_deps()
        if deps_missing:
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message=(
                    "MegaAgent bridge missing Python packages: "
                    + ", ".join(deps_missing)
                    + f". Install with: {INSTALL_HINT}"
                ),
            )

        env = os.environ.copy()
        env["RACEBENCH_INSTRUCTION_DIR"] = str(ctx.instruction_dir.resolve())
        env["RACEBENCH_ROOT"] = str(ctx.workspace.root)
        env["RACEBENCH_TASK"] = ctx.task.name
        env["RACEBENCH_TIMEOUT_S"] = str(int(ctx.timeout_s))
        env["MEGAAGENT_ROOT"] = str(root)

        cmd = [sys.executable, str(_BRIDGE)]
        ctx.log.log(
            "external_megaagent_start",
            megaagent_root=str(root),
            bridge=str(_BRIDGE),
            command=cmd,
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=ctx.timeout_s,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "timeout" for s in ctx.agent_specs},
                message="megaagent bridge timed out",
            )

        out = (stdout or b"").decode("utf-8", errors="replace")[-2000:]
        err = (stderr or b"").decode("utf-8", errors="replace")[-2000:]
        code = proc.returncode if proc.returncode is not None else -1
        ctx.log.log(
            "external_megaagent_end",
            exit_code=code,
            stdout_tail=out,
            stderr_tail=err,
        )
        ok = code == 0
        return ExternalOutcome(
            ok=ok,
            agent_statuses={
                s.id: ("done" if ok else "error") for s in ctx.agent_specs
            },
            message=(
                f"exit {code}"
                + (f": {err.strip()[:500]}" if err.strip() and not ok else "")
            ),
        )
