from schema.constants import STATUS_ACTIVE


def filter_active(records):
    return [r for r in records if r.get("status") == STATUS_ACTIVE]


def summarize_active(records):
    return {"active_count": len(filter_active(records))}
