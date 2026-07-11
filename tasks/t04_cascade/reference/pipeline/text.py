"""Text-to-summary entry points."""
import datasource

from pipeline.aggregate import summarize


def summarize_text(text):
    """Parse raw text using the record-parsing function datasource provides,
    then return summarize() of the result."""
    return summarize(datasource.parse_dataset(text))
