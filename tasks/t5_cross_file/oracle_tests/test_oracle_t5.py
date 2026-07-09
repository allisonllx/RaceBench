"""Hidden oracle: new interface landed AND the service is built on it."""
import pytest

import models
import services


def test_interface_changed():
    assert hasattr(models, "create_user"), "create_user missing"
    assert not hasattr(models, "make_user"), "old make_user must be removed"


def test_create_user_validates_email():
    with pytest.raises(ValueError):
        models.create_user("ada", "not-an-email")
    user = models.create_user("ada", "ada@example.com")
    assert user == {"name": "ada", "email": "ada@example.com", "active": True}


def test_register_uses_current_factory():
    services._USERS.clear()
    user = services.register("bob", "bob@example.com")
    assert user["email"] == "bob@example.com"
    assert user["active"] is True


def test_active_users():
    services._USERS.clear()
    a = services.register("a", "a@x.com")
    b = services.register("b", "b@x.com")
    b["active"] = False
    assert services.active_users() == [a]


def test_register_rejects_bad_email_via_factory():
    services._USERS.clear()
    with pytest.raises(ValueError):
        services.register("evil", "no-at-sign")
