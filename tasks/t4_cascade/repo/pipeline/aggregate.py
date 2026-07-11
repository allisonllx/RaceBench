"""Aggregation over parsed records."""


def summarize(records):
    """Return {"count": n, "total": sum_of_values, "mean": total / count}.
    mean is 0.0 when records is empty (count 0, total 0.0)."""
    raise NotImplementedError
