"""TTL helpers — stubs for agents to wire into Cache if useful."""


def expired(expiry_ts, now_fn):
    """Return True if expiry_ts is set and now_fn() is past it."""
    raise NotImplementedError
