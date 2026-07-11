"""Profile views (username lookup)."""
from __future__ import annotations

import sqlite3

from conduit.db.store import fetch_one
from conduit.serializers.user_format import format_user


def get_profile(conn: sqlite3.Connection, username: str) -> dict | None:
    row = fetch_one(conn, "SELECT * FROM users WHERE username = ?", (username,))
    if row is None:
        return None
    return format_user(row)
