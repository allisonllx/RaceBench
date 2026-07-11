"""Hidden oracle: BOTH features present, integrated, and composing."""
import clock
from cache import Cache


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def advance(self, dt):
        self.t += dt


def _fake_time(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(clock, "now", lambda: fake.t)
    # Cache may import clock_adapter directly
    import cache.clock_adapter as ca
    monkeypatch.setattr(ca, "now", lambda: fake.t)
    return fake


def test_ttl_expiry(monkeypatch):
    fake = _fake_time(monkeypatch)
    c = Cache()
    c.set("k", "v", ttl=10)
    assert c.get("k") == "v"
    fake.advance(11)
    assert c.get("k", "gone") == "gone"


def test_no_ttl_never_expires(monkeypatch):
    fake = _fake_time(monkeypatch)
    c = Cache()
    c.set("k", "v")
    fake.advance(10**6)
    assert c.get("k") == "v"


def test_eviction_oldest_first():
    evicted = []
    c = Cache(max_size=2, on_evict=lambda k, v: evicted.append((k, v)))
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert evicted == [("a", 1)]
    assert c.get("a") is None
    assert c.get("b") == 2 and c.get("c") == 3


def test_update_existing_never_evicts():
    evicted = []
    c = Cache(max_size=2, on_evict=lambda k, v: evicted.append((k, v)))
    c.set("a", 1)
    c.set("b", 2)
    c.set("a", 99)
    assert evicted == []
    assert c.get("a") == 99


def test_ttl_and_eviction_compose(monkeypatch):
    fake = _fake_time(monkeypatch)
    evicted = []
    c = Cache(max_size=2, on_evict=lambda k, v: evicted.append((k, v)))
    c.set("a", 1, ttl=5)
    c.set("b", 2)
    fake.advance(6)
    assert c.get("a", "gone") == "gone"
    c.set("c", 3)
    assert c.get("c") == 3


def test_basic_behavior_intact():
    c = Cache()
    c.set("a", 1)
    assert c.get("a") == 1
    assert c.get("missing", 42) == 42
