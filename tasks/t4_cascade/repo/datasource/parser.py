"""Record parsing for the reporting pipeline."""
from datasource.filters import is_skippable


def parse_records(text):
    """Parse 'name,value' lines into a list of (name, float_value) tuples."""
    records = []
    for line in text.splitlines():
        if is_skippable(line):
            continue
        name, value = line.strip().split(",")
        records.append((name.strip(), float(value)))
    return records
