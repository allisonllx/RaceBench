"""A tiny client over a pluggable transport (no real network involved).

A transport is any callable taking (url, **kwargs) and returning a response
object, raising TransportError on failure.

Agents must replace the entire fetch() body/signature via a full-file
write_file from their last read — do not piecemeal-edit a single line.
"""


class TransportError(Exception):
    """Raised by a transport when a request fails."""


def fetch(url, transport):
    """Fetch url via the given transport and return the response."""
    return transport(url)
