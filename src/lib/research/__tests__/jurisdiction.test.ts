import { describe, expect, it } from "vitest";
import { resolveAirDistrict, resolveWaterBoard, AIR_DISTRICTS, REGIONAL_WATER_BOARDS } from "../jurisdictionRegistry";

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

describe("regional water board resolution", () => {
  it("resolves a single-region county directly", () => {
    const r = resolveWaterBoard("Orange");
    expect(r.boards.map((b) => b.id)).toEqual(["region-8-santa-ana"]);
    expect(r.needsGeometry).toBe(false);
  });

  it("flags Riverside as a three-region split needing geometry", () => {
    const r = resolveWaterBoard("Riverside");
    const ids = r.boards.map((b) => b.id);
    expect(ids).toContain("region-7-colorado-river-basin");
    expect(ids).toContain("region-8-santa-ana");
    expect(ids).toContain("region-9-san-diego");
    expect(r.needsGeometry).toBe(true);
  });

  it("maps San Diego to regions 9 and 7 (per the State Board fact sheet), not region 8", () => {
    const ids = resolveWaterBoard("San Diego").boards.map((b) => b.id);
    expect(ids).toContain("region-9-san-diego");
    expect(ids).toContain("region-7-colorado-river-basin");
    expect(ids).not.toContain("region-8-santa-ana");
  });

  it("returns empty (not a guess) for an unknown county", () => {
    expect(resolveWaterBoard("Nowhere").boards).toEqual([]);
  });

  it("covers all 58 counties", () => {
    // every CA county resolves to at least one region (no silent gaps)
    const missing = COUNTY_NAMES.filter((c) => resolveWaterBoard(c).boards.length === 0);
    expect(missing).toEqual([]);
  });
});

const COUNTY_NAMES = [
  "Alameda", "Alpine", "Amador", "Butte", "Calaveras", "Colusa", "Contra Costa", "Del Norte",
  "El Dorado", "Fresno", "Glenn", "Humboldt", "Imperial", "Inyo", "Kern", "Kings", "Lake",
  "Lassen", "Los Angeles", "Madera", "Marin", "Mariposa", "Mendocino", "Merced", "Modoc", "Mono",
  "Monterey", "Napa", "Nevada", "Orange", "Placer", "Plumas", "Riverside", "Sacramento",
  "San Benito", "San Bernardino", "San Diego", "San Francisco", "San Joaquin", "San Luis Obispo",
  "San Mateo", "Santa Barbara", "Santa Clara", "Santa Cruz", "Shasta", "Sierra", "Siskiyou",
  "Solano", "Sonoma", "Stanislaus", "Sutter", "Tehama", "Trinity", "Tulare", "Tuolumne",
  "Ventura", "Yolo", "Yuba",
];
