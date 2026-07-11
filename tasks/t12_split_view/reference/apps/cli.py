from lib.api import Greeter


def welcome(name: str) -> str:
    return Greeter().greet(name)
