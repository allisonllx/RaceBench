class Greeter:
    """Public greeting API — agents extend this class in separate worktrees."""

    def ping(self) -> str:
        return "pong"
