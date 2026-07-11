from api import fetch


def test_fetch_returns_transport_result():
    assert fetch("http://x", lambda url, **kw: f"GOT {url}") == "GOT http://x"
