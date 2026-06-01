import { describe, it, expect } from "vitest";
import { INTAKE_SYSTEM_PROMPT } from "../prompt";

describe("deep intake prompt", () => {
  it("probes the dimensions that unlock open-ended families", () => {
    const p = INTAKE_SYSTEM_PROMPT.toLowerCase();
    expect(p).toMatch(/building|occupancy|fire/);
    expect(p).toMatch(/ceqa|discretionary|environmental review/);
    expect(p).toMatch(/square footage|land|zoning/);
  });
});
