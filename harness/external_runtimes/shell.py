"""Shell external runtime — run an arbitrary command against the instruction pack.

Environment variables passed to the command:

- RACEBENCH_INSTRUCTION_DIR — task.json / paths.json / agents/*.md
- RACEBENCH_ROOT — shared workspace root (oracle runs here after merge)
- RACEBENCH_TASK — task name
- RACEBENCH_TIMEOUT_S — trial timeout hint (seconds)

Exit code 0 → ok; non-zero → failure (oracle still runs on whatever is on disk).
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from harness.external import ExternalContext, ExternalOutcome


@dataclass
class ShellExternalRuntime:
    command: str
    name: str = "shell"

    async def run(self, ctx: ExternalContext) -> ExternalOutcome:
        if not self.command or not self.command.strip():
            return ExternalOutcome(
                ok=False,
                agent_statuses={s.id: "error" for s in ctx.agent_specs},
                message="shell runtime requires a non-empty command",
            )

        env = os.environ.copy()
        env["RACEBENCH_INSTRUCTION_DIR"] = str(ctx.instruction_dir.resolve())
        env["RACEBENCH_ROOT"] = str(ctx.workspace.root)
        env["RACEBENCH_TASK"] = ctx.task.name
        env["RACEBENCH_TIMEOUT_S"] = str(int(ctx.timeout_s))

        ctx.log.log("external_shell_start", command=self.command)
        proc = await asyncio.create_subprocess_shell(
            self.command,
            env=env,
            cwd=str(ctx.workspace.root),
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
                message="shell command timed out",
            )

        out = (stdout or b"").decode("utf-8", errors="replace")[-1500:]
        err = (stderr or b"").decode("utf-8", errors="replace")[-1500:]
        code = proc.returncode if proc.returncode is not None else -1
        ctx.log.log(
            "external_shell_end",
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
            message=f"exit {code}" + (f": {err.strip()}" if err.strip() and not ok else ""),
        )
