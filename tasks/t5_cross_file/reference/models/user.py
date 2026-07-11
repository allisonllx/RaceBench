"""User factory functions."""
from models.validators import looks_like_email


def create_user(name, email):
    """Create a user record with a validated email."""
    if not looks_like_email(email):
        raise ValueError("invalid email")
    return {"name": name, "email": email, "active": True}
