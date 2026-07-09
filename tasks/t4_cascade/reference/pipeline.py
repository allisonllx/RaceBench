"""Aggregation over parsed records."""
import datasource


def summarize(records):
    """Return {"count": n, "total": sum_of_values, "mean": total / count}.
    mean is 0.0 when records is empty (count 0, total 0.0)."""
    count = len(records)
    total = float(sum(value for _, value in records))
    return {"count": count, "total": total, "mean": total / count if count else 0.0}


def summarize_text(text):
    """Parse raw text using the record-parsing function datasource provides,
    then return summarize() of the result."""
    return summarize(datasource.parse_dataset(text))
