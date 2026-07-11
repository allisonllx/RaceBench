"""Build a report from raw text via the pipeline."""
import pipeline

from report.format import format_report


def report_from_text(text):
    """Summarize raw text via pipeline.summarize_text and format the result
    with format_report."""
    raise NotImplementedError
