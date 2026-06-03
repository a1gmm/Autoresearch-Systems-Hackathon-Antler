import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from trace_events import trace_event  # noqa: E402


def test_trace_event_has_ui_friendly_shape():
    event = trace_event("reviewer", "review.started", "running", "Reviewing task", "task-1", run_id="run-1")

    assert event["id"] == "trace_run-1_reviewer_review.started_task-1"
    assert event["run_id"] == "run-1"
    assert event["actor"] == "reviewer"
    assert event["phase"] == "review.started"
    assert event["status"] == "running"
    assert event["message"] == "Reviewing task"
    assert event["ts"].endswith("+00:00")


def test_trace_event_rejects_invalid_actor():
    try:
        trace_event("orchestrator", "workspace.booting", "running", "Bad actor")
    except ValueError as exc:
        assert "Invalid trace actor" in str(exc)
    else:
        raise AssertionError("Expected invalid actor to be rejected")


def test_trace_event_rejects_invalid_status():
    try:
        trace_event("parent", "workspace.booting", "pending", "Bad status")
    except ValueError as exc:
        assert "Invalid trace status" in str(exc)
    else:
        raise AssertionError("Expected invalid status to be rejected")


def test_trace_event_ref_id_makes_id_stable():
    first = trace_event("research_worker", "draft.completed", "done", "Draft complete", "draft-a", run_id="run-1")
    second = trace_event("research_worker", "draft.completed", "done", "Draft complete", "draft-a", run_id="run-1")

    assert first["id"] == second["id"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
