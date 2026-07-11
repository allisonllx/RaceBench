"""Hidden oracle: BOTH features must be integrated into the same fetch()."""
import inspect

import pytest

from api import TransportError, fetch


def test_signature_has_both_params():
    params = inspect.signature(fetch).parameters
    assert "timeout" in params, "timeout parameter missing"
    assert "retries" in params, "retries parameter missing"
    assert params["timeout"].default == 10
    assert params["retries"].default == 3


def test_timeout_passed_through():
    seen = {}

    def transport(url, **kwargs):
        seen.update(kwargs)
        return "ok"

    assert fetch("http://x", transport, timeout=5) == "ok"
    assert seen.get("timeout") == 5


def test_retries_on_transport_error():
    calls = {"n": 0}

    def flaky(url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransportError("boom")
        return "recovered"

    assert fetch("http://x", flaky, retries=3) == "recovered"
    assert calls["n"] == 3


def test_raises_after_retries_exhausted():
    def always_fails(url, **kwargs):
        raise TransportError("down")

    with pytest.raises(TransportError):
        fetch("http://x", always_fails, retries=2)


def test_basic_behavior_intact():
    assert fetch("http://x", lambda url, **kw: f"GOT {url}") == "GOT http://x"
