"""User routes."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from conduit.api.deps import get_db
from conduit.schemas.user import UserCreate, UserOut
from conduit.serializers.user_format import format_user
from conduit.services import auth as auth_svc

router = APIRouter(prefix="/api", tags=["users"])


@router.post("/users", response_model=UserOut)
def register(payload: UserCreate, conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    existing = auth_svc.get_user_by_username(conn, payload.username)
    if existing is not None:
        raise HTTPException(status_code=409, detail="username taken")
    user = auth_svc.create_user(
        conn, payload.username, payload.email, payload.bio, payload.image)
    return format_user(user)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, conn: Annotated[sqlite3.Connection, Depends(get_db)]):
    user = auth_svc.get_user(conn, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="not found")
    return format_user(user)
