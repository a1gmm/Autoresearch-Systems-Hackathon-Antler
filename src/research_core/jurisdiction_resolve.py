from __future__ import annotations

from dataclasses import dataclass

from research_core.jurisdiction_registry import (
    AirDistrict,
    RegionalWaterBoard,
    resolve_air_district,
    resolve_water_board,
)
from research_core.jurisdiction_skills import (
    JurisdictionSkill,
    resolve_jurisdiction_skills,
)
from research_core.models import MissingFact, ScopePack


@dataclass(frozen=True)
class ResolvedJurisdiction:
    county: str | None
    city: str | None
    air_districts: tuple[AirDistrict, ...]
    air_needs_geometry: bool
    water_boards: tuple[RegionalWaterBoard, ...]
    water_needs_geometry: bool
    county_skill: JurisdictionSkill | None
    city_skill: JurisdictionSkill | None
    stack: tuple[str, ...]
    gaps: tuple[str, ...]


ALL_JURISDICTION_BLOCKS = (
    "air",
    "stormwater",
    "hazmat",
    "waste",
    "wastewater",
    "land_use",
    "fire_code",
)


def resolve_jurisdiction(
    facility: dict[str, str | None],
) -> ResolvedJurisdiction:
    county = facility.get("county")
    city = facility.get("city")

    if not county:
        return ResolvedJurisdiction(
            county=None,
            city=city,
            air_districts=(),
            air_needs_geometry=False,
            water_boards=(),
            water_needs_geometry=False,
            county_skill=None,
            city_skill=None,
            stack=(),
            gaps=("location:county_unknown",),
        )

    air = resolve_air_district(county)
    water = resolve_water_board(county)
    skills = resolve_jurisdiction_skills(
        {"county": county, **({"city": city} if city else {})}
    )

    gaps = list(skills.gaps)
    if air.needs_geometry:
        gaps.append(f"air_geometry:{county}")
    if len(air.districts) == 0:
        gaps.append(f"air_district:{county}")
    if water.needs_geometry:
        gaps.append(f"water_geometry:{county}")
    if len(water.boards) == 0:
        gaps.append(f"water_board:{county}")

    stack: list[str] = []
    stack.extend(district.name for district in air.districts)
    stack.extend(board.name for board in water.boards)
    if skills.county:
        stack.append(f"{county} County local programs (CUPA / fire / building)")
    if skills.city and city:
        stack.append(f"{city} local programs")

    return ResolvedJurisdiction(
        county=county,
        city=city,
        air_districts=air.districts,
        air_needs_geometry=air.needs_geometry,
        water_boards=water.boards,
        water_needs_geometry=water.needs_geometry,
        county_skill=skills.county,
        city_skill=skills.city,
        stack=tuple(stack),
        gaps=tuple(gaps),
    )


def jurisdiction_context_for(facility: dict[str, str | None]) -> str:
    resolved = resolve_jurisdiction(facility)
    parts: list[str] = []

    if resolved.stack:
        parts.append("Resolved controlling authorities for this location:")
        for name in resolved.stack:
            parts.append(f"  - {name}")

    if resolved.county_skill:
        parts.append(
            "\n## County local-authority reference\n"
            + resolved.county_skill.content.strip()
        )
    if resolved.city_skill:
        parts.append(
            "\n## City local-authority reference\n"
            + resolved.city_skill.content.strip()
        )

    if resolved.gaps:
        parts.append(
            "\nUNRESOLVED jurisdiction levels - do NOT assume an authority for these; "
            "treat any dependent determination as needs_review until confirmed: "
            + ", ".join(resolved.gaps)
        )

    if parts:
        return "\n".join(parts)
    return (
        "Jurisdiction unresolved - no county provided; confirm the controlling "
        "authority before any local determination."
    )


def _blocks_for_gap(gap: str) -> list[str]:
    if gap.startswith("air_"):
        return ["air"]
    if gap.startswith("water_"):
        return ["stormwater", "wastewater"]
    if gap.startswith("location:"):
        return list(ALL_JURISDICTION_BLOCKS)
    if gap.startswith("county:") or gap.startswith("city:"):
        return ["hazmat", "waste", "land_use", "fire_code"]
    return list(ALL_JURISDICTION_BLOCKS)


def _model_copy(model, **updates):
    if hasattr(model, "model_copy"):
        return model.model_copy(update=updates, deep=True)
    return model.copy(update=updates, deep=True)


def apply_jurisdiction_to_scope(scope: ScopePack) -> ScopePack:
    resolved = resolve_jurisdiction(
        {"county": scope.facility.county, "city": scope.facility.city}
    )
    jurisdiction_stack = (
        resolved.stack if resolved.stack else scope.facility.jurisdiction_stack
    )

    missing_facts = [
        _model_copy(missing_fact, blocks=list(missing_fact.blocks))
        for missing_fact in scope.missing_facts
    ]
    existing_fields = {missing_fact.field for missing_fact in missing_facts}
    for gap in resolved.gaps:
        field = f"jurisdiction.{gap}"
        if field in existing_fields:
            continue
        missing_facts.append(
            MissingFact(
                field=field,
                why_needed=(
                    "Local jurisdiction could not be resolved to a single "
                    "controlling authority; the responsible agency and its "
                    "adopted rules must be confirmed before any determination."
                ),
                blocks=_blocks_for_gap(gap),
            )
        )
        existing_fields.add(field)

    facility = _model_copy(
        scope.facility,
        jurisdiction_stack=list(jurisdiction_stack),
    )
    return _model_copy(scope, facility=facility, missing_facts=missing_facts)
