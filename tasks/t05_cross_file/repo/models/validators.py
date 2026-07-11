"""Email validation helpers."""


def looks_like_email(email: str) -> bool:
    return isinstance(email, str) and "@" in email
