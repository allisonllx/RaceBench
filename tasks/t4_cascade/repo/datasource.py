"""Record parsing for the reporting pipeline."""


def parse_records(text):
    """Parse 'name,value' lines into a list of (name, float_value) tuples."""
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        name, value = line.split(",")
        records.append((name.strip(), float(value)))
    return records
