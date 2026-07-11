"""Services package — re-exports registration API."""
from services.queries import active_users
from services.registration import register

from db import store as _store

_USERS = _store._USERS

__all__ = ["register", "active_users", "_USERS"]
