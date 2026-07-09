"""Command-line entry point."""
import report


def build_report(text):
    """Return report.report_from_text(text) prefixed with 'REPORT: '."""
    return "REPORT: " + report.report_from_text(text)
