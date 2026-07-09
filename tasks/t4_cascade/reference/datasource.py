"""Record parsing for the reporting pipeline."""


def parse_dataset(text):
    """Parse 'name,value' lines into a list of (name, float_value) tuples.
    Blank lines and lines starting with '#' are skipped."""
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, value = line.split(",")
        records.append((name.strip(), float(value)))
    return records
