"""Feed / reading-time routes — stubs for agent tasks."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from conduit.api.deps import get_db
from conduit.services import feed as feed_svc

router = APIRouter(prefix="/api", tags=["feed"])


@router.get("/articles/{slug}/reading-time")
def reading_time(slug: str, conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    try:
        return feed_svc.reading_time_for_slug(conn, slug)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="not implemented") from None


@router.get("/feed/summary")
def feed_summary(conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    try:
        return {"feed": feed_svc.feed_summary(conn)}
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="not implemented") from None


@router.get("/feed/tags/{tag}/count")
def tag_count(tag: str, conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    try:
        return {"tag": tag, "count": feed_svc.tag_article_count(conn, tag)}
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="not implemented") from None
