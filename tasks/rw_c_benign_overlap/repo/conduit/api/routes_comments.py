"""Comment routes."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from conduit.api.deps import get_db, require_user
from conduit.schemas.comment import CommentCreate
from conduit.services import articles as articles_svc
from conduit.services import comments as comments_svc

router = APIRouter(prefix="/api", tags=["comments"])


@router.get("/articles/{slug}/comments")
def list_comments(slug: str, conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    article = articles_svc.get_article_by_slug(conn, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="not found")
    rows = comments_svc.list_comments_for_article(conn, article["id"])
    return {
        "comments": [
            {
                "id": r["id"],
                "body": r["body"],
                "author_id": r["author_id"],
                "article_slug": r["article_slug"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


@router.post("/articles/{slug}/comments")
def create_comment(
    slug: str,
    payload: CommentCreate,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[dict, Depends(require_user)],
):
    article = articles_svc.get_article_by_slug(conn, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="not found")
    row = comments_svc.add_comment(conn, article["id"], user["id"], payload.body)
    return {
        "comment": {
            "id": row["id"],
            "body": row["body"],
            "author_id": row["author_id"],
            "article_slug": row["article_slug"],
            "created_at": row["created_at"],
        }
    }
