import pytest

from config import DEFAULTS, get_config, validate


def test_defaults_present():
    assert DEFAULTS["host"] == "localhost"
    assert DEFAULTS["port"] == 8080


def test_override_applies():
    assert get_config({"port": 9000})["port"] == 9000


def test_unknown_key_rejected():
    with pytest.raises(KeyError):
        validate({"nope": 1})


def test_bad_port_rejected():
    with pytest.raises(ValueError):
        validate({"port": -1})
