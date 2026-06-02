from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


TraceSender = Callable[[str, dict[str, Any]], Any]


class WorkshopTracer:
    def __init__(
        self,
        endpoint: str | None,
        *,
        sender: TraceSender | None = None,
    ):
        self.endpoint = endpoint
        self.sender = sender or _default_sender
        self.events: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []

    def event(self, run_id: str, scope: str, payload: dict[str, Any] | None = None) -> None:
        event = {
            "type": "event",
            "run_id": run_id,
            "scope": scope,
            "payload": payload or {},
            "created_at": _now(),
        }
        self.events.append(event)
        self._send(event)

    def finish(self, run_id: str, payload: dict[str, Any] | None = None) -> None:
        event = {
            "type": "finish",
            "run_id": run_id,
            "scope": "finish",
            "payload": payload or {},
            "created_at": _now(),
        }
        self.events.append(event)
        self._send(event)

    def _send(self, event: dict[str, Any]) -> None:
        if not self.endpoint:
            return
        try:
            self.sender(self.endpoint, event)
        except Exception as exc:  # pragma: no cover - defensive by design
            self.failures.append(
                {
                    "event_scope": event.get("scope"),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )


def workshop(
    endpoint: str | None = None,
    *,
    sender: TraceSender | None = None,
) -> WorkshopTracer:
    return WorkshopTracer(endpoint, sender=sender)


def _default_sender(endpoint: str, event: dict[str, Any]) -> None:
    import json
    from urllib import request

    data = json.dumps(event).encode("utf-8")
    req = request.Request(
        endpoint,
        data=data,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=2):
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
