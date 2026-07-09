"""MegaAgent-style git-hash optimistic concurrency.

On read, the strategy snapshots the content the agent saw (equivalent to
recording the commit hash: it pins the read version). On write, under a global
mutex (as in MegaAgent), the agent's intended content is computed against its
READ snapshot and three-way merged with whatever is currently on disk:

    base   = content at the agent's last read
    ours   = current disk content (other agents' landed writes)
    theirs = agent's intended new content

A clean merge lands and is committed; a conflicting merge is refused and the
agent is told to re-read and integrate — the optimistic-concurrency retry cost
this benchmark measures.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from harness.strategies.base import Mutation, Strategy, WriteOutcome, register


def three_way_merge(base: str, ours: str, theirs: str) -> tuple[bool, str]:
    """git merge-file; returns (clean, merged_content)."""
    with tempfile.TemporaryDirectory() as td:
        paths = {}
        for name, content in (("base", base), ("ours", ours), ("theirs", theirs)):
            p = Path(td) / name
            p.write_text(content, encoding="utf-8")
            paths[name] = p
        proc = subprocess.run(
            ["git", "merge-file", "-L", "current", "-L", "base", "-L", "yours",
             str(paths["ours"]), str(paths["base"]), str(paths["theirs"])],
            capture_output=True, text=True,
        )
        merged = paths["ours"].read_text(encoding="utf-8")
        return proc.returncode == 0, merged


@register
class GitHashStrategy(Strategy):
    name = "git_hash"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # (agent, path) -> content snapshot at last read
        self._read_base: dict[tuple[str, str], str] = {}

    async def _coordinate_read(self, agent_id: str, relpath: str) -> str | None:
        if not self.ws.exists(relpath):
            return None
        content = self.ws.read_file(relpath)
        self._read_base[(agent_id, relpath)] = content
        return content

    async def _coordinate_write(self, agent_id: str, relpath: str,
                                mutation: Mutation) -> WriteOutcome:
        async with self._apply_lock:  # MegaAgent's global mutex over git ops
            current = self.ws.read_file(relpath) if self.ws.exists(relpath) else None
            base = self._read_base.get((agent_id, relpath))

            if mutation.kind == "replace":
                anchor_source = base if base is not None else current
                theirs = mutation.apply(anchor_source)
                if theirs is None:
                    return WriteOutcome(
                        status="edit_failed",
                        message="old_string not found in the version you read; "
                                "re-read the file and retry",
                    )
            else:
                theirs = mutation.content

            # new file, or agent never read it and file absent: plain write
            if current is None:
                self.ws.write_file(relpath, theirs)
                head = self.ws.commit_all(f"{agent_id} writes {relpath}")
                self._read_base[(agent_id, relpath)] = theirs
                return WriteOutcome(status="applied", changed=set(), message=head[:12])

            effective_base = base if base is not None else current

            if effective_base == current:
                merged, clean = theirs, True  # no concurrent change since read
            else:
                clean, merged = three_way_merge(effective_base, current, theirs)

            if not clean:
                self.log.log("coord", strategy=self.name, action="merge_conflict",
                             agent=agent_id, path=relpath)
                return WriteOutcome(
                    status="conflict",
                    message=("your change conflicts with a concurrent edit to "
                             f"{relpath}; the file has changed since you read it. "
                             "Re-read it and reapply your change on top.\n"
                             "Current content:\n" + current),
                )

            if effective_base != current:
                self.log.log("coord", strategy=self.name, action="auto_merge",
                             agent=agent_id, path=relpath)
            self.ws.write_file(relpath, merged)
            head = self.ws.commit_all(f"{agent_id} writes {relpath}")
            self._read_base[(agent_id, relpath)] = merged
            from harness.symbols import changed_symbols
            status = "merged" if effective_base != current else "applied"
            return WriteOutcome(status=status, message=head[:12],
                                changed=changed_symbols(current, merged))
