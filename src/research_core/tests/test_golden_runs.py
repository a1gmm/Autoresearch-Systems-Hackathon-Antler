from research_core.orchestrator import run_research_sync
from research_core.store import LocalRunStore


def test_golden_coating_booth_solvent_run_reaches_terminal_report():
    result = run_research_sync(
        {
            "project_description": (
                "A Los Angeles County coating shop adds a coating booth and stores "
                "60 gal flammable solvent."
            ),
            "facility": {"county": "Los Angeles", "city": "Los Angeles"},
        },
        deps="fake",
    )

    assert result.status in {"done", "needs_review"}
    assert result.result["report"]["summary"]
    assert result.result["determination"]["status"] in {"verified", "needs_review"}
    assert result.evidence
    assert result.verdicts


def test_golden_missing_solvent_quantity_requests_information():
    result = run_research_sync(
        {"project_description": "A coating shop stores solvent, unknown quantity."},
        deps="fake",
    )

    assert result.status == "needs_information"
    assert any(request.field == "chemicals.quantity" for request in result.information_requests)
    assert not result.evidence


def test_golden_user_does_not_know_gets_low_expected_high_scenarios():
    result = run_research_sync(
        {
            "project_description": "A coating shop stores solvent, unknown quantity.",
            "user_does_not_know": True,
        },
        deps="fake",
    )

    assert result.status in {"done", "needs_review"}
    assert result.information_requests
    assert {scenario.label for scenario in result.scenarios} == {"low", "expected", "high"}


def test_golden_complex_scenario_plans_more_tasks_than_simple():
    simple_store = LocalRunStore()
    complex_store = LocalRunStore()

    simple = run_research_sync(
        {"project_description": "A small tenant improvement adds office lighting."},
        deps="fake",
        store=simple_store,
    )
    complex_result = run_research_sync(
        {
            "project_description": (
                "A coating shop adds a coating booth, stores 60 gal solvent, "
                "generates process waste, and discharges process wastewater."
            ),
            "facility": {"county": "Los Angeles", "city": "Los Angeles"},
            "waste_streams": [{"description": "spent solvent", "kg_per_month": 20}],
            "process_discharge": True,
        },
        deps="fake",
        store=complex_store,
    )

    simple_tasks = simple_store.get_run(simple.run_id)["artifacts"]["plan"]["research_tasks"]
    complex_tasks = complex_store.get_run(complex_result.run_id)["artifacts"]["plan"]["research_tasks"]

    assert len(complex_tasks) > len(simple_tasks)


def test_golden_trusted_hypotheses_have_source_url_and_quote():
    result = run_research_sync(
        {
            "project_description": "A coating shop adds a coating booth and stores 60 gal solvent.",
            "facility": {"county": "Los Angeles", "city": "Los Angeles"},
        },
        deps="fake",
    )
    trusted = set(result.result["determination"]["trusted_hypotheses"])
    evidence_by_hypothesis = {bundle["hypothesis_id"]: bundle for bundle in result.evidence}

    for hypothesis_id in trusted:
        source = evidence_by_hypothesis[hypothesis_id]["sources"][0]
        assert source["url"]
        assert source["quote"]
