import { describe, expect, it } from "vitest";
import { emptyScope, parseScopeLive } from "../scope";
import type { ResearchRunInput } from "../types";

const input: ResearchRunInput = {
  project_description:
    "We operate a metal finishing shop, NAICS 332813, adding an anodizing line that stores 200 gallons of sulfuric acid.",
};

describe("parseScopeLive", () => {
  it("extracts facts the keyword matcher cannot, from the LLM JSON", async () => {
    // A fact-bearing extraction the deterministic keyword parser would never produce:
    // it pulls the real NAICS and the acid quantity out of free text.
    const llmFn = async () =>
      JSON.stringify({
        facility: {
          address: "Unknown metal finishing shop",
          jurisdiction_stack: ["SCAQMD"],
          naics: "332813",
          sic: null,
        },
        project_change: {
          description: "Adding an anodizing line storing sulfuric acid.",
          equipment: [{ kind: "anodizing_line", description: "new process line" }],
          chemicals: [
            { name: "sulfuric acid", quantity: 200, unit: "gallons", hazard: "corrosive" },
          ],
          waste_streams: [],
          disturbance_acres: 0,
          process_discharge: null,
        },
        missing_facts: [],
        assumptions: [],
      });

    const scope = await parseScopeLive(input, "run_test", llmFn);

    expect(scope.facility.naics).toBe("332813");
    expect(scope.project_change.chemicals[0]).toMatchObject({
      name: "sulfuric acid",
      quantity: 200,
      unit: "gallons",
    });
    expect(scope.run_id).toBe("run_test");
  });

  it("fails closed to emptyScope when the LLM returns unparseable output", async () => {
    const llmFn = async () => "not json at all";

    const scope = await parseScopeLive(input, "run_bad", llmFn);

    expect(scope).toEqual(emptyScope("run_bad", input.project_description));
    expect(scope.project_change.equipment).toEqual([]);
    expect(scope.missing_facts.length).toBeGreaterThan(0);
  });

  it("fails closed to emptyScope when the llmFn throws", async () => {
    const llmFn = async () => {
      throw new Error("no api key");
    };

    const scope = await parseScopeLive(input, "run_throw", llmFn);

    expect(scope).toEqual(emptyScope("run_throw", input.project_description));
  });
});
