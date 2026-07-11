"""Aggregation over parsed records."""


def summarize(records):
    """Return {"count": n, "total": sum_of_values, "mean": total / count}.
    mean is 0.0 when records is empty (count 0, total 0.0)."""
    count = len(records)
    total = float(sum(value for _, value in records))
    return {"count": count, "total": total, "mean": total / count if count else 0.0}
