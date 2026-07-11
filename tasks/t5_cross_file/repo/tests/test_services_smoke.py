"""Visible tests."""
import pytest


def test_packages_import():
    import models  # noqa: F401
    import services  # noqa: F401
    import db  # noqa: F401


def test_register_when_implemented():
    import db
    import services

    db.clear()
    try:
        user = services.register("ada", "ada@example.com")
    except NotImplementedError:
        pytest.skip("stubs not implemented yet")
    assert user["name"] == "ada"
    assert user in services.active_users()
