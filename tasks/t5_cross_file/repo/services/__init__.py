"""Services package — re-exports registration API."""
from services.queries import active_users
from services.registration import register

# Compatibility shim used by older tests / agents that poke _USERS
from db import store as _store

_USERS = _store._USERS

__all__ = ["register", "active_users", "_USERS"]
