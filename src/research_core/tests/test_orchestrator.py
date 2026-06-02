import importlib
import sys
from types import ModuleType

import pytest

from research_core.orchestrator import ResearchDeps, run_research_sync, resume_research_sync
from research_core.orchestrator import scope_from_input
from research_core.planner import ResearchTask, ResearchTaskBudget
from research_core.store import LocalRunStore, store_from_env


def test_run_without_required_fact_requests_information():
    result = run_research_sync(
        {"project_description": "store solvent at a coating shop, unknown quantity"},
        deps="fake",
    )
    assert result.status in {"needs_information", "done", "needs_review"}
    assert result.run_id.startswith("run_")


def test_offline_run_persists_plan_evidence_verdict_and_result():
    store = LocalRunStore()

    result = run_research_sync(
        {
            "project_description": "store 60 gal solvent at a coating shop",
            "facility": {"city": "Los Angeles", "county": "Los Angeles"},
        },
        deps="fake",
        store=store,
    )

    record = store.get_run(result.run_id)
    assert record is not None
    assert record["status"] == result.status
    assert record["artifacts"]["scope"]["run_id"] == result.run_id
    assert record["artifacts"]["plan"]["research_tasks"]
    assert record["evidence"]
    assert record["verdicts"]
    assert record["result"]["run_id"] == result.run_id
    assert result.result["determination"]["status"] in {
        "verified",
        "needs_review",
        "needs_information",
    }


def test_unknown_quantity_can_continue_with_scenarios():
    result = run_research_sync(
        {
            "project_description": "store solvent at a coating shop, unknown quantity",
            "user_does_not_know": True,
        },
        deps="fake",
    )

    assert result.status in {"done", "needs_review"}
    assert result.information_requests
    assert result.scenarios
    assert {scenario.label for scenario in result.scenarios} == {
        "low",
        "expected",
        "high",
    }


def test_resume_run_uses_stored_input_and_updates_attempt():
    store = LocalRunStore()
    first = run_research_sync(
        {"project_description": "store 60 gal solvent at a coating shop"},
        deps="fake",
        store=store,
    )

    resumed = store.resume_run(first.run_id)

    assert resumed["run_id"] == first.run_id
    assert resumed["attempt"] == 2
    assert resumed["input"]["project_description"] == (
        "store 60 gal solvent at a coating shop"
    )


def test_resume_rerun_replaces_attempt_scoped_state():
    store = LocalRunStore()
    first = run_research_sync(
        {"project_description": "store 60 gal solvent at a coating shop"},
        deps="fake",
        store=store,
    )
    first_record = store.get_run(first.run_id)

    second = resume_research_sync(first.run_id, deps="fake", store=store)
    second_record = store.get_run(first.run_id)

    assert second.run_id == first.run_id
    assert second_record["attempt"] == 2
    assert len(second_record["evidence"]) == len(first_record["evidence"])
    assert len(second_record["verdicts"]) == len(first_record["verdicts"])
    assert second_record["result"]["run_id"] == first.run_id


def test_needs_review_repair_tickets_are_processed_up_to_budget():
    store = LocalRunStore()
    deps = CountingRepairDeps(max_repair_attempts=2)

    result = run_research_sync(
        {
            "project_description": "store solvent at a coating shop, unknown quantity",
            "user_does_not_know": True,
        },
        deps=deps,
        store=store,
    )

    repaired_ticket_ids = [call["ticket_id"] for call in deps.repair_calls]
    hmbp_ticket_ids = [
        ticket_id
        for ticket_id in repaired_ticket_ids
        if ticket_id.startswith("R-H-HAZMAT-HMBP")
    ]
    repair_counts_by_hypothesis = {}
    for call in deps.repair_calls:
        repair_counts_by_hypothesis[call["hypothesis_id"]] = (
            repair_counts_by_hypothesis.get(call["hypothesis_id"], 0) + 1
        )

    assert len(hmbp_ticket_ids) == 2
    assert any(ticket_id.endswith("predicate_math") for ticket_id in hmbp_ticket_ids)
    assert any(ticket_id.endswith("conf") for ticket_id in hmbp_ticket_ids)
    assert all(count <= 2 for count in repair_counts_by_hypothesis.values())
    assert result.status == "needs_review"
    assert any(
        "predicate_math failed" in reason
        for reason in result.result["determination"]["reasons"]
    )
    assert len(store.get_run(result.run_id)["evidence"]) >= len(result.evidence)


def test_failed_verdict_can_be_cleared_by_passing_repair():
    result = run_research_sync(
        {"project_description": "store 60 gal solvent"},
        deps=RepairPassDeps(initial="fail"),
        store=LocalRunStore(),
    )

    assert result.status == "done"
    assert result.result["determination"]["status"] == "verified"
    assert result.verdicts
    assert all(verdict.verdict == "pass" for verdict in result.verdicts)
    assert all(not verdict.repair_tickets for verdict in result.verdicts)
    assert all(not verdict.distrust_reasons for verdict in result.verdicts)


def test_needs_review_verdict_can_be_cleared_by_passing_repair():
    result = run_research_sync(
        {"project_description": "store 60 gal solvent"},
        deps=RepairPassDeps(initial="needs_review"),
        store=LocalRunStore(),
    )

    assert result.status == "done"
    assert result.verdicts
    assert all(verdict.verdict == "pass" for verdict in result.verdicts)
    assert all(not verdict.repair_tickets for verdict in result.verdicts)


def test_unresolved_repair_budget_exhaustion_remains_needs_review():
    result = run_research_sync(
        {"project_description": "store 60 gal solvent"},
        deps=RepairPassDeps(initial="needs_review", max_repair_attempts=0),
        store=LocalRunStore(),
    )

    assert result.status == "needs_review"
    assert result.verdicts
    assert all(verdict.verdict == "needs_review" for verdict in result.verdicts)
    assert all(verdict.repair_tickets for verdict in result.verdicts)
    assert any(
        "Repair budget exhausted" in reason
        for reason in result.result["determination"]["reasons"]
    )


def test_file_store_rejects_traversal_run_id(tmp_path):
    store = LocalRunStore(tmp_path)

    with pytest.raises(ValueError, match="invalid run_id"):
        store.create_run({"project_description": "x"}, run_id="../escape")


def test_file_store_rejects_duplicate_run_id(tmp_path):
    store = LocalRunStore(tmp_path)
    store.create_run({"project_description": "x"}, run_id="run_duplicate")

    with pytest.raises(ValueError, match="already exists"):
        store.create_run({"project_description": "y"}, run_id="run_duplicate")


def test_store_from_env_uses_durable_root(monkeypatch, tmp_path):
    monkeypatch.setenv("RESEARCH_CORE_STORE_ROOT", str(tmp_path))
    monkeypatch.delenv("RESEARCH_CORE_STORE_BACKEND", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    store = store_from_env()
    record = store.create_run({"project_description": "x"}, run_id="run_env")

    assert record["run_id"] == "run_env"
    assert LocalRunStore(tmp_path).get_run("run_env")["input"]["project_description"] == "x"


def test_live_deps_call_researcher_agent_with_sandbox_policy(monkeypatch, tmp_path):
    task = ResearchTask(
        task_id="task-live",
        hypothesis_id="H-LIVE",
        assigned_agent="air_researcher",
        allowed_tools=["web_fetch", "submit_finding"],
        blocked_tools=[],
        budget=ResearchTaskBudget(max_sources=3, max_runtime_seconds=30, max_model_calls=2),
    )
    scope = scope_from_input(
        {"project_description": "install a coating booth"},
        "run_live",
    )
    captured = {}

    def fake_researcher_agent(task_arg, context, policy, **kwargs):
        captured["task_id"] = task_arg.task_id
        captured["run_id"] = policy.run_id
        captured["artifact_root"] = policy.artifact_root
        captured["allow_network"] = policy.allow_network
        return {
            "hypothesis_id": task_arg.hypothesis_id,
            "sources": [
                {
                    "url": "https://www.epa.gov/rules",
                    "source_name": "EPA",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "effective_date": "2026-01-01",
                    "currency_status": "current",
                    "quote": "Coating booth permit applicability is confirmed.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "applicability",
                    "value": "applies",
                    "source_url": "https://www.epa.gov/rules",
                    "quote": "Coating booth permit applicability is confirmed.",
                    "confidence": 0.95,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }

    monkeypatch.setenv("RESEARCH_CORE_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr("research_core.orchestrator.run_researcher_agent", fake_researcher_agent)

    bundle = ResearchDeps(mode="live").research(task, scope)

    assert captured == {
        "task_id": "task-live",
        "run_id": "run_live",
        "artifact_root": tmp_path,
        "allow_network": True,
    }
    assert bundle["hypothesis_id"] == "H-LIVE"
    assert bundle["researcher_conclusion"] == "applies"


def test_live_deps_fail_closed_when_agent_output_is_unavailable(monkeypatch):
    task = ResearchTask(
        task_id="task-live",
        hypothesis_id="H-LIVE",
        assigned_agent="air_researcher",
        allowed_tools=[],
        blocked_tools=[],
        budget=ResearchTaskBudget(max_sources=1, max_runtime_seconds=10, max_model_calls=1),
    )
    scope = scope_from_input({"project_description": "demo"}, "run_live")

    def fake_researcher_agent(*args, **kwargs):
        return {
            "ok": False,
            "status": "unavailable",
            "error": {"code": "agents_sdk_unavailable", "message": "SDK missing"},
        }

    monkeypatch.setattr("research_core.orchestrator.run_researcher_agent", fake_researcher_agent)

    bundle = ResearchDeps(mode="live").research(task, scope)

    assert bundle["sources"] == []
    assert bundle["researcher_conclusion"] == "needs_review"
    assert bundle["agent_error"]["code"] == "agents_sdk_unavailable"


def test_modal_app_registers_expected_functions_when_modal_is_available(monkeypatch):
    fake_modal = _fake_modal_module()
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    modal_app_module = importlib.import_module("research_core.modal_app")
    modal_app_module = importlib.reload(modal_app_module)

    app = modal_app_module.modal_app()

    assert app is not None
    assert app.name == "permitpilot-python-research"
    assert set(app.functions) == {
        "start_run",
        "run_sync",
        "resume_run",
        "get_run",
        "research_run",
    }
    assert app.functions["research_run"].background is True
    assert app.functions["start_run"].endpoint is True
    assert app.functions["run_sync"].endpoint is True
    assert app.functions["resume_run"].endpoint is True
    assert app.functions["get_run"].endpoint is True


def test_modal_run_sync_defaults_to_live_deps(monkeypatch):
    modal_app_module = importlib.import_module("research_core.modal_app")
    captured = {}

    class FakeResult:
        def model_dump(self, **kwargs):
            return {"run_id": "run_modal", "status": "done"}

    def fake_run_research_sync(input_payload, *, deps, store):
        captured["deps_mode"] = deps.mode
        captured["store"] = store
        return FakeResult()

    fake_store = object()
    monkeypatch.delenv("RESEARCH_CORE_DEPS_MODE", raising=False)
    monkeypatch.setattr(modal_app_module, "run_research_sync", fake_run_research_sync)
    monkeypatch.setattr(modal_app_module, "store_from_env", lambda: fake_store)

    response = modal_app_module.run_sync({"project_description": "demo"})

    assert response == {"run_id": "run_modal", "status": "done"}
    assert captured == {"deps_mode": "live", "store": fake_store}


def test_modal_function_options_include_runtime_image_and_supabase_secret():
    fake_modal = _fake_modal_module()
    fake_modal.Image = FakeModalImage
    fake_modal.Secret = FakeModalSecret

    modal_app_module = importlib.import_module("research_core.modal_app")

    options = modal_app_module._modal_function_options(fake_modal)

    assert "openai-agents" in options["image"].packages
    assert "supabase" in options["image"].packages
    assert "permitpilot-supabase" in [secret.name for secret in options["secrets"]]


def test_modal_start_run_spawns_background_research_run(monkeypatch):
    fake_modal = _fake_modal_module()
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    modal_app_module = importlib.import_module("research_core.modal_app")
    modal_app_module = importlib.reload(modal_app_module)
    app = modal_app_module.modal_app()

    response = app.functions["start_run"](
        {"project_description": "store 60 gal solvent at a coating shop"}
    )

    assert response["status"] == "queued"
    assert response["run_id"].startswith("run_")
    assert app.functions["research_run"].spawned == [
        (
            response["run_id"],
            {"project_description": "store 60 gal solvent at a coating shop"},
        )
    ]


def test_modal_background_can_run_from_payload_without_shared_memory(monkeypatch, tmp_path):
    fake_modal = _fake_modal_module()
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    monkeypatch.setenv("RESEARCH_CORE_STORE_ROOT", str(tmp_path))

    modal_app_module = importlib.import_module("research_core.modal_app")
    modal_app_module = importlib.reload(modal_app_module)
    app = modal_app_module.modal_app()
    payload = {"project_description": "store 60 gal solvent at a coating shop"}

    response = app.functions["start_run"](payload)
    result = app.functions["research_run"](response["run_id"], payload)

    assert result["run_id"] == response["run_id"]
    assert LocalRunStore(tmp_path).get_run(response["run_id"])["result"]["run_id"] == (
        response["run_id"]
    )


def _fake_modal_module():
    fake_modal = ModuleType("modal")
    fake_modal.App = FakeModalApp

    def fastapi_endpoint(*args, **kwargs):
        def decorator(function):
            function._fake_modal_endpoint = True
            return function

        return decorator

    fake_modal.fastapi_endpoint = fastapi_endpoint
    return fake_modal


class FakeModalFunction:
    def __init__(self, function, *, background=False):
        self.function = function
        self.background = background
        self.endpoint = bool(getattr(function, "_fake_modal_endpoint", False))
        self.spawned = []

    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)

    def spawn(self, *args, **kwargs):
        self.spawned.append(args)
        return {"spawned": True, "args": args, "kwargs": kwargs}


class FakeModalApp:
    def __init__(self, name):
        self.name = name
        self.functions = {}

    def function(self, **options):
        def decorator(function):
            modal_function = FakeModalFunction(
                function,
                background=bool(
                    options.get("is_background")
                    or getattr(function, "_permitpilot_background", False)
                ),
            )
            self.functions[function.__name__] = modal_function
            return modal_function

        return decorator


class FakeModalImage:
    def __init__(self):
        self.packages = ()
        self.local_dirs = []

    @classmethod
    def debian_slim(cls, **kwargs):
        image = cls()
        image.python_version = kwargs.get("python_version")
        return image

    def pip_install(self, *packages):
        self.packages = packages
        return self

    def add_local_dir(self, local_path, *, remote_path):
        self.local_dirs.append((local_path, remote_path))
        return self


class FakeModalSecret:
    def __init__(self, name):
        self.name = name

    @classmethod
    def from_name(cls, name):
        return cls(name)


class CountingRepairDeps(ResearchDeps):
    def __init__(self, *, max_repair_attempts):
        super().__init__(mode="fake", max_repair_attempts=max_repair_attempts)
        self.repair_calls = []

    def repair(self, ticket, previous_bundle, scope):
        self.repair_calls.append(ticket.model_dump(mode="json"))
        return super().repair(ticket, previous_bundle, scope)


class RepairPassDeps(ResearchDeps):
    def __init__(self, *, initial, max_repair_attempts=3):
        super().__init__(mode="fake", max_repair_attempts=max_repair_attempts)
        self.initial = initial

    def research(self, task, scope):
        if self.initial == "fail":
            return _bundle_for(task.hypothesis_id, grounded=False, conclusion="applies")
        return _bundle_for(task.hypothesis_id, grounded=True, conclusion="needs_review")

    def repair(self, ticket, previous_bundle, scope):
        return _bundle_for(ticket.hypothesis_id, grounded=True, conclusion="applies")


def _bundle_for(hypothesis_id, *, grounded, conclusion):
    source_quote = f"{hypothesis_id} repaired source proves applicability."
    claim_quote = source_quote if grounded else "different ungrounded quote"
    return {
        "hypothesis_id": hypothesis_id,
        "sources": [
            {
                "url": f"https://offline.local/{hypothesis_id.lower()}",
                "source_name": "Injected test source",
                "authority_rank": 1,
                "fetched_at": "2026-01-01T00:00:00Z",
                "effective_date": "2026-01-01",
                "currency_status": "current",
                "quote": source_quote,
            }
        ],
        "extracted_claims": [
            {
                "field": "applicability",
                "value": conclusion,
                "source_url": f"https://offline.local/{hypothesis_id.lower()}",
                "quote": claim_quote,
                "confidence": 0.9,
            }
        ],
        "researcher_conclusion": conclusion,
        "uncertainties": [],
    }
