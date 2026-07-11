"""Profile routes."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from conduit.api.deps import get_db
from conduit.services.profiles import get_profile

router = APIRouter(prefix="/api", tags=["profiles"])


@router.get("/profiles/{username}")
def profile(username: str, conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    p = get_profile(conn, username)
    if p is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"profile": p}
