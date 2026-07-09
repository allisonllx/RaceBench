"""Hidden oracle: the rename landed everywhere, the chain works end to end."""
import pytest

import cli
import datasource
import pipeline
import report


def test_rename_completed():
    assert hasattr(datasource, "parse_dataset"), "parse_dataset missing"
    assert not hasattr(datasource, "parse_records"), \
        "old name must be removed (no alias)"


def test_parse_dataset_skips_comments_and_blanks():
    text = "# header\na,1\n\n  \nb,2\n# trailing\n"
    assert datasource.parse_dataset(text) == [("a", 1.0), ("b", 2.0)]


def test_summarize():
    s = pipeline.summarize([("a", 1.0), ("b", 2.0)])
    assert s == {"count": 2, "total": 3.0, "mean": 1.5}
    assert pipeline.summarize([]) == {"count": 0, "total": 0.0, "mean": 0.0}


def test_summarize_text_uses_current_parser():
    # comment lines only parse under the NEW parser: a stale call to the old
    # name raises AttributeError, an inlined old parser chokes on '#'
    s = pipeline.summarize_text("# c\na,1\nb,2\n")
    assert s["count"] == 2 and s["total"] == 3.0


def test_format_report():
    assert report.format_report({"count": 2, "total": 3.0, "mean": 1.5}) == \
        "count=2 total=3.0 mean=1.50"


def test_full_chain():
    assert cli.build_report("a,1\nb,2\n") == "REPORT: count=2 total=3.0 mean=1.50"


def test_full_chain_with_comments():
    assert cli.build_report("# x\na,4\n") == "REPORT: count=1 total=4.0 mean=4.00"
