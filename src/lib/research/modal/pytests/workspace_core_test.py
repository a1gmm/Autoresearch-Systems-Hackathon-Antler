import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workspace_core import append_event, ensure_workspace, read_json, write_json  # noqa: E402


def test_ensure_workspace_creates_expected_directories():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-123")

        assert workspace == Path(tmp) / "run-123"
        for child in ("tasks", "reviews", "repairs", "synthesis", "logs"):
            assert (workspace / child).is_dir()


def test_write_json_and_read_json_round_trip_nested_payload():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nested" / "payload.json"
        payload = {
            "run_id": "run-123",
            "task": {"id": "task-1", "claims": [{"field": "threshold", "value": 55}]},
            "ok": True,
        }

        write_json(path, payload)

        assert read_json(path) == payload


def test_append_event_writes_jsonl_timeline_entries():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = ensure_workspace(Path(tmp), "run-123")

        append_event(workspace, {"type": "task_started", "task_id": "task-1"})
        append_event(workspace, {"type": "task_finished", "task_id": "task-1", "status": "ok"})

        lines = (workspace / "logs" / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["type"] == "task_started"
        assert first["task_id"] == "task-1"
        assert "ts" in first
        assert second["type"] == "task_finished"
        assert second["status"] == "ok"
        assert "ts" in second


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} passed")
