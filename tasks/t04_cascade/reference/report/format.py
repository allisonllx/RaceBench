"""Human-readable report formatting."""


def format_report(summary):
    """Return the string 'count=<count> total=<total:.1f> mean=<mean:.2f>'
    for a summary dict as produced by pipeline.summarize."""
    return (f"count={summary['count']} total={summary['total']:.1f} "
            f"mean={summary['mean']:.2f}")
