"""Shared article formatting — includes summary."""
from __future__ import annotations

from typing import Any


def format_article(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": article["slug"],
        "title": article["title"],
        "description": article.get("description", ""),
        "body": article["body"],
        "summary": article["summary"],
        "author_id": article["author_id"],
        "tag_list": list(article.get("tag_list") or []),
        "favorites_count": int(article.get("favorites_count") or 0),
    }


def estimate_reading_minutes(body: str, words_per_minute: int = 200) -> int:
    words = len((body or "").split())
    return max(1, (words + words_per_minute - 1) // words_per_minute)
