"""Aggregation over parsed records."""
import datasource


def summarize(records):
    """Return {"count": n, "total": sum_of_values, "mean": total / count}.
    mean is 0.0 when records is empty (count 0, total 0.0)."""
    raise NotImplementedError


def summarize_text(text):
    """Parse raw text using the record-parsing function datasource provides,
    then return summarize() of the result."""
    raise NotImplementedError
