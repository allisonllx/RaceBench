"""Query helpers over the user store."""
from db import all_users


def active_users():
    """Return the list of stored users whose "active" value is True."""
    raise NotImplementedError
