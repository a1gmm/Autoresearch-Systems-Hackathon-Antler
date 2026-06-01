import { describe, it, expect } from "vitest";
import { expectedProgramsForScope } from "../completeness";
import { planResearch } from "../planner";
import { orchestrateResearchPlan } from "../orchestrator";
import type { ScopePack } from "../types";

function scopeFrom(pc: Partial<ScopePack["project_change"]>): ScopePack {
  return {
    run_id: "corpus",
    facility: { address: "x", jurisdiction_stack: ["SCAQMD"], naics: null, sic: null },
    project_change: { description: "", equipment: [], chemicals: [], waste_streams: [], disturbance_acres: null, process_discharge: false, ...pc },
    missing_facts: [], assumptions: [],
  };
}

// Recall = fraction of expected programs that some proposed hypothesis directly covers
// (via the program's hypothesis_ids). 1.0 = nothing silently dropped.
function directRecall(proposedHypothesisIds: Set<string>, scope: ScopePack): number {
  const expected = expectedProgramsForScope(scope);
  if (expected.length === 0) return 1;
  const covered = expected.filter((p) => p.hypothesis_ids.some((h) => proposedHypothesisIds.has(h)));
  return covered.length / expected.length;
}

const CORPUS: Array<{ name: string; scope: ScopePack }> = [
  { name: "air + hazmat", scope: scopeFrom({ equipment: [{ kind: "coating_booth", description: "" }], chemicals: [{ name: "solvent", quantity: 60, unit: "gal" }] }) },
  { name: "waste + wastewater", scope: scopeFrom({ waste_streams: [{ description: "spent solvent", kg_per_month: 200 }], process_discharge: true }) },
  { name: "stormwater (acres)", scope: scopeFrom({ disturbance_acres: 3 }) },
  { name: "all families", scope: scopeFrom({ equipment: [{ kind: "coating_booth", description: "" }], chemicals: [{ name: "solvent", quantity: 60, unit: "gal" }], waste_streams: [{ description: "spent solvent", kg_per_month: 200 }], disturbance_acres: 3, process_discharge: true }) },
];

describe("recall-metric golden corpus", () => {
  it("the deterministic planner directly covers every expected program (recall == 1.0)", () => {
    for (const { name, scope } of CORPUS) {
      const ids = new Set(planResearch(scope).research_graph.map((h) => h.id));
      expect(directRecall(ids, scope), name).toBe(1);
    }
  });

  it("the orchestrator (no-op LLM) never lowers recall below the planner", async () => {
    for (const { name, scope } of CORPUS) {
      const plan = await orchestrateResearchPlan(scope, { llmFn: async () => ({ content: null, tool_calls: [] }) });
      expect(directRecall(new Set(plan.research_graph.map((h) => h.id)), scope), name).toBe(1);
    }
  });
});
