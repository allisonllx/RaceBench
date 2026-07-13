"""Append-only JSONL event log — the raw data every metric derives from."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class EventLogger:
    """Thread/task-safe JSONL writer. One file per trial."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = open(self.path, "a", encoding="utf-8")
        self._t0 = time.monotonic()

    def log(self, event: str, **fields: Any) -> None:
        record = {"ts": round(time.monotonic() - self._t0, 4), "event": event, **fields}
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            self._fh.close()


def read_events(path: Path) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def has_trial_end(path: Path) -> bool:
    """True if path exists and contains at least one trial_end event."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event") == "trial_end":
                    return True
    except OSError:
        return False
    return False


def read_trial_end(path: Path) -> dict | None:
    """Return the last trial_end record in the log, or None."""
    path = Path(path)
    if not path.is_file():
        return None
    last: dict | None = None
    try:
        for rec in read_events(path):
            if rec.get("event") == "trial_end":
                last = rec
    except (OSError, json.JSONDecodeError):
        return None
    return last
