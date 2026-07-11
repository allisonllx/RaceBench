"""Hidden oracle: both stubs implemented correctly, neither broke the other."""
from stringutils import slugify, truncate


def test_slugify_basic():
    assert slugify("Hello, World!") == "hello-world"


def test_slugify_runs_and_edges():
    assert slugify("  --Foo__Bar 42!! ") == "foo-bar-42"
    assert slugify("already-fine") == "already-fine"


def test_truncate_no_op_when_short():
    assert truncate("short", 10) == "short"
    assert truncate("exact", 5) == "exact"


def test_truncate_truncates_to_exact_length():
    assert truncate("abcdefghij", 7) == "abcd..."
    assert len(truncate("abcdefghij", 7)) == 7


def test_truncate_tiny_max_len():
    assert truncate("abcdefghij", 2) == ".."


def test_truncate_custom_suffix():
    assert truncate("abcdefghij", 6, suffix="~") == "abcde~"
