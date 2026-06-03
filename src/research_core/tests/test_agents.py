from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from research_core.agents import (
    MaxTurnsExceeded,
    build_researcher_agent,
    build_scope_agent,
    run_researcher_agent,
    run_scope_agent,
)
from research_core.planner import ResearchTask, ResearchTaskBudget
from research_core.tools import SandboxPolicy


def test_agents_have_expected_names():
    assert build_scope_agent().name == "permitpilot-scope-agent"
    assert build_researcher_agent().name == "permitpilot-researcher"


def test_researcher_agent_exposes_sandbox_tools_and_terminal_submit():
    agent = build_researcher_agent()

    assert [tool.name for tool in agent.tools] == [
        "read_skill",
        "web_search",
        "web_fetch",
        "browser_use",
        "read_pdf",
        "read_docx",
        "read_spreadsheet",
        "write_artifact",
        "submit_finding",
    ]
    assert agent.terminal_tool_names == ("submit_finding",)


def test_researcher_tools_bind_policy_as_first_argument(tmp_path: Path, monkeypatch):
    _force_agent_shims(monkeypatch)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path, allow_network=False)
    tools = {tool.name: tool for tool in build_researcher_agent(policy=policy).tools}

    result = tools["web_fetch"]("https://www.aqmd.gov/rules")

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "network_disabled"


def test_submit_finding_tool_accepts_json_metadata(tmp_path: Path, monkeypatch):
    _force_agent_shims(monkeypatch)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)
    tools = {tool.name: tool for tool in build_researcher_agent(policy=policy).tools}

    result = tools["submit_finding"](
        title="Applicability confirmed",
        summary="Official source confirms applicability.",
        sources=["https://www.aqmd.gov/rules"],
        confidence=0.91,
        metadata_json='{"task_id": "task-1", "pages": [1, 2]}',
    )

    assert result["ok"] is True
    assert result["finding"]["metadata"] == {"task_id": "task-1", "pages": [1, 2]}


def test_submit_finding_tool_returns_structured_error_for_invalid_metadata_json(
    tmp_path: Path,
    monkeypatch,
):
    _force_agent_shims(monkeypatch)
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)
    tools = {tool.name: tool for tool in build_researcher_agent(policy=policy).tools}

    result = tools["submit_finding"](
        title="Applicability confirmed",
        summary="Official source confirms applicability.",
        sources=["https://www.aqmd.gov/rules"],
        confidence=0.91,
        metadata_json="{not json",
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_metadata_json"


def test_run_scope_agent_uses_injected_runner_and_returns_structured_data():
    calls = []

    def fake_runner(*, agent, input, max_turns):
        calls.append((agent.name, input, max_turns))
        return {"scope": {"facility": {"city": "Los Angeles"}}}

    result = run_scope_agent(
        {"description": "install spray booth"},
        runner=fake_runner,
        max_turns=2,
    )

    assert result == {"scope": {"facility": {"city": "Los Angeles"}}}
    assert calls == [
        (
            "permitpilot-scope-agent",
            'PermitPilot agent input JSON:\n{"description": "install spray booth"}',
            2,
        )
    ]


def test_run_researcher_agent_uses_injected_runner_with_policy(tmp_path: Path):
    task = ResearchTask(
        task_id="task-1",
        hypothesis_id="hyp-1",
        assigned_agent="researcher",
        allowed_tools=["web_fetch", "submit_finding"],
        blocked_tools=[],
        budget=ResearchTaskBudget(max_sources=3, max_runtime_seconds=30, max_model_calls=2),
    )
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    def fake_runner(*, agent, input, max_turns):
        assert agent.name == "permitpilot-researcher"
        assert agent.terminal_tool_names == ("submit_finding",)
        assert max_turns == 2
        assert isinstance(input, str)
        payload = json.loads(input.removeprefix("PermitPilot agent input JSON:\n"))
        assert payload["task"]["task_id"] == "task-1"
        assert payload["context"] == {"facility": "demo"}
        assert [tool.name for tool in agent.tools][-1] == "submit_finding"
        return {"finding": {"title": "Applicability confirmed"}}

    result = run_researcher_agent(
        task,
        {"facility": "demo"},
        policy,
        runner=fake_runner,
    )

    assert result == {"finding": {"title": "Applicability confirmed"}}


def test_runner_helpers_enforce_positive_max_turns():
    with pytest.raises(MaxTurnsExceeded):
        run_scope_agent({}, runner=lambda **kwargs: {}, max_turns=0)


def test_sdk_agent_constructor_failure_is_not_silently_shimmed(monkeypatch):
    fake_agents = ModuleType("agents")

    class BrokenAgent:
        def __init__(self, **kwargs):
            raise RuntimeError("sdk constructor rejected kwargs")

    fake_agents.Agent = BrokenAgent
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    with pytest.raises(RuntimeError, match="sdk constructor rejected kwargs"):
        build_scope_agent()


def test_sdk_function_tool_failure_is_not_silently_shimmed(monkeypatch):
    fake_agents = ModuleType("agents")

    class FakeAgent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def broken_function_tool(function):
        raise RuntimeError(f"sdk decorator rejected {function.__name__}")

    fake_agents.Agent = FakeAgent
    fake_agents.function_tool = broken_function_tool
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    with pytest.raises(RuntimeError, match="sdk decorator rejected read_skill"):
        build_researcher_agent()


def test_sdk_function_tool_submit_finding_metadata_signature_is_strict_schema_safe(monkeypatch):
    fake_agents = ModuleType("agents")

    class FakeTool:
        def __init__(self, function):
            self.function = function
            self.name = function.__name__

    class FakeAgent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def strict_function_tool(function):
        if function.__name__ == "submit_finding":
            parameters = inspect.signature(function).parameters
            assert "metadata_json" in parameters
            assert "metadata" not in parameters
            annotation = str(parameters["metadata_json"].annotation)
            if "dict" in annotation or "Any" in annotation:
                raise RuntimeError("strict schema rejected arbitrary metadata object")
        return FakeTool(function)

    fake_agents.Agent = FakeAgent
    fake_agents.function_tool = strict_function_tool
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    agent = build_researcher_agent()

    assert [tool.name for tool in agent.tools][-1] == "submit_finding"


def test_default_runner_receives_sdk_safe_input_shape(tmp_path: Path, monkeypatch):
    captured = {}
    fake_agents = ModuleType("agents")

    class FakeTool:
        def __init__(self, function):
            self.function = function
            self.name = function.__name__

    class FakeAgent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeRunner:
        @staticmethod
        def run_sync(agent, input, max_turns):
            if not isinstance(input, (str, list)):
                raise TypeError("Runner input must be SDK-safe")
            captured["agent_name"] = agent.name
            captured["input"] = input
            captured["max_turns"] = max_turns
            return {"ok": True}

    fake_agents.Agent = FakeAgent
    fake_agents.Runner = FakeRunner
    fake_agents.function_tool = FakeTool
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    task = ResearchTask(
        task_id="task-1",
        hypothesis_id="hyp-1",
        assigned_agent="researcher",
        allowed_tools=["web_fetch", "submit_finding"],
        blocked_tools=[],
        budget=ResearchTaskBudget(max_sources=3, max_runtime_seconds=30, max_model_calls=2),
    )
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = run_researcher_agent(task, {"facility": "demo"}, policy)

    assert result == {"ok": True}
    assert captured["agent_name"] == "permitpilot-researcher"
    assert captured["max_turns"] == 2
    payload = json.loads(captured["input"].removeprefix("PermitPilot agent input JSON:\n"))
    assert payload["task"]["task_id"] == "task-1"
    assert payload["context"] == {"facility": "demo"}


def test_default_runner_parses_stringified_terminal_tool_dict(tmp_path: Path, monkeypatch):
    fake_agents = ModuleType("agents")

    class FakeTool:
        def __init__(self, function):
            self.function = function
            self.name = function.__name__

    class FakeAgent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeRunResult:
        final_output = (
            "{'ok': True, 'status': 'submitted', "
            "'finding': {'title': 'Needs review'}}"
        )

    class FakeRunner:
        @staticmethod
        def run_sync(agent, input, max_turns):
            return FakeRunResult()

    fake_agents.Agent = FakeAgent
    fake_agents.Runner = FakeRunner
    fake_agents.function_tool = FakeTool
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    task = ResearchTask(
        task_id="task-1",
        hypothesis_id="hyp-1",
        assigned_agent="researcher",
        allowed_tools=["submit_finding"],
        blocked_tools=[],
        budget=ResearchTaskBudget(max_sources=1, max_runtime_seconds=30, max_model_calls=2),
    )
    policy = SandboxPolicy(run_id="run_1", artifact_root=tmp_path)

    result = run_researcher_agent(task, {"facility": "demo"}, policy)

    assert result == {
        "ok": True,
        "status": "submitted",
        "finding": {"title": "Needs review"},
    }


def _force_agent_shims(monkeypatch):
    monkeypatch.setattr("research_core.agents._sdk_agent_class", lambda: None)
    monkeypatch.setattr("research_core.agents._sdk_function_tool", lambda: None)


def test_researcher_read_skill_loads_mapped_law_skill_on_wrong_guess():
    from research_core.agents import _researcher_tools
    task = {"task_id": "T", "hypothesis_id": "H-AIR-201", "assigned_agent": "air",
            "allowed_tools": [], "blocked_tools": []}
    tools = _researcher_tools(None, task)
    by_name = {getattr(t, "name", None): t for t in tools}
    assert "read_skill" in by_name
    # The agent guesses a non-existent id -> falls back to the hypothesis's canonical skill.
    result = by_name["read_skill"](skill_id="SCAQMD.Rule201.GUESS")
    assert result.get("skill_id") == "scaqmd-permit-to-construct"
    assert len(result.get("content", "")) > 50
