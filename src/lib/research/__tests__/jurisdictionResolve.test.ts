import { describe, expect, it } from "vitest";
import { resolveJurisdiction, applyJurisdictionToScope } from "../jurisdictionResolve";
import type { ScopePack } from "../types";

function scopeWith(facility: Partial<ScopePack["facility"]>): ScopePack {
  return {
    run_id: "r",
    facility: { address: "X", jurisdiction_stack: ["SCAQMD", "California Water Boards", "Local CUPA"], county: null, city: null, naics: null, sic: null, ...facility },
    project_change: { description: "d", equipment: [], chemicals: [], waste_streams: [], disturbance_acres: null, process_discharge: null },
    missing_facts: [],
    assumptions: [],
  };
}

describe("resolveJurisdiction", () => {
  it("resolves a single-air-district county with a researched skill folder", () => {
    const r = resolveJurisdiction({ county: "San Diego", city: null });
    expect(r.airDistricts.map((d) => d.id)).toEqual(["san-diego-county-apcd"]);
    expect(r.airNeedsGeometry).toBe(false);
    expect(r.countySkill?.id).toBe("san-diego-county");
    // The resolved stack names the real authorities, not the hardcoded SCAQMD trio.
    expect(r.stack).toContain("San Diego County APCD");
    // No air-geometry or county-skill gap for a fully-resolved, single-district county.
    expect(r.gaps).not.toContain("air_geometry:San Diego");
    expect(r.gaps.some((g) => g.startsWith("county:"))).toBe(false);
  });

  it("resolves the regional water board and includes it in the stack", () => {
    const r = resolveJurisdiction({ county: "Orange", city: null });
    expect(r.waterBoards.map((b) => b.id)).toEqual(["region-8-santa-ana"]);
    expect(r.waterNeedsGeometry).toBe(false);
    expect(r.stack).toContain("Santa Ana Regional Water Quality Control Board");
  });

  it("flags water-board geometry as a gap for a multi-region county", () => {
    const r = resolveJurisdiction({ county: "Riverside", city: null });
    expect(r.waterNeedsGeometry).toBe(true);
    expect(r.gaps).toContain("water_geometry:Riverside");
  });

  it("flags air geometry as a gap when the county spans multiple districts", () => {
    const r = resolveJurisdiction({ county: "Los Angeles", city: "Vernon" });
    expect(r.airNeedsGeometry).toBe(true);
    expect(r.gaps).toContain("air_geometry:Los Angeles");
    // City skill exists for Vernon -> no city gap, and its content is carried.
    expect(r.citySkill?.id).toBe("los-angeles-county/city-of-vernon");
    expect(r.gaps.some((g) => g.startsWith("city:"))).toBe(false);
  });

  it("reports an unresearched county/city as honest gaps (never a guessed authority)", () => {
    const r = resolveJurisdiction({ county: "Mendocino", city: "Fort Bragg" });
    // Mendocino is a real air district county, but its local skill folder is not researched yet.
    expect(r.gaps).toContain("county:mendocino-county");
    expect(r.gaps).toContain("city:mendocino-county/city-of-fort-bragg");
    expect(r.countySkill).toBeNull();
  });

  it("fails closed when the county is unknown (no guessed jurisdiction)", () => {
    const r = resolveJurisdiction({ county: null, city: null });
    expect(r.airDistricts).toEqual([]);
    expect(r.countySkill).toBeNull();
    expect(r.gaps).toContain("location:county_unknown");
    expect(r.stack).toEqual([]);
  });
});

describe("applyJurisdictionToScope", () => {
  it("replaces the default stack with the real resolved authorities when county is known", () => {
    const out = applyJurisdictionToScope(scopeWith({ county: "San Diego", city: null }));
    expect(out.facility.jurisdiction_stack).toContain("San Diego County APCD");
    // The hardcoded SCAQMD placeholder is gone once we have a real resolution.
    expect(out.facility.jurisdiction_stack).not.toContain("SCAQMD");
    // San Diego County spans water regions 7 and 9 -> an honest water-geometry gap,
    // never a silently-picked single board.
    expect(out.missing_facts.map((m) => m.field)).toContain("jurisdiction.water_geometry:San Diego");
  });

  it("records a fail-closed missing fact for an air-geometry gap", () => {
    const out = applyJurisdictionToScope(scopeWith({ county: "Los Angeles", city: "Vernon" }));
    const fields = out.missing_facts.map((m) => m.field);
    expect(fields).toContain("jurisdiction.air_geometry:Los Angeles");
  });

  it("flags an unknown county as a missing fact and keeps the conservative default stack", () => {
    const out = applyJurisdictionToScope(scopeWith({ county: null, city: null }));
    expect(out.missing_facts.map((m) => m.field)).toContain("jurisdiction.location:county_unknown");
    // No real resolution -> do not overwrite the default with an empty stack.
    expect(out.facility.jurisdiction_stack.length).toBeGreaterThan(0);
  });

  it("does not mutate the input scope", () => {
    const input = scopeWith({ county: "San Diego", city: null });
    const before = input.facility.jurisdiction_stack;
    applyJurisdictionToScope(input);
    expect(input.facility.jurisdiction_stack).toBe(before);
    expect(input.missing_facts).toEqual([]);
  });
});
