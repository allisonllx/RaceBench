"""Line filters for raw datasource text."""


def is_skippable(line: str) -> bool:
    """Return True for blank lines. Comment handling is added by the parser agent."""
    return not line.strip()
