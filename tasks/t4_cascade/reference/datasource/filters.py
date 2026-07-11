"""Line filters for raw datasource text."""


def is_skippable(line: str) -> bool:
    """Return True for blank lines and comment lines starting with '#'."""
    stripped = line.strip()
    return (not stripped) or stripped.startswith("#")
