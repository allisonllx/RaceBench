"""Models package — re-exports the public user factory."""
from models.user import create_user

__all__ = ["create_user"]
