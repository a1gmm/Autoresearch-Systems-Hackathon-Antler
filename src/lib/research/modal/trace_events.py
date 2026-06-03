from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

VALID_ACTORS = {"parent", "research_worker", "reviewer", "synthesis_agent"}
VALID_STATUSES = {"queued", "running", "done", "failed", "needs_review"}


def _event_id(run_id: str, actor: str, phase: str, status: str, message: str, ref_id: str | None) -> str:
    run_part = f"{run_id}_" if run_id else ""
    if ref_id:
        return f"trace_{run_part}{actor}_{phase}_{ref_id}"
    digest = hashlib.sha256(f"{actor}:{phase}:{status}:{message}".encode("utf-8")).hexdigest()[:12]
    return f"trace_{run_part}{actor}_{phase}_{digest}"


def trace_event(
    actor: str,
    phase: str,
    status: str,
    message: str,
    ref_id: str | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    if actor not in VALID_ACTORS:
        raise ValueError(f"Invalid trace actor: {actor}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid trace status: {status}")

    event = {
        "id": _event_id(run_id, actor, phase, status, message, ref_id),
        "run_id": run_id,
        "actor": actor,
        "phase": phase,
        "status": status,
        "message": message,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if ref_id:
        event["artifact_id"] = ref_id
    return event
