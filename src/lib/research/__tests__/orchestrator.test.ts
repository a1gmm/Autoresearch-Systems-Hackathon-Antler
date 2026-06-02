import { describe, it, expect } from "vitest";
import { orchestrateResearchPlan, type OrchestratorLlmFn } from "../orchestrator";
import { planResearch } from "../planner";
import type { ScopePack } from "../types";

function scope(): ScopePack {
  return {
    run_id: "orch-test",
    facility: { address: "x", jurisdiction_stack: ["SCAQMD"], county: null, city: null, naics: null, sic: null },
    project_change: {
      description: "Adds a coating booth and stores 60 gallons of flammable solvent.",
      equipment: [{ kind: "coating_booth", description: "" }],
      chemicals: [{ name: "solvent", quantity: 60, unit: "gal" }],
      waste_streams: [], disturbance_acres: null, process_discharge: false,
    },
    missing_facts: [], assumptions: [],
  };
}

const submitsFireCode: OrchestratorLlmFn = async (messages) => {
  const alreadyRead = messages.some((m) => m.role === "tool" && m.name === "read_skill");
  if (!alreadyRead) {
    return { content: null, tool_calls: [{ id: "c1", name: "read_skill", arguments: { skill_id: "scaqmd-air" } }] };
  }
  return {
    content: null,
    tool_calls: [{
      id: "c2", name: "submit_research_plan",
      arguments: { proposals: [{ family: "fire_code", novel_regime: false, rationale: "Spray booth may trigger fire-code permit",
        hypotheses: [{ question: "Does the spray booth require a fire-code permit?" }] }] },
    }],
  };
};

const proposesNothing: OrchestratorLlmFn = async () => ({ content: null, tool_calls: [] });

describe("orchestrateResearchPlan", () => {
  it("adds an open-ended family beyond the deterministic 5 as a needs_review discovery candidate", async () => {
    const baseline = planResearch(scope());
    const plan = await orchestrateResearchPlan(scope(), { llmFn: submitsFireCode });
    expect(plan.research_graph.length).toBe(baseline.research_graph.length + 1);
    const added = plan.research_graph.find((h) => h.family === "fire_code");
    expect(added).toBeDefined();
    expect(added?.id).toMatch(/^H-DISCOVER-/);
    expect(plan.coverage_family_statuses.some((s) => s.family === "fire_code" && s.status === "discovery_candidate")).toBe(true);
  });

  it("falls back to the deterministic planner when the LLM proposes nothing", async () => {
    const baseline = planResearch(scope());
    const plan = await orchestrateResearchPlan(scope(), { llmFn: proposesNothing });
    expect(plan.research_graph.map((h) => h.id).sort()).toEqual(baseline.research_graph.map((h) => h.id).sort());
  });

  it("dispatches read_skill through the injected reader", async () => {
    const seen: string[] = [];
    const plan = await orchestrateResearchPlan(scope(), {
      llmFn: submitsFireCode,
      skillReader: (id) => { seen.push(id); return `# ${id}`; },
    });
    expect(seen).toContain("scaqmd-air");
    expect(plan.research_graph.length).toBeGreaterThan(0);
  });
});
