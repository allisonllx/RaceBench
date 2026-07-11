from lib.api import Greeter


def goodbye(name: str) -> str:
    g = Greeter()
    # Will use farewell once agent-ext lands it
    return g.ping()
