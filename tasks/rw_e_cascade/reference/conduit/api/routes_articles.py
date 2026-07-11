"""Article routes — create passes summary."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from conduit.api.deps import get_db, require_user
from conduit.schemas.article import ArticleCreate
from conduit.serializers.article_format import format_article
from conduit.services import articles as articles_svc
from conduit.services import favorites as favorites_svc

router = APIRouter(prefix="/api", tags=["articles"])


@router.get("/articles")
def list_articles(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    tag: Annotated[str | None, Query()] = None,
):
    rows = articles_svc.list_articles(conn, tag)
    return {"articles": [format_article(r) for r in rows]}


@router.get("/articles/{slug}")
def get_article(slug: str, conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    article = articles_svc.get_article_by_slug(conn, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"article": format_article(article)}


@router.post("/articles")
def create_article(
    payload: ArticleCreate,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[dict, Depends(require_user)],
):
    article = articles_svc.create_article(
        conn, user["id"], payload.title, payload.description, payload.body,
        payload.summary, payload.tag_list,
    )
    return {"article": format_article(article)}


@router.post("/articles/{slug}/favorite")
def favorite_article(
    slug: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[dict, Depends(require_user)],
):
    article = favorites_svc.favorite_article(conn, user["id"], slug)
    if article is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"article": format_article(article)}


@router.delete("/articles/{slug}/favorite")
def unfavorite_article(
    slug: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[dict, Depends(require_user)],
):
    raise HTTPException(status_code=501, detail="not implemented")
