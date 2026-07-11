from lib.api import Greeter


def test_ping():
    assert Greeter().ping() == "pong"
