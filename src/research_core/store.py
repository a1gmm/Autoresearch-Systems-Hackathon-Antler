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
STORE_BACKEND_ENV = "RESEARCH_CORE_STORE_BACKEND"
SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_KEY_ENVS = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")
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
        _validate_run_id(run_id)
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
        _validate_run_id(run_id)
        record = self._load(run_id)
        return deepcopy(record) if record is not None else None

    def resume_run(self, run_id: str) -> dict[str, Any]:
        _validate_run_id(run_id)
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
        _validate_run_id(run_id)
        record = self._load(run_id)
        if record is None:
            raise KeyError(f"run {run_id!r} was not found")
        return record

    def _load(self, run_id: str) -> dict[str, Any] | None:
        _validate_run_id(run_id)
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
        _validate_run_id(run_id)
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
        _validate_run_id(run_id)
        if self.root is None:
            raise ValueError("file path requested for in-memory store")
        path = (self.root / f"{run_id}.json").resolve()
        if path.parent != self.root:
            raise ValueError(f"run_id {run_id!r} escapes store root")
        return path


class SupabaseRunStore:
    def __init__(self, url: str, service_key: str, *, client: Any | None = None):
        self.client = client or _create_supabase_client(url, service_key)

    def create_run(
        self,
        input_payload: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or self._new_run_id()
        _validate_run_id(run_id)
        if self.get_run(run_id) is not None:
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
        self._save_run(record)
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
        self._save_run(record)
        return deepcopy(record)

    def write_artifact(self, run_id: str, name: str, artifact: Any) -> dict[str, Any]:
        record = self._require(run_id)
        record.setdefault("artifacts", {})[name] = _jsonable(artifact)
        record["updated_at"] = _now()
        self._save_run(record)
        return deepcopy(record)

    def write_evidence(self, run_id: str, evidence: Any) -> dict[str, Any]:
        record = self._require(run_id)
        bundle = _jsonable(evidence)
        current = record.setdefault("evidence", [])
        evidence_id = _evidence_id_for_bundle(bundle, current)
        current.append(bundle)
        record["updated_at"] = _now()
        self._save_evidence(run_id, evidence_id, bundle)
        self._save_run(record)
        return deepcopy(record)

    def write_verdict(self, run_id: str, verdict: Any) -> dict[str, Any]:
        record = self._require(run_id)
        record.setdefault("verdicts", []).append(_jsonable(verdict))
        record["updated_at"] = _now()
        self._save_run(record)
        return deepcopy(record)

    def write_result(self, run_id: str, result: Any) -> dict[str, Any]:
        record = self._require(run_id)
        record["result"] = _jsonable(result)
        record["updated_at"] = _now()
        self._save_run(record)
        return deepcopy(record)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        _validate_run_id(run_id)
        row = self._load_run_row(run_id)
        if row is None:
            return None
        return deepcopy(self._record_from_rows(row, self._load_evidence_rows(run_id)))

    def resume_run(self, run_id: str) -> dict[str, Any]:
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
        self._delete_evidence(run_id)
        self._save_run(record)
        return deepcopy(record)

    def _require(self, run_id: str) -> dict[str, Any]:
        record = self.get_run(run_id)
        if record is None:
            raise KeyError(f"run {run_id!r} was not found")
        return record

    def _new_run_id(self) -> str:
        while True:
            run_id = f"run_{uuid4().hex[:12]}"
            if self.get_run(run_id) is None:
                return run_id

    def _load_run_row(self, run_id: str) -> dict[str, Any] | None:
        query = self.client.table("research_runs").select("*").eq("run_id", run_id)
        maybe_single = getattr(query, "maybe_single", None)
        if callable(maybe_single):
            query = maybe_single()
        data = _execute_data(query)
        if isinstance(data, list):
            return data[0] if data else None
        return data if isinstance(data, dict) else None

    def _load_evidence_rows(self, run_id: str) -> list[dict[str, Any]]:
        query = (
            self.client.table("research_evidence")
            .select("evidence_id,hypothesis_id,bundle,created_at")
            .eq("run_id", run_id)
        )
        order = getattr(query, "order", None)
        if callable(order):
            query = order("created_at")
        data = _execute_data(query)
        return data if isinstance(data, list) else []

    def _save_run(self, record: dict[str, Any]) -> None:
        row = _run_row_from_record(record)
        _execute_data(self.client.table("research_runs").upsert(row))

    def _save_evidence(
        self,
        run_id: str,
        evidence_id: str,
        bundle: dict[str, Any],
    ) -> None:
        row = {
            "run_id": run_id,
            "evidence_id": evidence_id,
            "hypothesis_id": str(bundle.get("hypothesis_id") or evidence_id),
            "bundle": bundle,
        }
        query = self.client.table("research_evidence")
        try:
            upsert = query.upsert(row, on_conflict="run_id,evidence_id")
        except TypeError:
            upsert = query.upsert(row)
        _execute_data(upsert)

    def _delete_evidence(self, run_id: str) -> None:
        _execute_data(self.client.table("research_evidence").delete().eq("run_id", run_id))

    def _record_from_rows(
        self,
        row: dict[str, Any],
        evidence_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        artifacts = dict(row.get("artifacts") or {})
        if row.get("scope_pack") is not None:
            artifacts.setdefault("scope", row["scope_pack"])
        if row.get("plan") is not None:
            artifacts.setdefault("plan", row["plan"])
        if row.get("trace_events") is not None:
            artifacts.setdefault("trace_events", row["trace_events"])
        record = {
            "run_id": row["run_id"],
            "status": row.get("status") or "queued",
            "attempt": int(row.get("attempt") or 1),
            "input": row.get("input") or {},
            "artifacts": artifacts,
            "evidence": [item.get("bundle") for item in evidence_rows if item.get("bundle") is not None],
            "verdicts": row.get("verdicts") or [],
            "result": row.get("result"),
            "events": row.get("events") or [],
            "created_at": row.get("created_at") or _now(),
            "updated_at": row.get("updated_at") or row.get("created_at") or _now(),
        }
        if row.get("status_reason") is not None:
            record["status_reason"] = row["status_reason"]
        return record


DEFAULT_STORE = LocalRunStore()


def get_default_store() -> Any:
    return store_from_env()


def store_from_env() -> Any:
    backend = os.environ.get(STORE_BACKEND_ENV, "").strip().lower()
    supabase_url = os.environ.get(SUPABASE_URL_ENV)
    supabase_key = _supabase_service_key_from_env()
    if backend == "supabase" or (backend != "local" and (supabase_url or supabase_key)):
        if not supabase_url or not supabase_key:
            raise RuntimeError(
                "Supabase store selected but SUPABASE_URL and a service role key are not both set."
            )
        return SupabaseRunStore(supabase_url, supabase_key)

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


def _validate_run_id(run_id: str) -> None:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"invalid run_id {run_id!r}")


def _supabase_service_key_from_env() -> str | None:
    for name in SUPABASE_SERVICE_KEY_ENVS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _create_supabase_client(url: str, service_key: str) -> Any:
    try:
        from supabase import create_client
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Supabase persistence requires the supabase package. Install "
            "requirements-dev.txt locally or include supabase in the Modal image."
        ) from exc
    return create_client(url, service_key)


def _execute_data(query: Any) -> Any:
    response = query.execute()
    return getattr(response, "data", response)


def _run_row_from_record(record: dict[str, Any]) -> dict[str, Any]:
    artifacts = record.get("artifacts") or {}
    scope = artifacts.get("scope")
    plan = artifacts.get("plan")
    result = record.get("result")
    row = {
        "run_id": record["run_id"],
        "status": record.get("status") or "queued",
        "attempt": int(record.get("attempt") or 1),
        "input": _jsonable(record.get("input") or {}),
        "artifacts": _jsonable(artifacts),
        "verdicts": _jsonable(record.get("verdicts") or []),
        "result": _jsonable(result),
        "events": _jsonable(record.get("events") or []),
        "status_reason": record.get("status_reason"),
        "scope_pack": _jsonable(scope),
        "plan": _jsonable(plan),
        "jurisdiction_stack": _jurisdiction_stack(scope),
        "task_count": _task_count(plan),
        "determinations": _jsonable(_determination_payload(result)),
        "report_markdown": _report_markdown(result),
        "trace_events": _jsonable(artifacts.get("trace_events") or []),
        "created_at": record.get("created_at") or _now(),
        "updated_at": record.get("updated_at") or _now(),
    }
    return row


def _jurisdiction_stack(scope: Any) -> list[str]:
    if isinstance(scope, BaseModel):
        scope = scope.model_dump(mode="json")
    if not isinstance(scope, dict):
        return []
    facility = scope.get("facility")
    if not isinstance(facility, dict):
        return []
    stack = facility.get("jurisdiction_stack")
    return [str(item) for item in stack] if isinstance(stack, list) else []


def _task_count(plan: Any) -> int:
    if isinstance(plan, BaseModel):
        plan = plan.model_dump(mode="json")
    if not isinstance(plan, dict):
        return 0
    tasks = plan.get("research_tasks")
    return len(tasks) if isinstance(tasks, list) else 0


def _determination_payload(result: Any) -> Any:
    if isinstance(result, BaseModel):
        result = result.model_dump(mode="json")
    if not isinstance(result, dict):
        return None
    return result.get("determinations") or result.get("determination")


def _report_markdown(result: Any) -> str | None:
    if isinstance(result, BaseModel):
        result = result.model_dump(mode="json")
    if not isinstance(result, dict):
        return None
    value = result.get("report_markdown") or result.get("markdown")
    if isinstance(value, str):
        return value
    report = result.get("report")
    if isinstance(report, dict) and isinstance(report.get("summary"), str):
        return report["summary"]
    return None


def _evidence_id_for_bundle(
    bundle: dict[str, Any],
    existing: list[dict[str, Any]],
) -> str:
    evidence_id = _clean_evidence_id(_raw_evidence_id_for_bundle(bundle))
    existing_ids = {
        _clean_evidence_id(_raw_evidence_id_for_bundle(item))
        for item in existing
    }
    if evidence_id not in existing_ids:
        return evidence_id
    suffix = 2
    while f"{evidence_id}:{suffix}" in existing_ids:
        suffix += 1
    return f"{evidence_id}:{suffix}"


def _clean_evidence_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_:.=-]+", "-", value.strip())
    return cleaned[:240] or f"evidence:{uuid4().hex}"


def _raw_evidence_id_for_bundle(bundle: dict[str, Any]) -> str:
    raw = bundle.get("evidence_id")
    if raw is None:
        hypothesis_id = str(bundle.get("hypothesis_id") or "evidence")
        repair_id = bundle.get("repair_ticket_id")
        raw = f"{hypothesis_id}:{repair_id}" if repair_id else hypothesis_id
    return str(raw)
