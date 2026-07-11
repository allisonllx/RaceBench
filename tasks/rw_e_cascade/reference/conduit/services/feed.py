"""Feed helpers — reference with summary."""
from __future__ import annotations

import sqlite3

from conduit.services.articles import list_articles


def reading_time_for_slug(conn: sqlite3.Connection, slug: str) -> dict:
    raise NotImplementedError("reading_time_for_slug not implemented")


def feed_summary(conn: sqlite3.Connection) -> list[dict]:
    return [
        {"slug": a["slug"], "title": a["title"], "summary": a["summary"]}
        for a in list_articles(conn)
    ]
