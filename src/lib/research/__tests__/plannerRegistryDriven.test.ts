import { describe, expect, it } from "vitest";
import { planResearch } from "../planner";
import { PROGRAM_REGISTRY } from "../programRegistry";
import type { ScopePack } from "../types";

function scope(over: Partial<ScopePack["project_change"]> = {}, facility: Partial<ScopePack["facility"]> = {}): ScopePack {
  return {
    run_id: "r",
    facility: { address: "X", jurisdiction_stack: [], county: null, city: null, naics: null, sic: null, ...facility },
    project_change: { description: "d", equipment: [], chemicals: [], waste_streams: [], disturbance_acres: null, process_discharge: null, ...over },
    missing_facts: [],
    assumptions: [],
  };
}

describe("planResearch is registry-driven (no hardcoded angle pool)", () => {
  it("emits exactly the hypotheses of the programs whose triggers fire", () => {
    // Equipment only -> only the air programs (triggeredBy hasEquipment) fire.
    const plan = planResearch(scope({ equipment: [{ kind: "oven", description: "oven" }] }));
    const ids = new Set(plan.research_graph.map((h) => h.id));

    const expectedAir = new Set(
      PROGRAM_REGISTRY.filter((p) => p.family === "air").flatMap((p) => p.hypotheses.map((h) => h.id))
    );
    for (const id of expectedAir) expect(ids.has(id)).toBe(true);
    // No hazmat or hazardous-waste-generator hypotheses (no chemicals/waste in scope).
    expect(ids.has("H-HAZMAT-HMBP")).toBe(false);
    expect(ids.has("H-WASTE-GENERATOR")).toBe(false);
  });

  it("every emitted hypothesis traces back to a real registry program", () => {
    const plan = planResearch(
      scope(
        { equipment: [{ kind: "booth", description: "b" }], chemicals: [{ name: "solvent", quantity: 60, unit: "gal" }], waste_streams: [{ description: "spent", kg_per_month: 5 }], process_discharge: true },
        { naics: "323111" }
      )
    );
    const registryIds = new Set(PROGRAM_REGISTRY.flatMap((p) => p.hypotheses.map((h) => h.id)));
    for (const h of plan.research_graph) {
      expect(registryIds.has(h.id), `${h.id} is not in the registry`).toBe(true);
      // Each hypothesis's angle id points at its program (A-<program.id>).
      expect(h.angle_id.startsWith("A-")).toBe(true);
    }
  });

  it("a richer scope yields strictly more hypotheses (fact-driven, not fixed)", () => {
    const lean = planResearch(scope({ equipment: [{ kind: "oven", description: "o" }] }));
    const rich = planResearch(
      scope(
        { equipment: [{ kind: "booth", description: "b" }], chemicals: [{ name: "solvent", quantity: 60, unit: "gal" }], waste_streams: [{ description: "spent", kg_per_month: 5 }], process_discharge: true },
        { naics: "323111" }
      )
    );
    expect(rich.research_graph.length).toBeGreaterThan(lean.research_graph.length);
  });
});
