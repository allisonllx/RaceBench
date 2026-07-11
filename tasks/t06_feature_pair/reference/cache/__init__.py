"""Cache package — re-exports Cache and clock."""
from cache.core import Cache
from cache import clock_adapter as clock

__all__ = ["Cache", "clock"]
