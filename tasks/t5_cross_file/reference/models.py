"""Domain objects."""


def create_user(name, email):
    """Create a user record with a validated email."""
    if "@" not in email:
        raise ValueError("invalid email")
    return {"name": name, "email": email, "active": True}
