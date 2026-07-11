"""Core Cache with TTL and bounded-size eviction."""
from cache import clock_adapter as clock
from cache.eviction import oldest_key
from cache.expiry import expired


class Cache:
    def __init__(self, max_size=128, on_evict=None):
        self.max_size = max_size
        self.on_evict = on_evict
        self._data = {}
        self._expiry = {}

    def set(self, key, value, ttl=None):
        is_new = key not in self._data
        if is_new and len(self._data) >= self.max_size:
            old = oldest_key(self._data)
            if old is not None:
                evicted = self._data.pop(old)
                self._expiry.pop(old, None)
                if self.on_evict is not None:
                    self.on_evict(old, evicted)
        self._data[key] = value
        if ttl is None:
            self._expiry.pop(key, None)
        else:
            self._expiry[key] = clock.now() + ttl

    def get(self, key, default=None):
        if key in self._expiry and expired(self._expiry[key], clock.now):
            del self._data[key]
            del self._expiry[key]
            return default
        return self._data.get(key, default)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return self.get(key) is not None
