import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { resolveScope } from "../scope";
import type { ResearchRunInput } from "../types";

const input: ResearchRunInput = {
  project_description: "Adding a coating booth and storing 60 gallons of flammable solvent.",
};

const ORIGINAL_MODE = process.env.RESEARCH_MODE;

afterEach(() => {
  if (ORIGINAL_MODE === undefined) delete process.env.RESEARCH_MODE;
  else process.env.RESEARCH_MODE = ORIGINAL_MODE;
});

describe("resolveScope", () => {
  it("uses the deterministic fixture parser in fixture mode (ignores llmFn)", async () => {
    delete process.env.RESEARCH_MODE; // defaults to fixture
    let called = false;
    const llmFn = async () => {
      called = true;
      return "{}";
    };

    const scope = await resolveScope(input, "run_fix", llmFn);

    expect(called).toBe(false);
    // Fixture path returns the seeded complex scope for this description.
    expect(scope.project_change.equipment.length).toBeGreaterThan(0);
  });

  it("uses the live extraction in live mode", async () => {
    process.env.RESEARCH_MODE = "live_modal";
    const llmFn = async () =>
      JSON.stringify({
        facility: { address: "Live shop", jurisdiction_stack: [], naics: "111111", sic: null },
        project_change: {
          description: "live",
          equipment: [],
          chemicals: [],
          waste_streams: [],
          disturbance_acres: 0,
          process_discharge: null,
        },
        missing_facts: [],
        assumptions: [],
      });

    const scope = await resolveScope(input, "run_live", llmFn);

    expect(scope.facility.naics).toBe("111111");
  });
});
