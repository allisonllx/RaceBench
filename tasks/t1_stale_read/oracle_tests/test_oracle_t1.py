"""Hidden oracle: BOTH agents' keys and validation rules must have landed,
and the pre-existing behavior must be intact."""
import pytest

from config import DEFAULTS, get_config, validate


def test_timeout_key_added():
    assert DEFAULTS.get("timeout") == 30.0


def test_retries_key_added():
    assert DEFAULTS.get("retries") == 3


def test_timeout_validation():
    with pytest.raises(ValueError):
        validate({"timeout": 0})
    with pytest.raises(ValueError):
        validate({"timeout": -5})
    validate({"timeout": 1.5})  # must not raise


def test_retries_validation():
    with pytest.raises(ValueError):
        validate({"retries": -1})
    validate({"retries": 0})  # must not raise
    validate({"retries": 5})


def test_existing_behavior_intact():
    assert get_config()["host"] == "localhost"
    assert get_config({"port": 9000})["port"] == 9000
    with pytest.raises(KeyError):
        validate({"nope": 1})
    with pytest.raises(ValueError):
        validate({"port": 70000})


def test_both_overrides_together():
    cfg = get_config({"timeout": 2.0, "retries": 1})
    assert cfg["timeout"] == 2.0
    assert cfg["retries"] == 1
