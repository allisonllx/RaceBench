"""Visible tests. The integration test skips until implemented, then becomes
the recovery signal for a stale cross-file premise."""
import pytest


def test_modules_import():
    import models  # noqa: F401
    import services  # noqa: F401


def test_register_when_implemented():
    import services

    services._USERS.clear()
    try:
        user = services.register("ada", "ada@example.com")
    except NotImplementedError:
        pytest.skip("stubs not implemented yet")
    assert user["name"] == "ada"
    assert user in services.active_users()
