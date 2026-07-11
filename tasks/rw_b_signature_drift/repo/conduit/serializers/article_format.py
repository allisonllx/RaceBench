"""Shared article formatting — collision surface for signature-drift tasks."""
from __future__ import annotations

from typing import Any


def format_article(article: dict[str, Any]) -> dict[str, Any]:
    """Return the public article payload used by list/get endpoints.

    Keys: slug, title, description, body, author_id, tag_list, favorites_count.
    """
    return {
        "slug": article["slug"],
        "title": article["title"],
        "description": article.get("description", ""),
        "body": article["body"],
        "author_id": article["author_id"],
        "tag_list": list(article.get("tag_list") or []),
        "favorites_count": int(article.get("favorites_count") or 0),
    }


def estimate_reading_minutes(body: str, words_per_minute: int = 200) -> int:
    """Rough reading-time estimate from body text."""
    words = len((body or "").split())
    return max(1, (words + words_per_minute - 1) // words_per_minute)
