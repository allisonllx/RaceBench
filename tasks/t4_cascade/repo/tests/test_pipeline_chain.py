"""Visible tests. The chain test is skipped while stubs are unimplemented, but
once implementations land it exercises the WHOLE chain — this is the signal an
agent gets (via run_tests) that an upstream rename invalidated its work."""
import pytest


def test_modules_import():
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
