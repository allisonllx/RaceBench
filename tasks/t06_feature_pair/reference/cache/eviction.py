"""Eviction helpers."""


def oldest_key(data: dict):
    return next(iter(data), None)
