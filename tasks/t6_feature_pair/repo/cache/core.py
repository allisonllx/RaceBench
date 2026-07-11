"""Core Cache class. Agents must integrate TTL and eviction here."""
from cache import clock_adapter as clock


class Cache:
    def __init__(self, max_size=128):
        self.max_size = max_size
        self._data = {}

    def set(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return self.get(key) is not None
