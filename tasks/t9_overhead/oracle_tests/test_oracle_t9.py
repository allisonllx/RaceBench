import mod_a
import mod_b


def test_mod_a():
    assert mod_a.double(3) == 6
    assert mod_a.greet("ada") == "hello ada"


def test_mod_b():
    assert mod_b.square(4) == 16
    assert mod_b.shout("ada") == "ADA!"
