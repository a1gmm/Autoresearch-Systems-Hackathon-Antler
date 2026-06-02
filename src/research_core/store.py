from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel


STORE_ROOT_ENV = "RESEARCH_CORE_STORE_ROOT"
RUN_ID_RE = re.compile(r"^run_[A-Za-z0-9_-]+$")


class LocalRunStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).expanduser().resolve() if root is not None else None
        self._runs: dict[str, dict[str, Any]] = {}
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    def create_run(
        self,
        input_payload: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or self._new_run_id()
        self._validate_run_id(run_id)
        if self._load(run_id) is not None:
            raise ValueError(f"run_id {run_id!r} already exists")
        now = _now()
        record = {
            "run_id": run_id,
            "status": "queued",
            "attempt": 1,
            "input": _jsonable(input_payload),
            "artifacts": {},
            "evidence": [],
            "verdicts": [],
            "result": None,
            "events": [],
            "created_at": now,
            "updated_at": now,
        }
        self._save(record)
        return deepcopy(record)

    def update_status(
        self,
        run_id: str,
        status: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        record = self._require(run_id)
        record["status"] = status
        if reason is not None:
            record["status_reason"] = reason
        record["updated_at"] = _now()
        self._save(record)
        return deepcopy(record)

    def write_artifact(self, run_id: str, name: str, artifact: Any) -> dict[str, Any]:
        record = self._require(run_id)
        record.setdefault("artifacts", {})[name] = _jsonable(artifact)
        record["updated_at"] = _now()
        self._save(record)
        return deepcopy(record)

    def write_evidence(self, run_id: str, evidence: Any) -> dict[str, Any]:
        record = self._require(run_id)
        record.setdefault("evidence", []).append(_jsonable(evidence))
        record["updated_at"] = _now()
        self._save(record)
        return deepcopy(record)

    def write_verdict(self, run_id: str, verdict: Any) -> dict[str, Any]:
        record = self._require(run_id)
        record.setdefault("verdicts", []).append(_jsonable(verdict))
        record["updated_at"] = _now()
        self._save(record)
        return deepcopy(record)

    def write_result(self, run_id: str, result: Any) -> dict[str, Any]:
        record = self._require(run_id)
        record["result"] = _jsonable(result)
        record["updated_at"] = _now()
        self._save(record)
        return deepcopy(record)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        self._validate_run_id(run_id)
        record = self._load(run_id)
        return deepcopy(record) if record is not None else None

    def resume_run(self, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        record = self._require(run_id)
        record["attempt"] = int(record.get("attempt") or 0) + 1
        record["status"] = "queued"
        record.pop("status_reason", None)
        record["artifacts"] = {}
        record["evidence"] = []
        record["verdicts"] = []
        record["result"] = None
        record["updated_at"] = _now()
        record.setdefault("events", []).append(
            {
                "type": "resume",
                "attempt": record["attempt"],
                "created_at": record["updated_at"],
            }
        )
        self._save(record)
        return deepcopy(record)

    def _require(self, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        record = self._load(run_id)
        if record is None:
            raise KeyError(f"run {run_id!r} was not found")
        return record

    def _load(self, run_id: str) -> dict[str, Any] | None:
        self._validate_run_id(run_id)
        if run_id in self._runs:
            return self._runs[run_id]
        if self.root is None:
            return None
        path = self._path_for(run_id)
        if not path.exists():
            return None
        import json

        record = json.loads(path.read_text(encoding="utf-8"))
        self._runs[run_id] = record
        return record

    def _save(self, record: dict[str, Any]) -> None:
        self._runs[record["run_id"]] = record
        if self.root is None:
            return
        import json

        run_id = str(record["run_id"])
        self._validate_run_id(run_id)
        path = self._path_for(run_id)
        tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        tmp_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    def _new_run_id(self) -> str:
        while True:
            run_id = f"run_{uuid4().hex[:12]}"
            if self._load(run_id) is None:
                return run_id

    def _path_for(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        if self.root is None:
            raise ValueError("file path requested for in-memory store")
        path = (self.root / f"{run_id}.json").resolve()
        if path.parent != self.root:
            raise ValueError(f"run_id {run_id!r} escapes store root")
        return path

    def _validate_run_id(self, run_id: str) -> None:
        if not RUN_ID_RE.fullmatch(run_id):
            raise ValueError(f"invalid run_id {run_id!r}")


DEFAULT_STORE = LocalRunStore()


def get_default_store() -> LocalRunStore:
    return store_from_env()


def store_from_env() -> LocalRunStore:
    root = os.environ.get(STORE_ROOT_ENV)
    if root:
        return LocalRunStore(root)
    return DEFAULT_STORE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return deepcopy(value)
