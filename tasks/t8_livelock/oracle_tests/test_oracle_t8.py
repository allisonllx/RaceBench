import alpha
import beta


def test_all_edits_landed():
    assert alpha.GREETING == "hello"
    assert alpha.VERSION == "0.2"
    assert beta.FAREWELL == "goodbye"
    assert beta.COUNT == 2
