from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata


JURISDICTIONS_ROOT = (
    Path(__file__).resolve().parents[1] / "lib" / "research" / "skills" / "jurisdictions"
)


@dataclass(frozen=True)
class JurisdictionSkill:
    id: str
    content: str


@dataclass(frozen=True)
class JurisdictionSkillsResolution:
    county: JurisdictionSkill | None
    city: JurisdictionSkill | None
    gaps: tuple[str, ...]


def _deaccent(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_county_name(county: str) -> str:
    return re.sub(r"\s+county\s*$", "", county.strip(), flags=re.IGNORECASE)


def _slug_part(value: str) -> str:
    deaccented = _deaccent(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", deaccented).strip("-")


def _slug_county(county: str) -> str:
    return f"{_slug_part(normalize_county_name(county))}-county"


def _slug_city(city: str) -> str:
    return f"city-of-{_slug_part(city)}"


def jurisdiction_skill_id(county: str, city: str | None = None) -> str:
    county_id = _slug_county(county)
    if city:
        return f"{county_id}/{_slug_city(city)}"
    return county_id


def _read_skill(skill_id: str) -> JurisdictionSkill | None:
    path = JURISDICTIONS_ROOT / skill_id / "JURISDICTION.md"
    if not path.exists():
        return None
    return JurisdictionSkill(id=skill_id, content=path.read_text(encoding="utf-8"))


def resolve_jurisdiction_skills(
    loc: dict[str, str | None],
) -> JurisdictionSkillsResolution:
    county_value = loc["county"]
    county_id = _slug_county(county_value)
    county = _read_skill(county_id)
    gaps: list[str] = []
    if county is None:
        gaps.append(f"county:{county_id}")

    city: JurisdictionSkill | None = None
    city_value = loc.get("city")
    if city_value:
        city_id = f"{county_id}/{_slug_city(city_value)}"
        city = _read_skill(city_id)
        if city is None:
            gaps.append(f"city:{city_id}")

    return JurisdictionSkillsResolution(county=county, city=city, gaps=tuple(gaps))
