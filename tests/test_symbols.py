from harness.symbols import FILE_SYMBOL, MODULE_SYMBOL, changed_symbols, file_symbols

SRC = '''import os

X = 1


def foo():
    return 1


class Bar:
    def method(self):
        return 2
'''


def test_file_symbols():
    assert file_symbols(SRC) == {"foo", "Bar", MODULE_SYMBOL}


def test_changed_symbols_single_function():
    new = SRC.replace("return 1", "return 42")
    assert changed_symbols(SRC, new) == {"foo"}


def test_changed_symbols_module_level():
    new = SRC.replace("X = 1", "X = 2")
    assert changed_symbols(SRC, new) == {MODULE_SYMBOL}


def test_changed_symbols_added_function():
    new = SRC + "\n\ndef baz():\n    return 3\n"
    assert changed_symbols(SRC, new) == {"baz"}


def test_no_change():
    assert changed_symbols(SRC, SRC) == set()


def test_non_python_falls_back_to_file():
    assert changed_symbols("{ not python", "{ not python either") == {FILE_SYMBOL}
    assert changed_symbols("{ same", "{ same") == set()
