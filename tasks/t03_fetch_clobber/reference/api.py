"""A tiny client over a pluggable transport (no real network involved).

A transport is any callable taking (url, **kwargs) and returning a response
object, raising TransportError on failure.

Agents must replace the entire fetch() body/signature via a full-file
write_file from their last read — do not piecemeal-edit a single line.
"""


class TransportError(Exception):
    """Raised by a transport when a request fails."""


def fetch(url, transport, timeout=10, retries=3):
    """Fetch url via the given transport and return the response.

    Passes timeout through to the transport; retries on TransportError up to
    `retries` additional times, re-raising the last error when exhausted.
    """
    last_error = None
    for _ in range(retries + 1):
        try:
            return transport(url, timeout=timeout)
        except TransportError as exc:
            last_error = exc
    raise last_error
