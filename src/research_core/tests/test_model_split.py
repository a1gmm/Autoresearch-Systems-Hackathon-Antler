from __future__ import annotations

from types import SimpleNamespace

from research_core.orchestrator import (
    DEFAULT_REPAIR_MODEL,
    ResearchDeps,
    _agent_model_from_env,
    _repair_model_from_env,
)


def test_worker_and_repair_models_split_by_env(monkeypatch):
    monkeypatch.setenv("RESEARCH_CORE_AGENT_MODEL", "gpt-5-mini")
    monkeypatch.setenv("RESEARCH_CORE_REPAIR_MODEL", "gpt-5.5")

    assert _agent_model_from_env() == "gpt-5-mini"
    assert _repair_model_from_env() == "gpt-5.5"


def test_repair_defaults_to_strong_model_when_worker_is_cheap(monkeypatch):
    monkeypatch.setenv("RESEARCH_CORE_AGENT_MODEL", "gpt-5-mini")
    monkeypatch.delenv("RESEARCH_CORE_REPAIR_MODEL", raising=False)

    # Worker goes cheap; repair stays strong by default (the tiered intent).
    assert _agent_model_from_env() == "gpt-5-mini"
    assert _repair_model_from_env() == DEFAULT_REPAIR_MODEL


def test_research_deps_repair_passes_repair_model_not_worker_model(monkeypatch):
    captured = {}

    def fake_repair(ticket, previous_bundle, scope, policy, *, model=None):
        captured["model"] = model
        return {
            "hypothesis_id": "H",
            "sources": [],
            "extracted_claims": [],
            "researcher_conclusion": "needs_review",
        }

    monkeypatch.setattr("research_core.orchestrator.run_repair_agent", fake_repair)
    deps = ResearchDeps(mode="live", agent_model="gpt-5-mini", repair_model="gpt-5.5")
    ticket = SimpleNamespace(hypothesis_id="H", ticket_id="R-H-001")
    scope = SimpleNamespace(run_id="run_1")

    deps.repair(ticket, {}, scope)

    assert captured["model"] == "gpt-5.5"  # repair used the strong model, not the cheap worker
