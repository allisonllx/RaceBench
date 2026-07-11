"""String utilities. The two functions below are unimplemented stubs."""
import re  # available for implementations; do not remove


def slugify(text):
    """Return a URL slug: lowercase, every run of characters outside a-z0-9
    replaced by a single hyphen, leading/trailing hyphens stripped.

    slugify("Hello, World!") == "hello-world"
    """
    raise NotImplementedError


def truncate(text, max_len, suffix="..."):
    """Truncate text so the result is at most max_len characters INCLUDING the
    suffix. Return text unchanged when len(text) <= max_len. When truncation
    happens, the result is exactly max_len characters and ends with suffix.
    If max_len < len(suffix), return suffix[:max_len].

    truncate("abcdefghij", 7) == "abcd..."
    """
    raise NotImplementedError
