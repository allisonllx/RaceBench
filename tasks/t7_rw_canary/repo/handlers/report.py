"""Report handlers — stubs."""


def filter_active(records):
    """Return records whose status equals schema.constants.STATUS_ACTIVE
    (the live constant value, not a hard-coded string)."""
    raise NotImplementedError


def summarize_active(records):
    """Return {"active_count": N} where N is len(filter_active(records))."""
    raise NotImplementedError
