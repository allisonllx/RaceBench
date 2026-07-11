"""HTTP error helpers."""
from fastapi import Request
from fastapi.responses import JSONResponse


async def not_implemented_handler(request: Request, exc: NotImplementedError):
    return JSONResponse(status_code=501, content={"detail": str(exc) or "not implemented"})
