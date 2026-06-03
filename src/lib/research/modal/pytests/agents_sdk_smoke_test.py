def test_agents_sdk_imports():
    from agents import Agent, Runner, function_tool

    assert Agent is not None
    assert Runner is not None
    assert function_tool is not None


if __name__ == "__main__":
    test_agents_sdk_imports()
