"""Favorites service."""
from __future__ import annotations

import sqlite3

from conduit.db.store import fetch_one
from conduit.services.articles import get_article_by_slug


def favorite_article(conn: sqlite3.Connection, user_id: int, slug: str) -> dict | None:
    article = get_article_by_slug(conn, slug)
    if article is None:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO favorites (user_id, article_id) VALUES (?, ?)",
        (user_id, article["id"]),
    )
    return get_article_by_slug(conn, slug)


def unfavorite_article(conn: sqlite3.Connection, user_id: int, slug: str) -> dict | None:
    """Remove a favorite. Implemented by agents in the benign-overlap task."""
    raise NotImplementedError("unfavorite_article not implemented")


def is_favorited(conn: sqlite3.Connection, user_id: int, article_id: int) -> bool:
    row = fetch_one(
        conn,
        "SELECT 1 AS ok FROM favorites WHERE user_id = ? AND article_id = ?",
        (user_id, article_id),
    )
    return row is not None
