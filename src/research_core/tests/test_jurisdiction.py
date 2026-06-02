from research_core.jurisdiction_registry import resolve_air_district, resolve_water_board
from research_core.jurisdiction_resolve import (
    _blocks_for_gap,
    apply_jurisdiction_to_scope,
    resolve_jurisdiction,
)
from research_core.jurisdiction_skills import (
    jurisdiction_skill_id,
    resolve_jurisdiction_skills,
)
from research_core.models import ScopePack


def test_los_angeles_county_requires_air_geometry_but_has_water_board():
    air = resolve_air_district("Los Angeles")
    water = resolve_water_board("Los Angeles")

    assert air.needs_geometry is True
    assert any(d.name == "South Coast AQMD" for d in air.districts)
    assert water.needs_geometry is True
    assert any(
        b.name == "Los Angeles Regional Water Quality Control Board"
        for b in water.boards
    )


def test_air_district_strips_trailing_county_suffix():
    air = resolve_air_district("Los Angeles County")

    assert air.needs_geometry is True
    assert any(d.name == "South Coast AQMD" for d in air.districts)


def test_jurisdiction_skill_id_deaccents_city():
    assert (
        jurisdiction_skill_id("Santa Clara", "San José")
        == "santa-clara-county/city-of-san-jose"
    )


def test_resolve_jurisdiction_reports_gaps_without_guessing():
    resolved = resolve_jurisdiction({"county": None, "city": "Nowhere"})

    assert resolved.stack == ()
    assert "location:county_unknown" in resolved.gaps


def test_resolve_jurisdiction_skills_reads_existing_county_and_city():
    resolved = resolve_jurisdiction_skills(
        {"county": "Los Angeles", "city": "Los Angeles"}
    )

    assert resolved.county is not None
    assert resolved.county.id == "los-angeles-county"
    assert resolved.city is not None
    assert resolved.city.id == "los-angeles-county/city-of-los-angeles"
    assert resolved.gaps == ()


def test_resolve_jurisdiction_skills_normalizes_punctuation():
    resolved = resolve_jurisdiction_skills({"county": "Napa", "city": "St. Helena"})

    assert resolved.city is not None
    assert resolved.city.id == "napa-county/city-of-st-helena"
    assert "city:napa-county/city-of-st-helena" not in resolved.gaps


def test_apply_jurisdiction_to_scope_returns_copy_with_missing_facts():
    scope = ScopePack(
        run_id="run_1",
        facility={
            "address": "1 Main St, Los Angeles, CA",
            "jurisdiction_stack": ["California"],
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

    updated = apply_jurisdiction_to_scope(scope)

    assert updated is not scope
    assert scope.facility.jurisdiction_stack == ["California"]
    assert "South Coast AQMD" in updated.facility.jurisdiction_stack
    assert any(
        m.field == "jurisdiction.air_geometry:Los Angeles"
        for m in updated.missing_facts
    )


def test_water_geometry_gap_blocks_water_determinations():
    scope = ScopePack(
        run_id="run_1",
        facility={
            "address": "1 Main St, Los Angeles, CA",
            "jurisdiction_stack": ["California"],
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

    updated = apply_jurisdiction_to_scope(scope)
    water_geometry = next(
        m
        for m in updated.missing_facts
        if m.field == "jurisdiction.water_geometry:Los Angeles"
    )

    assert water_geometry.blocks == ["stormwater", "wastewater"]


def test_unknown_future_gap_blocks_all_jurisdiction_dependent_families():
    assert _blocks_for_gap("future_gap:Los Angeles") == [
        "air",
        "stormwater",
        "hazmat",
        "waste",
        "wastewater",
        "land_use",
        "fire_code",
    ]
