import pytest

from harness.pricing import DEFAULT_PRICES, estimate_usd, load_prices_from_config


def test_estimate_usd_gpt5_mini():
    usd = estimate_usd(DEFAULT_PRICES, "gpt-5-mini",
                       prompt_tokens=1_000_000, completion_tokens=500_000)
    assert usd == pytest.approx(0.25 + 1.0)


def test_load_prices_from_config(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("prices:\n  my-model: {input: 1.0, output: 2.0}\n")
    assert load_prices_from_config(cfg)["my-model"]["input"] == 1.0
