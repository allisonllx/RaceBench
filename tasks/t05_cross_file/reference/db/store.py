"""In-memory user store."""

_USERS = []


def clear():
    _USERS.clear()


def all_users():
    return list(_USERS)


def append_user(user):
    _USERS.append(user)
    return user
