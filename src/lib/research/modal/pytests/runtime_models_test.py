import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from runtime_models import (  # noqa: E402
    ReviewFinding,
    ReviewResult,
    RuntimeTask,
    WorkerDraft,
)


def test_runtime_task_construction_defaults():
    task = RuntimeTask(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        question="Does HMBP apply?",
        family="hazmat",
        skill_id=None,
    )

    assert task.task_id == "task-1"
    assert task.allowed_domains == []
    assert task.input == {}


def test_worker_draft_and_review_result_construction():
    draft = WorkerDraft(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        answer="HMBP may apply based on liquid volume.",
        evidence=[{"id": "ev-1", "url": "https://calepa.ca.gov/cupa/"}],
        caveats=["Confirm onsite gallons."],
        artifact_path="tasks/task-1/draft.json",
    )
    finding = ReviewFinding(
        severity="major",
        signal="grounding",
        explanation="The source is allowed but the threshold quote is missing.",
        repair_instruction="Add a grounded source pointer for the threshold.",
    )
    review = ReviewResult(
        task_id="task-1",
        decision="needs_repair",
        findings=[finding],
        accepted_evidence_ids=["ev-1"],
        artifact_path="reviews/task-1/review.json",
    )

    assert draft.evidence[0]["id"] == "ev-1"
    assert review.findings[0].severity == "major"
    assert review.decision in {"accepted", "needs_repair", "needs_human_review"}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
