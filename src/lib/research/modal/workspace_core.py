from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    path: str
    task_id: str | None = None
    hypothesis_id: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_workspace(root: Path, run_id: str) -> Path:
    return root / run_id


def ensure_workspace(root: Path, run_id: str) -> Path:
    workspace = run_workspace(root, run_id)
    for child in ("tasks", "reviews", "repairs", "synthesis", "logs"):
        (workspace / child).mkdir(parents=True, exist_ok=True)
    return workspace


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_event(workspace: Path, event: dict[str, Any]) -> None:
    path = workspace / "logs" / "timeline.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": utc_now_iso(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
