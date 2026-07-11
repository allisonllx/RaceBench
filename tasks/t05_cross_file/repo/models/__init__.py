"""Models package — re-exports the public user factory."""
from models.user import make_user

__all__ = ["make_user"]
