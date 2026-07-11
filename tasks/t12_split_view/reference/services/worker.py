from lib.api import Greeter


def goodbye(name: str) -> str:
    return Greeter().farewell(name)
