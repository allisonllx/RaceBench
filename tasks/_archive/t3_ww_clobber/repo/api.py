"""A tiny client over a pluggable transport (no real network involved).

A transport is any callable taking (url, **kwargs) and returning a response
object, raising TransportError on failure.
"""


class TransportError(Exception):
    """Raised by a transport when a request fails."""


def fetch(url, transport):
    """Fetch url via the given transport and return the response."""
    return transport(url)
