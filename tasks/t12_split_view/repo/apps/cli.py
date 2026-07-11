from lib.api import Greeter


def welcome(name: str) -> str:
    g = Greeter()
    # Will use greet once agent-core lands it
    return g.ping()
