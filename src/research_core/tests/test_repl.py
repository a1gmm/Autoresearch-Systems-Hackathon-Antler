from __future__ import annotations

from research_core.cli import _Style
from research_core.repl import Session, _handle_command, run_with_progress


def test_session_payload_collects_facts():
    s = Session(mode="fake", model=None)
    s.facility["county"] = "Ventura"
    s.provided_estimates["chemicals.quantity"] = "200 gal"
    p = s.payload("coating shop")
    assert p["project_description"] == "coating shop"
    assert p["facility"]["county"] == "Ventura"
    assert p["provided_estimates"]["chemicals.quantity"] == "200 gal"


def test_handle_command_sets_facts_and_quits():
    s = Session(mode="fake", model=None)
    style = _Style(enabled=False)
    assert _handle_command("/county Ventura", s, style) is True
    assert s.facility["county"] == "Ventura"
    assert _handle_command("/quantity 200 gal", s, style) is True
    assert s.provided_estimates["chemicals.quantity"] == "200 gal"
    assert _handle_command("/mode fake", s, style) is True
    assert s.mode == "fake"
    assert _handle_command("/quit", s, style) is False


def test_run_with_progress_returns_result_in_fake_mode():
    style = _Style(enabled=False)
    payload = {"project_description": "coating shop, 200 gal solvent",
               "facility": {"county": "Ventura", "city": "Oxnard"}}
    result = run_with_progress(payload, "fake", style)
    assert result is not None
    assert "status" in result
    assert result.get("verdicts")
