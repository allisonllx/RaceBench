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
    """Return how many articles carry ``tag`` (must match list_articles filter).

    Implemented by agents in the tag-antidependency task.
    """
    raise NotImplementedError("tag_article_count not implemented")
