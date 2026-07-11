"""Token pricing helpers — shared by the grid runner and report pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

# USD per 1M tokens (list prices; update when re-running reports on old logs).
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "scripted": {"input": 0.0, "output": 0.0},
}


def estimate_usd(prices: dict, model: str, prompt_tokens: int,
                 completion_tokens: int) -> float:
    p = prices.get(model)
    if not p:
        return 0.0
    return (prompt_tokens * p.get("input", 0.0)
            + completion_tokens * p.get("output", 0.0)) / 1e6


def load_prices_from_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(cfg.get("prices") or DEFAULT_PRICES)


def load_prices(run_dir: Path | None = None,
                config_path: Path | None = None) -> dict:
    """Resolve prices: explicit config > run_meta.json in run_dir > defaults."""
    if config_path is not None:
        return load_prices_from_config(config_path)
    if run_dir is not None:
        meta = Path(run_dir) / "run_meta.json"
        if meta.is_file():
            data = json.loads(meta.read_text(encoding="utf-8"))
            if data.get("prices"):
                return dict(data["prices"])
    return dict(DEFAULT_PRICES)


def write_run_meta(run_dir: Path, *, run_id: str, model: str, mode: str,
                   prices: dict, budget: dict | None = None) -> Path:
    meta = {
        "run_id": run_id,
        "model": model,
        "mode": mode,
        "prices": prices,
        "budget": budget or {},
        "price_unit": "usd_per_1m_tokens",
    }
    path = run_dir / "run_meta.json"
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return path
