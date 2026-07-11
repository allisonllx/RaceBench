from pathlib import Path


def run():
    return "CONSOLE: " + Path("out/report.txt").read_text(encoding="utf-8")
