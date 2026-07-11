"""Injectable time source."""
import time


def now():
    return time.monotonic()
