def summarize(records):
    if not records:
        return {"count": 0, "total": 0, "mean": 0.0}
    total = sum(r["amount"] for r in records)
    count = len(records)
    return {"count": count, "total": total, "mean": total / count}
