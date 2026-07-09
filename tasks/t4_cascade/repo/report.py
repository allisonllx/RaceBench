"""Human-readable report formatting."""
import pipeline


def format_report(summary):
    """Return the string 'count=<count> total=<total:.1f> mean=<mean:.2f>'
    for a summary dict as produced by pipeline.summarize."""
    raise NotImplementedError


def report_from_text(text):
    """Summarize raw text via pipeline.summarize_text and format the result
    with format_report."""
    raise NotImplementedError
