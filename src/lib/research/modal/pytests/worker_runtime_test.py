import os
import sys
import tempfile
import types
from pathlib import Path

modal_stub = types.ModuleType("modal")


class _Image:
    def __init__(self):
        self.local_python_sources = []

    @staticmethod
    def debian_slim():
        return _Image()

    def pip_install(self, *args):
        return self

    def add_local_dir(self, *args, **kwargs):
        return self

    def add_local_python_source(self, *args):
        self.local_python_sources.extend(args)
        return self


class _Secret:
    @staticmethod
    def from_name(name):
        return name


class _App:
    def __init__(self, name):
        self.name = name

    def function(self, *args, **kwargs):
        def decorator(fn):
            fn.spawn = lambda *a, **k: fn(*a, **k)
            fn.remote = lambda *a, **k: fn(*a, **k)
            return fn
        return decorator

    def local_entrypoint(self):
        def decorator(fn):
            return fn
        return decorator


def _fastapi_endpoint(*args, **kwargs):
    def decorator(fn):
        return fn
    return decorator


modal_stub.App = _App
modal_stub.Image = _Image
modal_stub.Secret = _Secret
modal_stub.fastapi_endpoint = _fastapi_endpoint
sys.modules.setdefault("modal", modal_stub)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from runtime_models import ReviewFinding, ReviewResult, WorkerDraft  # noqa: E402
import worker  # noqa: E402
from worker import run_workspace_research  # noqa: E402


def _task_spec(task_id="task-1"):
    return {
        "task_id": task_id,
        "hypothesis_id": "H-HAZMAT-HMBP",
        "question": "Does HMBP apply?",
        "family": "hazmat",
        "skill_id": "ca-hmbp",
        "allowed_domains": ["calepa.ca.gov"],
    }


def _grounded_evidence():
    return {
        "id": "ev-repair",
        "source_url": "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
        "source_name": "California HMBP Threshold Summary",
        "verbatim_quote": "A business shall establish and implement a business plan if it handles a hazardous material.",
        "fetched_at": "2026-06-03T00:00:00+00:00",
        "content_hash": "sha256:grounded",
        "field": "liquid_gallons_threshold",
        "value": "55",
        "applies": "applies",
        "confidence": 0.9,
    }


def test_workspace_research_updates_status_events_and_artifacts():
    updates = []
    evidence_rows = []
    reviews = iter([
        ReviewResult(
            task_id="task-1",
            decision="needs_repair",
            findings=[
                ReviewFinding(
                    severity="major",
                    signal="grounding",
                    explanation="Quote is missing.",
                    repair_instruction="Add a quote.",
                )
            ],
            accepted_evidence_ids=[],
            artifact_path="reviews/task-1/review-1.json",
        ),
        ReviewResult(
            task_id="task-1",
            decision="accepted",
            findings=[],
            accepted_evidence_ids=["ev-repair"],
            artifact_path="reviews/task-1/review-2.json",
        ),
    ])

    def draft_fn(task, rulebook):
        return WorkerDraft(
            task_id=task.task_id,
            hypothesis_id=task.hypothesis_id,
            answer="draft",
            evidence=[],
            caveats=[],
            artifact_path="tasks/task-1/draft.json",
        )

    def review_fn(task, draft, rulebook):
        return next(reviews)

    def repair_fn(task, draft, review, rulebook):
        return WorkerDraft(
            task_id=task.task_id,
            hypothesis_id=task.hypothesis_id,
            answer="repaired",
            evidence=[_grounded_evidence()],
            caveats=[],
            artifact_path="repairs/task-1/repair-1.json",
        )

    with tempfile.TemporaryDirectory() as tmp:
        result = run_workspace_research(
            "run-1",
            [_task_spec()],
            update_run_fn=lambda payload: updates.append(payload),
            upsert_evidence_fn=lambda bundle: evidence_rows.append(bundle),
            draft_fn=draft_fn,
            review_fn=review_fn,
            repair_fn=repair_fn,
            workspace_root=Path(tmp),
            read_skill_fn=lambda skill_id: f"skill:{skill_id}",
        )

    assert updates[0]["status"] == "running"
    assert updates[-1]["status"] == "bundles_complete"

    trace_events = updates[-1]["trace_events"]
    assert all(event["run_id"] == "run-1" for event in trace_events)
    assert len({event["id"] for event in trace_events}) == len(trace_events)
    assert any(event["actor"] == "reviewer" and event["phase"] == "review.decision.needs_repair" for event in trace_events)
    assert any(event["actor"] == "research_worker" and event["phase"] == "repair.completed" for event in trace_events)
    assert any(event["actor"] == "reviewer" and event["phase"] == "review.accepted" for event in trace_events)

    artifact_paths = {artifact["path"] for artifact in updates[-1]["artifact_index"]}
    assert "tasks/task-1/draft.json" in artifact_paths
    assert "reviews/task-1/review-1.json" in artifact_paths
    assert "reviews/task-1/review-2.json" in artifact_paths
    assert "repairs/task-1/repair-1.json" in artifact_paths
    assert "synthesis/runtime-synthesis.json" in artifact_paths

    assert evidence_rows == [result["bundles"][0]]
    assert evidence_rows[0]["researcher_conclusion"] == "applies"
    assert evidence_rows[0]["sources"][0]["url"] == "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/"
    assert "not wired" not in " ".join(evidence_rows[0].get("uncertainties", []))
    assert result["run_id"] == "run-1"
    assert result["written"] == 1
    assert result["workspace_prefix"] == "run-1"
    assert result["synthesis"]["artifact_path"] == "synthesis/runtime-synthesis.json"


def test_modal_image_includes_worker_core_sibling_modules():
    sources = set(worker.image.local_python_sources)

    assert {"worker_core", "prompts", "tools", "synthesis_runtime"}.issubset(sources)


def test_workspace_research_marks_run_failed_on_runtime_error():
    updates = []

    def draft_fn(task, rulebook):
        raise RuntimeError("draft exploded")

    with tempfile.TemporaryDirectory() as tmp:
        try:
            run_workspace_research(
                "run-fail",
                [_task_spec()],
                update_run_fn=lambda payload: updates.append(payload),
                upsert_evidence_fn=lambda bundle: None,
                draft_fn=draft_fn,
                review_fn=lambda task, draft, rulebook: None,
                repair_fn=lambda task, draft, review, rulebook: None,
                workspace_root=Path(tmp),
                read_skill_fn=lambda skill_id: "",
            )
        except RuntimeError as exc:
            assert "draft exploded" in str(exc)
        else:
            raise AssertionError("Expected runtime error to be re-raised")

    assert updates[0]["status"] == "running"
    assert updates[-1]["status"] == "failed"
    assert any(event["phase"] == "runtime.failed" and event["status"] == "failed" for event in updates[-1]["trace_events"])
    assert all(event["run_id"] == "run-fail" for event in updates[-1]["trace_events"])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
