import { describe, expect, it } from "vitest";
import { resolveJurisdictionSkills, jurisdictionSkillId } from "../jurisdictionSkills";

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
    const r = resolveJurisdictionSkills({ county: "Fresno", city: "Clovis" });
    expect(r.county).toBeNull();
    expect(r.city).toBeNull();
    expect(r.gaps).toContain("county:fresno-county");
    expect(r.gaps).toContain("city:fresno-county/city-of-clovis");
  });

  it("normalizes names to folder ids", () => {
    expect(jurisdictionSkillId("Los Angeles")).toBe("los-angeles-county");
    expect(jurisdictionSkillId("Los Angeles", "Long Beach")).toBe("los-angeles-county/city-of-long-beach");
  });
});
