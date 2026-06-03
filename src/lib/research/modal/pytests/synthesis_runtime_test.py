import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from runtime_models import ReviewFinding, ReviewResult, RuntimeTask, WorkerDraft  # noqa: E402
from synthesis_runtime import evidence_bundle_from_review, synthesize_runtime_artifacts  # noqa: E402
from workspace_core import append_event, ensure_workspace, write_json  # noqa: E402


def _task(task_id="task-1"):
    return RuntimeTask(
        task_id=task_id,
        hypothesis_id="H-HAZMAT-HMBP",
        question="Does HMBP apply?",
        family="hazmat",
        skill_id="ca-hmbp",
        allowed_domains=["calepa.ca.gov"],
        input={"facility": {"liquid_gallons": 60}},
    )


def _accepted_review(task_id="task-1", evidence_ids=None):
    return ReviewResult(
        task_id=task_id,
        decision="accepted",
        findings=[],
        accepted_evidence_ids=evidence_ids if evidence_ids is not None else ["ev-grounded"],
        artifact_path=f"reviews/{task_id}/review.json",
    )


def _write_draft(workspace, task, evidence):
    draft = WorkerDraft(
        task_id=task.task_id,
        hypothesis_id=task.hypothesis_id,
        answer="HMBP applies when the liquid threshold is met.",
        evidence=evidence,
        caveats=[],
        artifact_path=f"tasks/{task.task_id}/draft.json",
    )
    write_json(workspace / draft.artifact_path, asdict(draft))
    append_event(workspace, {"type": "draft", "task_id": task.task_id, "artifact_path": draft.artifact_path})
    return draft


def _write_review(workspace, review):
    write_json(workspace / review.artifact_path, asdict(review))
    append_event(
        workspace,
        {
            "type": "review",
            "task_id": review.task_id,
            "decision": review.decision,
            "artifact_path": review.artifact_path,
        },
    )
    return review


def _grounded_evidence(evidence_id="ev-grounded", include_conclusion=True):
    evidence = {
        "id": evidence_id,
        "source_url": "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
        "source_name": "California HMBP Threshold Summary",
        "verbatim_quote": "A business shall establish and implement a business plan if it handles a hazardous material.",
        "field": "liquid_gallons_threshold",
        "value": "55",
        "confidence": 0.91,
        "content_hash": "sha256:grounded",
        "fetched_at": "2026-06-03T00:00:00+00:00",
    }
    if include_conclusion:
        evidence["applies"] = "applies"
    return evidence


def test_accepted_grounded_draft_yields_pass_verdict_and_real_evidence_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        task = _task()
        _write_draft(workspace, task, [_grounded_evidence(), _grounded_evidence("ev-other")])
        review = _write_review(workspace, _accepted_review())

        bundle = evidence_bundle_from_review(task, review, workspace)
        synthesis = synthesize_runtime_artifacts("run-1", [task], workspace)

        assert bundle["researcher_conclusion"] == "applies"
        assert bundle["runtime_review"]["verdict"] == "pass"
        assert bundle["sources"][0]["url"] == "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/"
        assert bundle["sources"][0]["quote"].startswith("A business shall")
        assert len(bundle["sources"]) == 1
        assert synthesis["verification_verdicts"][0]["verdict"] == "pass"
        assert synthesis["determinations"][0]["status"] == "pass"


def test_accepted_missing_grounded_quote_or_source_fails_closed_to_needs_review():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        task = _task()
        _write_draft(workspace, task, [{"id": "ev-grounded", "source_url": "", "source_name": "CalEPA"}])
        review = _write_review(workspace, _accepted_review())

        bundle = evidence_bundle_from_review(task, review, workspace)
        synthesis = synthesize_runtime_artifacts("run-1", [task], workspace)

        assert bundle["researcher_conclusion"] == "needs_review"
        assert bundle["sources"] == []
        assert "missing grounded URL, quote, source name, fetched date, or content hash" in bundle["uncertainties"][0]
        assert bundle["runtime_review"]["verdict"] == "needs_review"
        assert synthesis["verification_verdicts"][0]["verdict"] == "needs_review"
        assert synthesis["determinations"][0]["status"] == "needs_review"


def test_accepted_grounded_evidence_without_conclusion_does_not_invent_conclusion():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        task = _task()
        _write_draft(workspace, task, [_grounded_evidence(include_conclusion=False)])
        review = _write_review(workspace, _accepted_review())

        bundle = evidence_bundle_from_review(task, review, workspace)
        synthesis = synthesize_runtime_artifacts("run-1", [task], workspace)

        assert bundle["researcher_conclusion"] == "needs_review"
        assert synthesis["verification_verdicts"][0]["verdict"] == "needs_review"
        assert synthesis["determinations"][0]["status"] == "needs_review"


def test_human_review_creates_repair_ticket_and_needs_review_verdict():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        task = _task()
        _write_draft(workspace, task, [_grounded_evidence()])
        _write_review(
            workspace,
            ReviewResult(
                task_id=task.task_id,
                decision="needs_human_review",
                findings=[
                    ReviewFinding(
                        severity="major",
                        signal="grounding",
                        explanation="The reviewer could not verify the claim.",
                        repair_instruction="Have a human inspect the source.",
                    )
                ],
                accepted_evidence_ids=[],
                artifact_path=f"reviews/{task.task_id}/review.json",
            ),
        )

        synthesis = synthesize_runtime_artifacts("run-1", [task], workspace)

        assert synthesis["verification_verdicts"][0]["verdict"] == "needs_review"
        assert synthesis["repair_tickets"][0]["task_id"] == task.task_id
        assert synthesis["repair_tickets"][0]["reason"] == "needs_human_review"
        assert synthesis["repair_tickets"][0]["findings"][0]["repair_instruction"] == "Have a human inspect the source."


def test_synthesis_artifact_is_written_and_available():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        task = _task()
        _write_draft(workspace, task, [_grounded_evidence()])
        _write_review(workspace, _accepted_review())

        synthesis = synthesize_runtime_artifacts("run-1", [task], workspace)
        artifact_path = workspace / synthesis["artifact_path"]

        assert synthesis["artifact_path"] == "synthesis/runtime-synthesis.json"
        assert artifact_path.is_file()
        saved = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert saved["run_id"] == "run-1"
        assert saved["artifact_path"] == synthesis["artifact_path"]

        timeline = workspace / "logs" / "timeline.jsonl"
        assert "runtime-synthesis.json" in timeline.read_text(encoding="utf-8")


def test_synthesis_ignores_timeline_artifact_paths_outside_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        task = _task()
        append_event(workspace, {"type": "review", "task_id": task.task_id, "artifact_path": "../outside-review.json"})

        synthesis = synthesize_runtime_artifacts("run-1", [task], workspace)

        assert synthesis["verification_verdicts"][0]["verdict"] == "needs_review"
        assert synthesis["determinations"][0]["review_decision"] == "missing_review"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
