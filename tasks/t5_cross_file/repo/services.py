"""User services built on models."""
import models

_USERS = []


def register(name, email):
    """Create a user via the user-factory function models provides, append it
    to _USERS, and return it."""
    raise NotImplementedError


def active_users():
    """Return the list of stored users whose "active" value is True."""
    raise NotImplementedError
