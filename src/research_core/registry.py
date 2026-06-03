from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_core.models import ScopePack


@dataclass(frozen=True)
class ProgramHypothesis:
    id: str
    question: str
    claim_to_test: str


@dataclass(frozen=True)
class ProgramRegistryEntry:
    id: str
    family: str
    name: str
    what_it_does: str
    jurisdiction: str
    authority_source_url: str
    authority_rank: int
    hypotheses: tuple[ProgramHypothesis, ...]
    triggered_by: Callable[[ScopePack], bool]
    # Optional jurisdiction gate: the resolved air-district name this program is scoped to
    # (e.g. "Ventura County APCD"). None = statewide/federal/template (never gated).
    air_district: str | None = None


def _has_equipment(scope: ScopePack) -> bool:
    return len(scope.project_change.equipment) > 0


def _has_chemicals(scope: ScopePack) -> bool:
    return len(scope.project_change.chemicals) > 0


def _has_waste(scope: ScopePack) -> bool:
    return len(scope.project_change.waste_streams) > 0


def _has_code_or_acres(scope: ScopePack) -> bool:
    return (
        bool(scope.facility.sic)
        or bool(scope.facility.naics)
        or scope.project_change.disturbance_acres is not None
    )


def _discharge_possible(scope: ScopePack) -> bool:
    return scope.project_change.process_discharge is not False


def _always(scope: ScopePack) -> bool:
    return True


# Declarative trigger names (declared in each skill's program.json) mapped to the scope
# predicate that decides whether the program applies to a given project change.
_TRIGGERS: dict[str, Callable[[ScopePack], bool]] = {
    "equipment": _has_equipment,
    "chemicals": _has_chemicals,
    "waste": _has_waste,
    "code_or_acres": _has_code_or_acres,
    "discharge_possible": _discharge_possible,
    "always": _always,
}

# Law-code skills are the SOURCE OF TRUTH. Each skill folder under
# src/lib/research/skills/<id>/ carries a program.json declaring the program's coverage
# family, hypotheses, jurisdiction, authority, and trigger. PROGRAM_REGISTRY is BUILT from
# those files at import time, so adding a permit = adding a skill folder (no hand-maintained
# Python tuple to drift out of sync with the skills).
_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "lib" / "research" / "skills"


def _entry_from_data(data: dict[str, Any], source: Path) -> ProgramRegistryEntry:
    trigger = data.get("trigger")
    if trigger not in _TRIGGERS:
        raise ValueError(
            f"{source}: unknown trigger {trigger!r}; expected one of {sorted(_TRIGGERS)}"
        )
    return ProgramRegistryEntry(
        id=str(data["id"]),
        family=str(data["family"]),
        name=str(data["name"]),
        what_it_does=str(data["what_it_does"]),
        jurisdiction=str(data["jurisdiction"]),
        authority_source_url=str(data["authority_source_url"]),
        authority_rank=int(data["authority_rank"]),
        hypotheses=tuple(
            ProgramHypothesis(
                id=str(h["id"]),
                question=str(h["question"]),
                claim_to_test=str(h["claim_to_test"]),
            )
            for h in data.get("hypotheses", [])
        ),
        triggered_by=_TRIGGERS[str(trigger)],
        air_district=(str(data["air_district"]) if data.get("air_district") else None),
    )


def _load_program_registry() -> tuple[ProgramRegistryEntry, ...]:
    loaded: list[tuple[int, str, ProgramRegistryEntry]] = []
    for path in _SKILLS_ROOT.glob("*/program.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        order = int(data.get("order", 10_000))
        loaded.append((order, str(data.get("id", path.parent.name)), _entry_from_data(data, path)))
    # Deterministic, stable order: declared `order` first, then id as a tiebreak.
    loaded.sort(key=lambda item: (item[0], item[1]))
    return tuple(entry for _, _, entry in loaded)


PROGRAM_REGISTRY: tuple[ProgramRegistryEntry, ...] = _load_program_registry()


def all_programs() -> tuple[ProgramRegistryEntry, ...]:
    return PROGRAM_REGISTRY


def programs_for_family(family: str) -> tuple[ProgramRegistryEntry, ...]:
    return tuple(program for program in PROGRAM_REGISTRY if program.family == family)


def skill_for_hypothesis(hypothesis_id: str) -> str | None:
    """The canonical law-code skill id for a hypothesis: the program that owns it.
    The program id IS the skill folder name under src/lib/research/skills/<id>/SKILL.md."""
    for program in PROGRAM_REGISTRY:
        if any(h.id == hypothesis_id for h in program.hypotheses):
            return program.id
    return None
