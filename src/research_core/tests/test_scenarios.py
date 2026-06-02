from research_core.models import FactProvenance, InformationRequest
from research_core.scenarios import (
    information_gap_options,
    is_valid_user_input,
    scenarios_for_missing_fact,
)


def test_unknown_quantity_gets_low_expected_high_scenarios():
    request = InformationRequest(
        field="chemicals.quantity",
        question="How many gallons?",
        why_needed="HMBP threshold",
        blocks=["ca-hmbp"],
    )
    scenarios = scenarios_for_missing_fact(request)
    assert [s.label for s in scenarios] == ["low", "expected", "high"]


def test_unknown_quantity_scenarios_are_agent_inferred():
    request = InformationRequest(
        field="chemicals.quantity",
        question="How many gallons?",
        why_needed="HMBP threshold",
        blocks=["ca-hmbp"],
    )

    scenarios = scenarios_for_missing_fact(request)

    assert all(
        assumption.provenance == FactProvenance.AGENT_INFERRED
        for scenario in scenarios
        for assumption in scenario.assumptions
    )


def test_disturbance_acres_gets_low_expected_high_agent_inferred_scenarios():
    request = InformationRequest(
        field="project_change.disturbance_acres",
        question="How many acres?",
        why_needed="Stormwater construction threshold",
        blocks=["stormwater-construction"],
    )

    scenarios = scenarios_for_missing_fact(request)
    values = [s.assumptions[0].value for s in scenarios]

    assert [s.label for s in scenarios] == ["low", "expected", "high"]
    assert values[0] < 1
    assert values[1] == 1
    assert values[2] > 1
    assert all(
        assumption.provenance == FactProvenance.AGENT_INFERRED
        and assumption.unit == "acre"
        for scenario in scenarios
        for assumption in scenario.assumptions
    )


def test_user_provided_estimate_preserves_provenance_and_counts_as_input():
    request = InformationRequest(
        field="chemicals.quantity",
        question="How many gallons?",
        why_needed="HMBP threshold",
        blocks=["ca-hmbp"],
    )

    scenarios = scenarios_for_missing_fact(
        request,
        provided_estimate=60,
        unit="gal",
    )

    assumption = scenarios[0].assumptions[0]
    assert assumption.value == 60
    assert assumption.provenance == FactProvenance.PROVIDED_ESTIMATE
    assert is_valid_user_input(assumption) is True


def test_user_does_not_know_gets_scenarios_and_suggestions():
    request = InformationRequest(
        field="chemicals.quantity",
        question="How many gallons?",
        why_needed="HMBP threshold",
        blocks=["ca-hmbp"],
    )

    options = information_gap_options(request, user_does_not_know=True)

    assert options.block_immediately is False
    assert [s.label for s in options.scenarios] == ["low", "expected", "high"]
    assert options.suggestions
