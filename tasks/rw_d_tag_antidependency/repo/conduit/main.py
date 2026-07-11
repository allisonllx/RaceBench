"""Application factory."""
from __future__ import annotations

from fastapi import FastAPI

from conduit.api.routes_articles import router as articles_router
from conduit.api.routes_comments import router as comments_router
from conduit.api.routes_feed import router as feed_router
from conduit.api.routes_profiles import router as profiles_router
from conduit.api.routes_users import router as users_router
from conduit.api.deps import reset_schema_flag
from conduit.db.connection import connect, set_db_path
from conduit.db.schema import init_schema


def create_app(db_path: str = "conduit.db") -> FastAPI:
    set_db_path(db_path)
    reset_schema_flag()
    conn = connect()
    init_schema(conn)
    conn.close()

    app = FastAPI(title="Conduit", version="0.1.0")
    app.include_router(users_router)
    app.include_router(profiles_router)
    app.include_router(articles_router)
    app.include_router(comments_router)
    app.include_router(feed_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
