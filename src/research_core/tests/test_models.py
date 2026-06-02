from research_core.models import (
    FactProvenance,
    InformationRequest,
    RunStatus,
    Scenario,
    ScopePack,
)


def test_scope_pack_requires_county_city_fields():
    scope = ScopePack(
        run_id="run_1",
        facility={
            "address": "1 Main St, Los Angeles, CA",
            "jurisdiction_stack": [],
            "county": "Los Angeles",
            "city": "Los Angeles",
            "naics": None,
            "sic": None,
        },
        project_change={
            "description": "new coating line",
            "equipment": [],
            "chemicals": [],
            "waste_streams": [],
            "disturbance_acres": None,
            "process_discharge": None,
        },
        missing_facts=[],
        assumptions=[],
    )

    assert scope.facility.county == "Los Angeles"
    assert scope.facility.city == "Los Angeles"


def test_information_request_and_scenarios_are_first_class():
    request = InformationRequest(
        field="chemicals.quantity",
        question="How many gallons of solvent will be stored on site?",
        why_needed="HMBP applicability depends on hazardous material quantity.",
        blocks=["ca-hmbp"],
    )
    scenario = Scenario(
        id="solvent-expected",
        label="expected",
        assumptions=[
            {
                "field": "chemicals.quantity",
                "value": 60,
                "unit": "gal",
                "provenance": FactProvenance.AGENT_INFERRED,
            }
        ],
        rationale="Typical drum storage for a small coating operation.",
        affects=["ca-hmbp"],
    )

    assert RunStatus.NEEDS_INFORMATION.value == "needs_information"
    assert request.blocks == ["ca-hmbp"]
    assert scenario.assumptions[0].provenance == FactProvenance.AGENT_INFERRED
