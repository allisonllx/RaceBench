"""User factory functions."""


def make_user(name):
    """Create a user record."""
    return {"name": name, "active": True}
