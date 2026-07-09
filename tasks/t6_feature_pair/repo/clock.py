"""Injectable time source so cache behavior is testable deterministically."""
import time


def now():
    """Current time in seconds (monotonic)."""
    return time.monotonic()
