def test_research_core_imports():
    import research_core as research_core

    assert research_core.__all__ == ["__version__"]
