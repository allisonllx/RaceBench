"""TTL helpers."""


def expired(expiry_ts, now_fn):
    return expiry_ts is not None and now_fn() > expiry_ts
