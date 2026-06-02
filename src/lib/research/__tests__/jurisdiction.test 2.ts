import { describe, expect, it } from "vitest";
import { resolveAirDistrict, AIR_DISTRICTS, REGIONAL_WATER_BOARDS } from "../jurisdictionRegistry";

describe("jurisdiction registry", () => {
  it("has all 35 California air districts", () => {
    expect(AIR_DISTRICTS.length).toBe(35);
  });

  it("has 9 regional water boards", () => {
    expect(REGIONAL_WATER_BOARDS.length).toBe(9);
  });

  it("resolves a single-district county directly", () => {
    const r = resolveAirDistrict("San Diego");
    expect(r.districts.map((d) => d.id)).toContain("san-diego-county-apcd");
    expect(r.needsGeometry).toBe(false);
  });

  it("flags a split county (Los Angeles -> South Coast OR Antelope Valley) as needs-geometry", () => {
    const r = resolveAirDistrict("Los Angeles");
    const ids = r.districts.map((d) => d.id);
    expect(ids).toContain("south-coast-aqmd");
    expect(ids).toContain("antelope-valley-aqmd");
    expect(r.needsGeometry).toBe(true); // can't resolve on county alone
  });

  it("flags all five known split counties", () => {
    for (const county of ["Los Angeles", "San Bernardino", "Riverside", "Kern", "Sonoma", "Solano"]) {
      expect(resolveAirDistrict(county).needsGeometry, `${county} should need geometry`).toBe(true);
    }
  });

  it("every air district has an authority host", () => {
    for (const d of AIR_DISTRICTS) {
      expect(d.website.length, `${d.id} missing website`).toBeGreaterThan(0);
    }
  });

  it("returns empty (not a guess) for an unknown county", () => {
    const r = resolveAirDistrict("Nowhere");
    expect(r.districts).toEqual([]);
  });
});
