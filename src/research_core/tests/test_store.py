from __future__ import annotations

from copy import deepcopy
import sys
from types import ModuleType

import pytest

from research_core.store import (
    STORE_BACKEND_ENV,
    STORE_ROOT_ENV,
    SUPABASE_SERVICE_KEY_ENVS,
    SUPABASE_URL_ENV,
    SupabaseRunStore,
    store_from_env,
)


def test_store_from_env_uses_supabase_when_service_credentials_are_present(monkeypatch):
    fake_client = FakeSupabaseClient()
    fake_supabase = ModuleType("supabase")
    captured = {}

    def create_client(url, key):
        captured["url"] = url
        captured["key"] = key
        return fake_client

    fake_supabase.create_client = create_client
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase)
    monkeypatch.setenv(SUPABASE_URL_ENV, "https://example.supabase.co")
    monkeypatch.setenv(SUPABASE_SERVICE_KEY_ENVS[0], "service-role-key")
    monkeypatch.delenv(STORE_BACKEND_ENV, raising=False)
    monkeypatch.delenv(STORE_ROOT_ENV, raising=False)

    store = store_from_env()
    record = store.create_run({"project_description": "demo"}, run_id="run_supabase")

    assert isinstance(store, SupabaseRunStore)
    assert captured == {
        "url": "https://example.supabase.co",
        "key": "service-role-key",
    }
    assert record["run_id"] == "run_supabase"
    assert fake_client.runs["run_supabase"]["input"]["project_description"] == "demo"


def test_store_from_env_rejects_partial_supabase_configuration(monkeypatch):
    monkeypatch.setenv(SUPABASE_URL_ENV, "https://example.supabase.co")
    monkeypatch.delenv(STORE_BACKEND_ENV, raising=False)
    monkeypatch.delenv(SUPABASE_SERVICE_KEY_ENVS[0], raising=False)
    monkeypatch.delenv(SUPABASE_SERVICE_KEY_ENVS[1], raising=False)
    monkeypatch.delenv(STORE_ROOT_ENV, raising=False)

    with pytest.raises(RuntimeError, match="SUPABASE_URL and a service role key"):
        store_from_env()


def test_supabase_store_round_trips_run_state_and_repair_evidence():
    client = FakeSupabaseClient()
    store = SupabaseRunStore("https://example.supabase.co", "service-role-key", client=client)

    store.create_run({"project_description": "demo"}, run_id="run_roundtrip")
    store.update_status("run_roundtrip", "researching", reason="working")
    store.write_artifact(
        "run_roundtrip",
        "scope",
        {"run_id": "run_roundtrip", "facility": {"jurisdiction_stack": ["SCAQMD"]}},
    )
    store.write_artifact(
        "run_roundtrip",
        "plan",
        {"research_tasks": [{"task_id": "task-1"}]},
    )
    store.write_artifact("run_roundtrip", "trace_events", [{"phase": "research"}])
    store.write_evidence("run_roundtrip", {"hypothesis_id": "H-1", "sources": []})
    store.write_evidence(
        "run_roundtrip",
        {
            "hypothesis_id": "H-1",
            "repair_ticket_id": "R-H-1-conf",
            "sources": [],
        },
    )
    store.write_verdict("run_roundtrip", {"hypothesis_id": "H-1", "verdict": "needs_review"})
    store.write_result(
        "run_roundtrip",
        {
            "run_id": "run_roundtrip",
            "determination": {"status": "needs_review"},
            "report": {"summary": "review"},
            "evidence": [],
        },
    )

    loaded = store.get_run("run_roundtrip")

    assert loaded["status"] == "researching"
    assert loaded["status_reason"] == "working"
    assert loaded["artifacts"]["scope"]["facility"]["jurisdiction_stack"] == ["SCAQMD"]
    assert loaded["artifacts"]["plan"]["research_tasks"][0]["task_id"] == "task-1"
    assert loaded["artifacts"]["trace_events"] == [{"phase": "research"}]
    assert len(loaded["evidence"]) == 2
    assert loaded["evidence"][1]["repair_ticket_id"] == "R-H-1-conf"
    assert loaded["verdicts"][0]["verdict"] == "needs_review"
    assert loaded["result"]["determination"]["status"] == "needs_review"
    assert client.runs["run_roundtrip"]["task_count"] == 1
    assert client.runs["run_roundtrip"]["jurisdiction_stack"] == ["SCAQMD"]
    assert set(client.evidence) == {
        ("run_roundtrip", "H-1"),
        ("run_roundtrip", "H-1:R-H-1-conf"),
    }


def test_supabase_resume_clears_attempt_scoped_state_and_increments_attempt():
    client = FakeSupabaseClient()
    store = SupabaseRunStore("https://example.supabase.co", "service-role-key", client=client)
    store.create_run({"project_description": "demo"}, run_id="run_resume")
    store.write_artifact("run_resume", "plan", {"research_tasks": [{"task_id": "task-1"}]})
    store.write_evidence("run_resume", {"hypothesis_id": "H-1"})
    store.write_verdict("run_resume", {"hypothesis_id": "H-1", "verdict": "pass"})
    store.write_result("run_resume", {"run_id": "run_resume"})

    resumed = store.resume_run("run_resume")
    loaded = store.get_run("run_resume")

    assert resumed["attempt"] == 2
    assert resumed["status"] == "queued"
    assert resumed["artifacts"] == {}
    assert resumed["evidence"] == []
    assert resumed["verdicts"] == []
    assert resumed["result"] is None
    assert loaded["attempt"] == 2
    assert loaded["evidence"] == []
    assert client.evidence == {}


class FakeSupabaseClient:
    def __init__(self):
        self.runs = {}
        self.evidence = {}

    def table(self, name):
        return FakeSupabaseQuery(self, name)


class FakeSupabaseQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.action = None
        self.payload = None
        self.filters = {}
        self.single = False

    def select(self, columns):
        self.action = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def maybe_single(self):
        self.single = True
        return self

    def order(self, column):
        return self

    def upsert(self, payload, **kwargs):
        self.action = "upsert"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def execute(self):
        if self.table == "research_runs":
            return self._execute_runs()
        if self.table == "research_evidence":
            return self._execute_evidence()
        raise AssertionError(f"unknown table {self.table}")

    def _execute_runs(self):
        if self.action == "upsert":
            self.client.runs[self.payload["run_id"]] = deepcopy(self.payload)
            return FakeResponse(deepcopy(self.payload))
        if self.action == "select":
            rows = [
                deepcopy(row)
                for row in self.client.runs.values()
                if _matches(row, self.filters)
            ]
            return FakeResponse(rows[0] if self.single and rows else (None if self.single else rows))
        raise AssertionError(f"unsupported run action {self.action}")

    def _execute_evidence(self):
        if self.action == "upsert":
            key = (self.payload["run_id"], self.payload["evidence_id"])
            self.client.evidence[key] = deepcopy(self.payload)
            return FakeResponse(deepcopy(self.payload))
        if self.action == "select":
            rows = [
                deepcopy(row)
                for row in self.client.evidence.values()
                if _matches(row, self.filters)
            ]
            return FakeResponse(rows)
        if self.action == "delete":
            for key, row in list(self.client.evidence.items()):
                if _matches(row, self.filters):
                    del self.client.evidence[key]
            return FakeResponse([])
        raise AssertionError(f"unsupported evidence action {self.action}")


class FakeResponse:
    def __init__(self, data):
        self.data = data


def _matches(row, filters):
    return all(row.get(key) == value for key, value in filters.items())
