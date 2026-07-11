"""Record parsing for the reporting pipeline."""
from datasource.filters import is_skippable


def parse_dataset(text):
    """Parse 'name,value' lines into a list of (name, float_value) tuples.
    Blank lines and lines starting with '#' are skipped."""
    records = []
    for line in text.splitlines():
        if is_skippable(line):
            continue
        name, value = line.strip().split(",")
        records.append((name.strip(), float(value)))
    return records
