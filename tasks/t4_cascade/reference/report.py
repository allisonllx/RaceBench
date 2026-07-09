"""Human-readable report formatting."""
import pipeline


def format_report(summary):
    """Return the string 'count=<count> total=<total:.1f> mean=<mean:.2f>'
    for a summary dict as produced by pipeline.summarize."""
    return (f"count={summary['count']} total={summary['total']:.1f} "
            f"mean={summary['mean']:.2f}")


def report_from_text(text):
    """Summarize raw text via pipeline.summarize_text and format the result
    with format_report."""
    return format_report(pipeline.summarize_text(text))
