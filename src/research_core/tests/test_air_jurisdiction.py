from __future__ import annotations

from research_core.jurisdiction_resolve import apply_jurisdiction_to_scope
from research_core.orchestrator import scope_from_input
from research_core.planner import plan_research


def _air_hypotheses(county: str | None, city: str | None) -> set[str]:
    scope = apply_jurisdiction_to_scope(
        scope_from_input(
            {
                "project_description": "adds a coating booth and spray operation",
                "facility": {"county": county, "city": city},
            },
            "r",
        )
    )
    plan = plan_research(scope)
    return {h.id for h in plan.research_graph if h.id.startswith("H-AIR")}


def test_vcapcd_air_programs_activate_only_in_ventura():
    ventura = _air_hypotheses("Ventura", "Oxnard")
    los_angeles = _air_hypotheses("Los Angeles", "Los Angeles")

    vcapcd = {"H-AIR-VCAPCD-PERMIT", "H-AIR-VCAPCD-RULE23", "H-AIR-VCAPCD-RULE74"}
    assert vcapcd <= ventura  # VCAPCD coverage present for a Ventura facility
    assert not (vcapcd & los_angeles)  # and absent for a Los Angeles facility


def test_untagged_air_programs_are_not_jurisdiction_gated():
    # The statewide/template air programs still appear regardless of county (no regression).
    no_county = _air_hypotheses(None, None)
    assert "H-AIR-201" in no_county
