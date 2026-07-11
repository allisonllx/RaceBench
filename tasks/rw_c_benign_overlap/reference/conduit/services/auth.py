"""Auth / user service."""
from __future__ import annotations

import sqlite3

from conduit.db.store import fetch_one


def create_user(conn: sqlite3.Connection, username: str, email: str,
                bio: str = "", image: str = "") -> dict:
    cur = conn.execute(
        "INSERT INTO users (username, email, bio, image) VALUES (?, ?, ?, ?)",
        (username, email, bio, image),
    )
    return get_user(conn, cur.lastrowid)


def get_user(conn: sqlite3.Connection, user_id: int) -> dict | None:
    return fetch_one(conn, "SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_username(conn: sqlite3.Connection, username: str) -> dict | None:
    return fetch_one(conn, "SELECT * FROM users WHERE username = ?", (username,))
