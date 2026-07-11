class Greeter:
    """Public greeting API — both methods present after merge."""

    def greet(self, name: str) -> str:
        return f"hello,{name}"

    def ping(self) -> str:
        return "pong"

    def farewell(self, name: str) -> str:
        return f"bye,{name}"
