import { describe, expect, it } from "vitest";
import { resolveJurisdictionSkills, jurisdictionSkillId } from "../jurisdictionSkills";

const ALL_58_COUNTIES = [
  "Alameda", "Alpine", "Amador", "Butte", "Calaveras", "Colusa", "Contra Costa", "Del Norte",
  "El Dorado", "Fresno", "Glenn", "Humboldt", "Imperial", "Inyo", "Kern", "Kings", "Lake",
  "Lassen", "Los Angeles", "Madera", "Marin", "Mariposa", "Mendocino", "Merced", "Modoc", "Mono",
  "Monterey", "Napa", "Nevada", "Orange", "Placer", "Plumas", "Riverside", "Sacramento",
  "San Benito", "San Bernardino", "San Diego", "San Francisco", "San Joaquin", "San Luis Obispo",
  "San Mateo", "Santa Barbara", "Santa Clara", "Santa Cruz", "Shasta", "Sierra", "Siskiyou",
  "Solano", "Sonoma", "Stanislaus", "Sutter", "Tehama", "Trinity", "Tulare", "Tuolumne",
  "Ventura", "Yolo", "Yuba",
];

describe("county/city jurisdiction skill tree", () => {
  it("resolves county-level skill when only county is known", () => {
    const r = resolveJurisdictionSkills({ county: "Los Angeles" });
    expect(r.county?.id).toBe("los-angeles-county");
    expect(r.county?.content).toContain("Health Hazardous Materials Division");
    expect(r.city).toBeNull();
  });

  it("resolves city-level skill when city is known", () => {
    const r = resolveJurisdictionSkills({ county: "Los Angeles", city: "Vernon" });
    expect(r.city?.id).toBe("los-angeles-county/city-of-vernon");
    // The verified gotcha: Vernon's fire AHJ is LA County Fire since 2020.
    expect(r.city?.content).toContain("LA County Fire");
  });

  it("reports a gap (not a guess) for a county/city not yet researched", () => {
    // Fictional names so this stays a gap even as every real CA county gets researched.
    const r = resolveJurisdictionSkills({ county: "Nowhere", city: "Faketown" });
    expect(r.county).toBeNull();
    expect(r.city).toBeNull();
    expect(r.gaps).toContain("county:nowhere-county");
    expect(r.gaps).toContain("city:nowhere-county/city-of-faketown");
  });

  it("normalizes names to folder ids", () => {
    expect(jurisdictionSkillId("Los Angeles")).toBe("los-angeles-county");
    expect(jurisdictionSkillId("Los Angeles", "Long Beach")).toBe("los-angeles-county/city-of-long-beach");
  });

  // Regression guard for the researched coverage: each county below has a real
  // verified JURISDICTION.md, so resolution must find it (no county gap) and
  // carry the captured gotcha. Guards against an accidental rename/deletion.
  it.each([
    ["Orange", undefined, "Anaheim"],
    ["Riverside", undefined, "CAL FIRE"],
    ["San Bernardino", undefined, "Victorville"],
    ["Alameda", undefined, "decertified"],
    ["Santa Clara", undefined, "FOUR CUPAs"],
    ["Sacramento", undefined, "does NOT run its own CUPA"],
    ["Fresno", undefined, "does NOT run its own CUPA"],
    ["Ventura", undefined, "Participating Agency"],
    ["Kern", undefined, "Bakersfield"],
    ["Contra Costa", undefined, "Industrial Safety Ordinance"],
  ] as const)("resolves researched county %s with its verified gotcha", (county, city, marker) => {
    const r = resolveJurisdictionSkills({ county, ...(city ? { city } : {}) });
    expect(r.county, `${county} county skill missing`).not.toBeNull();
    expect(r.county?.content).toContain(marker);
    expect(r.gaps.some((g) => g.startsWith("county:"))).toBe(false);
  });

  it.each([
    ["Orange", "Anaheim", "only full standalone CUPA"],
    ["Alameda", "Berkeley", "Toxics Management Division"],
    ["Alameda", "Oakland", "decertified"],
    ["Santa Clara", "San José", "does **NOT** run its own CUPA"],
    ["Kern", "Bakersfield", "its own CUPA"],
    ["Ventura", "Oxnard", "own full CUPA"],
    ["Ventura", "Ventura", "Participating Agency"],
    ["Ventura", "Fillmore", "its OWN municipal department"],
    ["Ventura", "Santa Paula", "until **2018**"],
    ["Ventura", "Port Hueneme", "Naval Base Ventura County"],
  ] as const)("resolves researched city %s/%s with its verified gotcha", (county, city, marker) => {
    const r = resolveJurisdictionSkills({ county, city });
    expect(r.city, `${city} city skill missing`).not.toBeNull();
    expect(r.city?.content).toContain(marker);
    expect(r.gaps.some((g) => g.startsWith("city:"))).toBe(false);
  });

  // Full statewide coverage: every one of the 58 CA counties now resolves to a
  // real researched skill folder — no county-level gap anywhere in the state.
  it.each(ALL_58_COUNTIES)("resolves CA county %s with a real skill (no county gap)", (county) => {
    const r = resolveJurisdictionSkills({ county });
    expect(r.county, `${county} county skill missing`).not.toBeNull();
    expect(r.gaps.some((g) => g.startsWith("county:"))).toBe(false);
  });

  // All 10 incorporated Ventura County cities are now researched (no city gap).
  it.each([
    "Camarillo", "Fillmore", "Moorpark", "Ojai", "Oxnard",
    "Port Hueneme", "Santa Paula", "Simi Valley", "Thousand Oaks", "Ventura",
  ])("resolves Ventura County city %s with no gap", (city) => {
    const r = resolveJurisdictionSkills({ county: "Ventura", city });
    expect(r.city, `${city} skill missing`).not.toBeNull();
    expect(r.gaps).toEqual([]);
  });
});
