// Orchestrates the full local-jurisdiction resolution for a facility location.
//
// Given a county (and optional city), it composes the three resolvers into one
// answer the run pipeline can act on:
//   - resolveAirDistrict   -> which of the 35 air districts cover the county
//   - resolveJurisdictionSkills -> the researched county/city skill folders
//   - (resolveWaterBoard folds in here once the county->region map lands)
//
// Every uncertainty is surfaced as an explicit gap, never papered over with a
// guessed authority. A county that spans multiple air districts can't be pinned
// on the county name alone (needs sub-county geometry) -> that's a gap. A county
// or city with no researched skill folder -> that's a gap. An unknown county ->
// that's a gap and an empty stack. The run treats gaps as fail-closed missing
// facts, so the report says "needs review" instead of citing the wrong agency.

import { resolveAirDistrict, resolveWaterBoard, type AirDistrict, type RegionalWaterBoard } from "./jurisdictionRegistry";
import { resolveJurisdictionSkills, type JurisdictionSkill } from "./jurisdictionSkills";
import type { ScopePack } from "./types";

export type ResolvedJurisdiction = {
  county: string | null;
  city: string | null;
  airDistricts: AirDistrict[];
  airNeedsGeometry: boolean;
  waterBoards: RegionalWaterBoard[];
  waterNeedsGeometry: boolean;
  countySkill: JurisdictionSkill | null;
  citySkill: JurisdictionSkill | null;
  // Human-readable resolved authority names for ScopePack.facility.jurisdiction_stack.
  stack: string[];
  // Honest gaps: unknown county, county spans multiple air districts (needs
  // geometry), or an unresearched county/city skill folder.
  gaps: string[];
};

export function resolveJurisdiction(facility: { county: string | null; city: string | null }): ResolvedJurisdiction {
  const county = facility.county;
  const city = facility.city;

  if (!county) {
    return {
      county: null,
      city,
      airDistricts: [],
      airNeedsGeometry: false,
      waterBoards: [],
      waterNeedsGeometry: false,
      countySkill: null,
      citySkill: null,
      stack: [],
      gaps: ["location:county_unknown"],
    };
  }

  const air = resolveAirDistrict(county);
  const water = resolveWaterBoard(county);
  const skills = resolveJurisdictionSkills({ county, ...(city ? { city } : {}) });

  const gaps: string[] = [...skills.gaps];
  // More than one district/region covers the county -> can't resolve on the
  // county name alone. Don't pick one arbitrarily; flag that sub-county geometry
  // is needed. Zero matches -> flag the missing authority.
  if (air.needsGeometry) gaps.push(`air_geometry:${county}`);
  if (air.districts.length === 0) gaps.push(`air_district:${county}`);
  if (water.needsGeometry) gaps.push(`water_geometry:${county}`);
  if (water.boards.length === 0) gaps.push(`water_board:${county}`);

  const stack: string[] = [];
  for (const d of air.districts) stack.push(d.name);
  for (const b of water.boards) stack.push(b.name);
  if (skills.county) stack.push(`${county} County local programs (CUPA / fire / building)`);
  if (skills.city && city) stack.push(`${city} local programs`);

  return {
    county,
    city,
    airDistricts: air.districts,
    airNeedsGeometry: air.needsGeometry,
    waterBoards: water.boards,
    waterNeedsGeometry: water.needsGeometry,
    countySkill: skills.county,
    citySkill: skills.city,
    stack,
    gaps,
  };
}

// Which coverage dimensions a jurisdiction gap blocks. A gap means we don't know
// the controlling authority, so any determination depending on it is unsafe.
function blocksForGap(gap: string): string[] {
  if (gap.startsWith("air_")) return ["air"];
  if (gap.startsWith("water_board")) return ["stormwater", "wastewater"];
  if (gap.startsWith("location:")) return ["air", "stormwater", "hazmat", "waste", "wastewater"];
  // county:/city: skill folders carry the local CUPA / fire / building authority.
  return ["hazmat", "waste"];
}

// Fold jurisdiction resolution into a ScopePack (pure — returns a new pack):
//  - when a real resolution exists, replace the conservative default
//    jurisdiction_stack with the actual resolved authorities;
//  - turn every resolution gap into a fail-closed missing_fact so the run
//    surfaces "needs review" rather than citing a guessed agency.
export function applyJurisdictionToScope(scope: ScopePack): ScopePack {
  const resolved = resolveJurisdiction(scope.facility);

  const jurisdiction_stack =
    resolved.stack.length > 0 ? resolved.stack : scope.facility.jurisdiction_stack;

  const missing_facts = scope.missing_facts.map((m) => ({ ...m, blocks: [...m.blocks] }));
  for (const gap of resolved.gaps) {
    const field = `jurisdiction.${gap}`;
    if (missing_facts.some((m) => m.field === field)) continue;
    missing_facts.push({
      field,
      why_needed:
        "Local jurisdiction could not be resolved to a single controlling authority; " +
        "the responsible agency and its adopted rules must be confirmed before any determination.",
      blocks: blocksForGap(gap),
    });
  }

  return {
    ...scope,
    facility: { ...scope.facility, jurisdiction_stack },
    missing_facts,
  };
}
