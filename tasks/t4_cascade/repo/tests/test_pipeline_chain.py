"""Visible tests. The chain test is skipped while stubs are unimplemented."""
import pytest


def test_packages_import():
    import cli  # noqa: F401
    import datasource  # noqa: F401
    import pipeline  # noqa: F401
    import report  # noqa: F401


def test_chain_when_implemented():
    import cli

    try:
        result = cli.build_report("a,1\nb,2\n")
    except NotImplementedError:
        pytest.skip("stubs not implemented yet")
    assert result == "REPORT: count=2 total=3.0 mean=1.50"
