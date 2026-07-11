def ok_summary(summary: dict) -> bool:
    return (
        isinstance(summary, dict)
        and "count" in summary
        and "total" in summary
        and "mean" in summary
    )
