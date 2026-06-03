import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orchestrator_runtime import run_task_with_review  # noqa: E402
from runtime_models import ReviewResult, RuntimeTask, WorkerDraft  # noqa: E402


def _task():
    return RuntimeTask(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        question="Does HMBP apply?",
        family="hazmat",
        skill_id="hazmat-skill",
        allowed_domains=["calepa.ca.gov"],
    )


def _draft(suffix="draft"):
    return WorkerDraft(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        answer=f"Answer from {suffix}",
        evidence=[{"id": f"ev-{suffix}", "url": "https://calepa.ca.gov/cupa/"}],
        caveats=[],
        artifact_path=f"tasks/task-1/{suffix}.json",
    )


def _review(decision, artifact="reviews/task-1/review.json"):
    return ReviewResult(
        task_id="task-1",
        decision=decision,
        findings=[],
        accepted_evidence_ids=["ev-draft"] if decision == "accepted" else [],
        artifact_path=artifact,
    )


def test_accepted_first_pass_returns_review():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_task_with_review(
            _task(),
            Path(tmp),
            "rulebook",
            draft_fn=lambda task, rulebook: _draft(),
            review_fn=lambda task, draft, rulebook: _review("accepted"),
            repair_fn=lambda task, draft, review, rulebook: _draft("repair"),
        )

        assert result.decision == "accepted"


def test_repair_once_then_accepted_uses_same_task():
    seen_task_ids = []
    reviews = iter([
        _review("needs_repair", "reviews/task-1/review-1.json"),
        _review("accepted", "reviews/task-1/review-2.json"),
    ])

    def repair_fn(task, draft, review, rulebook):
        seen_task_ids.append(task.task_id)
        return _draft("repair")

    with tempfile.TemporaryDirectory() as tmp:
        result = run_task_with_review(
            _task(),
            Path(tmp),
            "rulebook",
            draft_fn=lambda task, rulebook: _draft(),
            review_fn=lambda task, draft, rulebook: next(reviews),
            repair_fn=repair_fn,
        )

        assert result.decision == "accepted"
        assert seen_task_ids == ["task-1"]


def test_max_repair_attempts_becomes_human_review():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_task_with_review(
            _task(),
            Path(tmp),
            "rulebook",
            draft_fn=lambda task, rulebook: _draft(),
            review_fn=lambda task, draft, rulebook: _review("needs_repair"),
            repair_fn=lambda task, draft, review, rulebook: _draft("repair"),
            max_repairs=1,
        )

        assert result.decision == "needs_human_review"


def test_timeline_artifacts_are_written():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run_task_with_review(
            _task(),
            workspace,
            "rulebook",
            draft_fn=lambda task, rulebook: _draft(),
            review_fn=lambda task, draft, rulebook: _review("accepted"),
            repair_fn=lambda task, draft, review, rulebook: _draft("repair"),
        )

        timeline = workspace / "logs" / "timeline.jsonl"
        lines = [json.loads(line) for line in timeline.read_text(encoding="utf-8").splitlines()]
        assert [line["type"] for line in lines] == ["draft", "review", "accepted"]
        assert (workspace / "tasks" / "task-1" / "draft.json").is_file()
        assert (workspace / "reviews" / "task-1" / "review.json").is_file()


def test_artifact_paths_cannot_escape_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        try:
            run_task_with_review(
                _task(),
                workspace,
                "rulebook",
                draft_fn=lambda task, rulebook: WorkerDraft(
                    task_id="task-1",
                    hypothesis_id="H-HAZMAT-HMBP",
                    answer="Bad path",
                    evidence=[],
                    caveats=[],
                    artifact_path="../outside.json",
                ),
                review_fn=lambda task, draft, rulebook: _review("accepted"),
                repair_fn=lambda task, draft, review, rulebook: _draft("repair"),
            )
        except ValueError as exc:
            assert "escapes workspace" in str(exc)
        else:
            raise AssertionError("Expected path traversal to be rejected")


def test_absolute_artifact_paths_are_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        try:
            run_task_with_review(
                _task(),
                workspace,
                "rulebook",
                draft_fn=lambda task, rulebook: WorkerDraft(
                    task_id="task-1",
                    hypothesis_id="H-HAZMAT-HMBP",
                    answer="Bad path",
                    evidence=[],
                    caveats=[],
                    artifact_path="/tmp/outside.json",
                ),
                review_fn=lambda task, draft, rulebook: _review("accepted"),
                repair_fn=lambda task, draft, review, rulebook: _draft("repair"),
            )
        except ValueError as exc:
            assert "must be relative" in str(exc)
        else:
            raise AssertionError("Expected absolute path to be rejected")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
