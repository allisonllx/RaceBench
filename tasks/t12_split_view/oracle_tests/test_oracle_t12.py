"""Oracle: merged Greeter has both greet and farewell; callers updated."""
from apps.cli import welcome
from lib.api import Greeter
from services.worker import goodbye


def test_greeter_both_methods():
    g = Greeter()
    assert g.greet("ada") == "hello,ada"
    assert g.farewell("ada") == "bye,ada"
    assert g.ping() == "pong"


def test_call_sites():
    assert welcome("ada") == "hello,ada"
    assert goodbye("ada") == "bye,ada"
