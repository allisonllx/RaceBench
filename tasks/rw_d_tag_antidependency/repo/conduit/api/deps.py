"""FastAPI dependencies."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from conduit.db.connection import connect
from conduit.db.schema import init_schema
from conduit.services import auth as auth_svc

_schema_ready = False


def get_db() -> sqlite3.Connection:
    global _schema_ready
    conn = connect()
    if not _schema_ready:
        init_schema(conn)
        _schema_ready = True
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_schema_flag() -> None:
    global _schema_ready
    _schema_ready = False


def get_current_user_id(
    x_user_id: Annotated[int | None, Header()] = None,
) -> int:
    """Simple header-based auth for the benchmark (no JWT)."""
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="X-User-Id required")
    return int(x_user_id)


def require_user(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> dict:
    user = auth_svc.get_user(conn, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user
