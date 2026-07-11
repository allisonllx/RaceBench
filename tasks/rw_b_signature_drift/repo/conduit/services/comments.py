"""Comment service."""
from __future__ import annotations

import sqlite3

from conduit.db.store import fetch_all, fetch_one, now_iso


def add_comment(conn: sqlite3.Connection, article_id: int, author_id: int,
                body: str) -> dict:
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO comments (body, article_id, author_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        (body, article_id, author_id, ts),
    )
    return get_comment(conn, cur.lastrowid)


def get_comment(conn: sqlite3.Connection, comment_id: int) -> dict | None:
    row = fetch_one(
        conn,
        "SELECT c.*, a.slug AS article_slug FROM comments c "
        "JOIN articles a ON a.id = c.article_id WHERE c.id = ?",
        (comment_id,),
    )
    return row


def list_comments_for_article(conn: sqlite3.Connection, article_id: int) -> list[dict]:
    return fetch_all(
        conn,
        "SELECT c.*, a.slug AS article_slug FROM comments c "
        "JOIN articles a ON a.id = c.article_id "
        "WHERE c.article_id = ? ORDER BY c.created_at ASC",
        (article_id,),
    )


def comment_with_article_title(conn: sqlite3.Connection, comment_id: int) -> dict | None:
    """Return comment plus the parent article title (for cascade consumers)."""
    return fetch_one(
        conn,
        "SELECT c.*, a.slug AS article_slug, a.title AS article_title "
        "FROM comments c JOIN articles a ON a.id = c.article_id "
        "WHERE c.id = ?",
        (comment_id,),
    )
