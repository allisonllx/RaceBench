"""Registration service."""
import models
from db import append_user


def register(name, email):
    """Create a user via the user-factory function models provides, append it
    to the store, and return it."""
    user = models.create_user(name, email)
    return append_user(user)
