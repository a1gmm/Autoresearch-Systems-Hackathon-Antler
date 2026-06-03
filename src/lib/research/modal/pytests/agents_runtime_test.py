import json
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agents_runtime  # noqa: E402
from runtime_models import ReviewFinding, ReviewResult, RuntimeTask, WorkerDraft  # noqa: E402


@dataclass
class FakeRunResult:
    final_output: object


class FakeRunner:
    calls = []
    outputs = []

    @classmethod
    def run(cls, agent, input):
        cls.calls.append({"agent": agent, "input": input})
        return FakeRunResult(cls.outputs.pop(0))


class FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _install_fake_agents():
    FakeRunner.calls = []
    FakeRunner.outputs = []
    agents_runtime._load_agents_sdk = lambda: (FakeAgent, FakeRunner, lambda fn: fn)


def _task():
    return RuntimeTask(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        question="Does HMBP apply?",
        family="hazmat",
        skill_id="hazmat-skill",
        allowed_domains=["calepa.ca.gov"],
        input={"facility": {"liquid_gallons": 60}},
    )


def _draft():
    return WorkerDraft(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        answer="HMBP applies.",
        evidence=[{"id": "ev-1", "url": "https://calepa.ca.gov/cupa/"}],
        caveats=[],
        artifact_path="tasks/task-1/draft.json",
    )


def test_run_review_parses_needs_repair_with_findings():
    _install_fake_agents()
    FakeRunner.outputs.append(json.dumps({
        "task_id": "task-1",
        "decision": "needs_repair",
        "findings": [{
            "severity": "major",
            "signal": "allowed source",
            "explanation": "The evidence lacks a quoted threshold.",
            "repair_instruction": "Add the quoted threshold from CalEPA.",
        }],
        "accepted_evidence_ids": [],
        "artifact_path": "reviews/task-1/review.json",
    }))

    result = agents_runtime.run_review(_task(), _draft(), "Rulebook signals")

    assert result.decision == "needs_repair"
    assert result.findings == [
        ReviewFinding(
            severity="major",
            signal="allowed source",
            explanation="The evidence lacks a quoted threshold.",
            repair_instruction="Add the quoted threshold from CalEPA.",
        )
    ]


def test_run_review_rejects_invalid_decision():
    _install_fake_agents()
    FakeRunner.outputs.append({
        "task_id": "task-1",
        "decision": "accepted-ish",
        "findings": [],
        "accepted_evidence_ids": [],
        "artifact_path": "reviews/task-1/review.json",
    })

    try:
        agents_runtime.run_review(_task(), _draft(), "Rulebook")
    except ValueError as exc:
        assert "Invalid reviewer decision" in str(exc)
    else:
        raise AssertionError("Expected invalid reviewer decision to be rejected")


def test_run_review_rejects_invalid_finding_shape():
    _install_fake_agents()
    FakeRunner.outputs.append({
        "task_id": "task-1",
        "decision": "needs_repair",
        "findings": [{
            "severity": "urgent",
            "signal": "allowed source",
            "explanation": "Bad severity.",
            "repair_instruction": "Use a valid severity.",
        }],
        "accepted_evidence_ids": [],
        "artifact_path": "reviews/task-1/review.json",
    })

    try:
        agents_runtime.run_review(_task(), _draft(), "Rulebook")
    except ValueError as exc:
        assert "Invalid finding severity" in str(exc)
    else:
        raise AssertionError("Expected invalid finding severity to be rejected")


def test_research_worker_agent_exposes_deterministic_evidence_tools():
    _install_fake_agents()

    agent = agents_runtime.build_research_worker_agent(_task(), "Rulebook")

    tools = agent.kwargs["tools"]
    assert len(tools) == 4
    assert {tool.__name__ for tool in tools} == {
        "is_source_url_allowed",
        "get_official_source_pointer",
        "build_failed_evidence_bundle",
        "assemble_grounded_evidence_bundle",
    }

    allowed = next(tool for tool in tools if tool.__name__ == "is_source_url_allowed")
    pointer = next(tool for tool in tools if tool.__name__ == "get_official_source_pointer")
    assert allowed("https://calepa.ca.gov/cupa/")["allowed"] is True
    assert pointer("H-HAZMAT-HMBP")["found"] is True


def test_run_worker_repair_includes_original_draft_and_reviewer_findings_in_input():
    _install_fake_agents()
    review = ReviewResult(
        task_id="task-1",
        decision="needs_repair",
        findings=[
            ReviewFinding(
                severity="blocker",
                signal="scope",
                explanation="Conclusion is not scoped to facility facts.",
                repair_instruction="Scope the answer to the provided gallon count.",
            )
        ],
        accepted_evidence_ids=[],
        artifact_path="reviews/task-1/review.json",
    )
    FakeRunner.outputs.append({
        "task_id": "task-1",
        "hypothesis_id": "H-HAZMAT-HMBP",
        "answer": "Scoped repaired answer.",
        "evidence": [{"id": "ev-2"}],
        "caveats": ["Confirm SDS."],
        "artifact_path": "repairs/task-1/repair.json",
    })

    result = agents_runtime.run_worker_repair(_task(), _draft(), review, "Rulebook")

    assert result.answer == "Scoped repaired answer."
    repair_input = json.loads(FakeRunner.calls[0]["input"].split("\n\n", 1)[1])
    assert repair_input["mode"] == "repair"
    assert repair_input["task"]["task_id"] == "task-1"
    assert repair_input["original_draft"]["answer"] == "HMBP applies."
    assert repair_input["review_findings"][0]["repair_instruction"] == "Scope the answer to the provided gallon count."
    assert isinstance(FakeRunner.calls[0]["input"], str)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
