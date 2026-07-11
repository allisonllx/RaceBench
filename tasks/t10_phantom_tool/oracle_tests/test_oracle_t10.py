from pathlib import Path

import console
import pipeline


def test_summary():
    assert pipeline.build_summary() == {"count": 2, "total": 10, "mean": 5.0}


def test_report_is_v2_format():
    text = Path("out/report.txt").read_text(encoding="utf-8")
    assert text.startswith("# Ops Report")
    assert "count=2" in text


def test_console_run():
    out = console.run()
    assert out.startswith("CONSOLE: # Ops Report")
