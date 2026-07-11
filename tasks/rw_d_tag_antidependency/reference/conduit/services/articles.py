"""Article CRUD and listing."""
from __future__ import annotations

import re
import sqlite3

from conduit.db.store import fetch_all, fetch_one, now_iso


def slugify(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "article"


def _attach_meta(conn: sqlite3.Connection, article: dict) -> dict:
    tags = fetch_all(
        conn, "SELECT tag FROM tags WHERE article_id = ? ORDER BY tag",
        (article["id"],),
    )
    fav = fetch_one(
        conn,
        "SELECT COUNT(*) AS c FROM favorites WHERE article_id = ?",
        (article["id"],),
    )
    article = dict(article)
    article["tag_list"] = [t["tag"] for t in tags]
    article["favorites_count"] = int(fav["c"]) if fav else 0
    return article


def create_article(conn: sqlite3.Connection, author_id: int, title: str,
                   description: str, body: str,
                   tag_list: list[str] | None = None) -> dict:
    slug = slugify(title)
    base = slug
    n = 1
    while fetch_one(conn, "SELECT id FROM articles WHERE slug = ?", (slug,)):
        n += 1
        slug = f"{base}-{n}"
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO articles (slug, title, description, body, author_id, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (slug, title, description, body, author_id, ts, ts),
    )
    article_id = cur.lastrowid
    for tag in tag_list or []:
        conn.execute(
            "INSERT OR IGNORE INTO tags (article_id, tag) VALUES (?, ?)",
            (article_id, tag.lower()),
        )
    return get_article_by_slug(conn, slug)


def get_article_by_slug(conn: sqlite3.Connection, slug: str) -> dict | None:
    row = fetch_one(conn, "SELECT * FROM articles WHERE slug = ?", (slug,))
    if row is None:
        return None
    return _attach_meta(conn, row)


def list_articles(conn: sqlite3.Connection, tag: str | None = None) -> list[dict]:
    if tag:
        rows = fetch_all(
            conn,
            "SELECT a.* FROM articles a "
            "JOIN tags t ON t.article_id = a.id "
            "WHERE LOWER(t.tag) = LOWER(?) ORDER BY a.created_at DESC",
            (tag,),
        )
    else:
        rows = fetch_all(
            conn, "SELECT * FROM articles ORDER BY created_at DESC")
    return [_attach_meta(conn, r) for r in rows]
