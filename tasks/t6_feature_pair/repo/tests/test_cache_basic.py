"""Visible tests: the pre-existing behavior both features must preserve."""
from cache import Cache


def test_set_get():
    c = Cache()
    c.set("a", 1)
    assert c.get("a") == 1


def test_get_default():
    assert Cache().get("missing", 42) == 42


def test_len_and_contains():
    c = Cache()
    c.set("a", 1)
    c.set("b", 2)
    assert len(c) == 2
    assert "a" in c
