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
