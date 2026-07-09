def test_module_imports():
    import stringutils

    assert callable(stringutils.slugify)
    assert callable(stringutils.truncate)
