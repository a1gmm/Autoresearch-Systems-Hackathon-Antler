import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orchestrator_runtime import run_task_with_review  # noqa: E402
from runtime_models import ReviewFinding, ReviewResult, RuntimeTask, WorkerDraft  # noqa: E402
from synthesis_runtime import evidence_bundle_from_review  # noqa: E402
from workspace_core import ensure_workspace  # noqa: E402


def _task():
    return RuntimeTask(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        question="Does HMBP apply?",
        family="hazmat",
        skill_id="ca-hmbp",
        allowed_domains=["calepa.ca.gov"],
        input={"facility": {"liquid_gallons": 60}},
    )


def _draft(kind, artifact_path):
    evidence_by_kind = {
        "omitted_url": [{
            "id": "ev-1",
            "source_name": "California HMBP Threshold Summary",
            "verbatim_quote": "A business shall establish and implement a business plan.",
        }],
        "overclaim": [{
            "id": "ev-1",
            "source_url": "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
            "source_name": "California HMBP Threshold Summary",
            "verbatim_quote": "A business shall establish and implement a business plan.",
            "claim": "All small businesses are exempt from HMBP.",
        }],
        "guessed_fact": [{
            "id": "ev-1",
            "source_url": "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
            "source_name": "California HMBP Threshold Summary",
            "verbatim_quote": "A business shall establish and implement a business plan.",
            "guessed_facility_fact": "Facility stores exactly 100 gallons of liquid.",
        }],
        "grounded": [{
            "id": "ev-1",
            "source_url": "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
            "source_name": "California HMBP Threshold Summary",
            "verbatim_quote": "A business shall establish and implement a business plan if it handles a hazardous material.",
            "fetched_at": "2026-06-03T00:00:00+00:00",
            "content_hash": "sha256:grounded",
            "field": "liquid_gallons_threshold",
            "value": "55",
            "applies": "applies",
            "confidence": 0.9,
        }],
    }
    return WorkerDraft(
        task_id="task-1",
        hypothesis_id="H-HAZMAT-HMBP",
        answer=f"Adversarial {kind}",
        evidence=evidence_by_kind[kind],
        caveats=[],
        artifact_path=artifact_path,
    )


def _reviewer(task, draft, rulebook):
    evidence = draft.evidence[0] if draft.evidence else {}
    if not evidence.get("source_url"):
        return _needs_repair("allowed source URL", "Add the allowed source URL.")
    if "exempt" in (evidence.get("claim") or "").lower():
        return _needs_repair("overclaim", "Remove the unsupported exemption claim.")
    if evidence.get("guessed_facility_fact"):
        return _needs_repair("facility fact", "Do not guess missing facility facts.")
    if not evidence.get("verbatim_quote") or not evidence.get("source_name"):
        return _needs_repair("grounding", "Add a quote and source name.")
    return ReviewResult(
        task_id=task.task_id,
        decision="accepted",
        findings=[],
        accepted_evidence_ids=[evidence["id"]],
        artifact_path=f"reviews/{task.task_id}/{Path(draft.artifact_path).stem}-review.json",
    )


def _needs_repair(signal, instruction):
    return ReviewResult(
        task_id="task-1",
        decision="needs_repair",
        findings=[
            ReviewFinding(
                severity="major",
                signal=signal,
                explanation=f"Detected adversarial defect: {signal}.",
                repair_instruction=instruction,
            )
        ],
        accepted_evidence_ids=[],
        artifact_path=f"reviews/task-1/{signal.replace(' ', '-')}.json",
    )


def _identity_bad_repair(task, draft, review, rulebook):
    return _draft("omitted_url", "repairs/task-1/bad-repair.json")


def test_worker_omits_allowed_source_url_forces_needs_repair():
    review = _reviewer(_task(), _draft("omitted_url", "tasks/task-1/draft.json"), "rulebook")
    assert review.decision == "needs_repair"
    assert review.findings[0].signal == "allowed source URL"


def test_worker_overclaims_exemption_forces_needs_repair():
    review = _reviewer(_task(), _draft("overclaim", "tasks/task-1/draft.json"), "rulebook")
    assert review.decision == "needs_repair"
    assert review.findings[0].signal == "overclaim"


def test_worker_guesses_missing_facility_fact_forces_needs_repair():
    review = _reviewer(_task(), _draft("guessed_fact", "tasks/task-1/draft.json"), "rulebook")
    assert review.decision == "needs_repair"
    assert review.findings[0].signal == "facility fact"


def test_worker_repairs_with_grounded_quote_and_source_gets_accepted_bundle():
    def repair_fn(task, draft, review, rulebook):
        return _draft("grounded", "repairs/task-1/repair.json")

    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        review = run_task_with_review(
            _task(),
            workspace,
            "rulebook",
            draft_fn=lambda task, rulebook: _draft("omitted_url", "tasks/task-1/draft.json"),
            review_fn=_reviewer,
            repair_fn=repair_fn,
            max_repairs=1,
        )

        bundle = evidence_bundle_from_review(_task(), review, workspace)

        assert review.decision == "accepted"
        assert bundle["researcher_conclusion"] == "applies"
        assert bundle["sources"][0]["quote"].startswith("A business shall")


def test_repeated_bad_repair_returns_needs_human_review_and_failed_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-1")
        review = run_task_with_review(
            _task(),
            workspace,
            "rulebook",
            draft_fn=lambda task, rulebook: _draft("omitted_url", "tasks/task-1/draft.json"),
            review_fn=_reviewer,
            repair_fn=_identity_bad_repair,
            max_repairs=1,
        )

        bundle = evidence_bundle_from_review(_task(), review, workspace)

        assert review.decision == "needs_human_review"
        assert bundle["researcher_conclusion"] == "needs_review"
        assert bundle["sources"] == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    caught = 0
    for fn in tests:
        fn()
        caught += 1
    print(f"{caught}/{len(tests)} reviewer loop defects caught")
