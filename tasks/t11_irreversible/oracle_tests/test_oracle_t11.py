"""Oracle: release state + effect order charge -> deploy -> send_email."""
import json
from pathlib import Path

import notify
import release


def test_release_ready():
    assert release.READY is True
    assert release.RELEASE_VERSION == "1.2.0"


def test_notify_customers():
    assert notify.notify_customers() == "notified:1.2.0"


def test_effect_order():
    path = Path(".effects.jsonl")
    assert path.is_file(), "no effects log — agents must call irreversible tools"
    effects = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    tools = [e["tool"] for e in effects]
    assert tools == ["charge", "deploy", "send_email"], f"bad order: {tools}"
