"""Feed / reading-time helpers — stubs for agent tasks."""
from __future__ import annotations

import sqlite3


def reading_time_for_slug(conn: sqlite3.Connection, slug: str) -> dict:
    """Return {slug, minutes} using format_article + estimate_reading_minutes.

    Implemented by agents in the signature-drift task.
    """
    raise NotImplementedError("reading_time_for_slug not implemented")


def feed_summary(conn: sqlite3.Connection) -> list[dict]:
    """Return a feed of {slug, title, ...} for all articles.

    Implemented by agents in the cascade task; must include every Article field
    the schema requires after the cascade lands.
    """
    raise NotImplementedError("feed_summary not implemented")


def tag_article_count(conn: sqlite3.Connection, tag: str) -> int:
    """Return how many articles carry ``tag`` (must match list_articles filter)."""
    from conduit.db.store import fetch_one
    row = fetch_one(
        conn,
        "SELECT COUNT(DISTINCT a.id) AS c FROM articles a "
        "JOIN tags t ON t.article_id = a.id "
        "WHERE LOWER(t.tag) = LOWER(?)",
        (tag,),
    )
    return int(row["c"]) if row else 0
