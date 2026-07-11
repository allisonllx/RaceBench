"""User payload formatting."""
from __future__ import annotations

from typing import Any


def format_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "bio": user.get("bio", ""),
        "image": user.get("image", ""),
    }
