def test_imports():
    import exporters  # noqa: F401
    import handlers  # noqa: F401
    import schema  # noqa: F401


def test_active_label_smoke():
    import exporters
    assert isinstance(exporters.active_label(), str)
