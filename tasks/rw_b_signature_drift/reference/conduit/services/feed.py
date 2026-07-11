"""Feed helpers — reference."""
from __future__ import annotations

import sqlite3

from conduit.serializers.article_format import (
    estimate_reading_minutes,
    format_article,
)
from conduit.services.articles import get_article_by_slug


def reading_time_for_slug(conn: sqlite3.Connection, slug: str) -> dict:
    article = get_article_by_slug(conn, slug)
    if article is None:
        raise ValueError("not found")
    formatted = format_article(article, "en")
    return {
        "slug": formatted["slug"],
        "title": formatted["title"],
        "minutes": estimate_reading_minutes(article["body"]),
    }


def feed_summary(conn: sqlite3.Connection) -> list[dict]:
    raise NotImplementedError("feed_summary not implemented")
