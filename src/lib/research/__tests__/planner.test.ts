import { describe, expect, it } from "vitest";
import { planResearch, taskForHypothesis } from "../planner";
import type { ScopePack } from "../types";
import { scopePackFromFacts } from "../scope";

describe("researcher budget", () => {
  it("gives each research task at least 4 model calls for the agentic loop", () => {
    const scope: ScopePack = {
      run_id: "test_run",
      facility: { address: "X", jurisdiction_stack: [], county: null, city: null, naics: null, sic: null },
      project_change: {
        description: "test project",
        equipment: [{ kind: "coating_booth", description: "booth" }],
        chemicals: [{ name: "solvent", quantity: 60, unit: "gal", hazard: "flammable" }],
        waste_streams: [],
        disturbance_acres: null,
        process_discharge: null,
      },
      missing_facts: [],
      assumptions: [],
    };
    const plan = planResearch(scope);
    expect(plan.research_tasks.length).toBeGreaterThan(0);
    expect(plan.research_tasks.every((t) => t.budget.max_model_calls >= 4)).toBe(true);
  });

  it("exposes taskForHypothesis so the orchestrator can build tasks for proposed hypotheses", () => {
    const task = taskForHypothesis({
      id: "H-DISCOVER-1", angle_id: "A-DISCOVER-1", family: "fire_code",
      question: "q", claim_to_test: "c", required_facts: [],
      expected_source_type: "agency_guidance", success_criteria: [], dependencies: [],
    });
    expect(task.hypothesis_id).toBe("H-DISCOVER-1");
    expect(task.assigned_agent).toBe("fire_code_researcher");
    expect(task.allowed_tools.length).toBeGreaterThan(0);
  });
});

describe("planResearch — count varies with facts", () => {
  it("equipment-only project activates air but not hazmat/waste", () => {
    const scope = scopePackFromFacts({ equipment: [{ kind: "oven" }], naics: "323111" }, "r1", "two ovens");
    const plan = planResearch(scope);
    const families = new Set(plan.research_graph.map((h) => h.family));
    expect(families.has("air")).toBe(true);
    expect(plan.research_graph.some((h) => h.id === "H-HAZMAT-HMBP")).toBe(false);
    expect(plan.research_graph.some((h) => h.id === "H-WASTE-GENERATOR")).toBe(false);
  });

  it("a richer project spawns strictly more hypotheses than the equipment-only one", () => {
    const lean = planResearch(scopePackFromFacts({ equipment: [{ kind: "oven" }], naics: "323111" }, "r1", "ovens"));
    const rich = planResearch(
      scopePackFromFacts(
        {
          equipment: [{ kind: "coating booth" }],
          chemicals: [{ name: "solvent", quantity: 60, unit: "gallons" }],
          waste_streams: [{ description: "spent solvent", kg_per_month: 10 }],
          naics: "323111",
          process_discharge: true,
        },
        "r2",
        "complex",
      ),
    );
    expect(rich.research_graph.length).toBeGreaterThan(lean.research_graph.length);
    expect(rich.research_graph.some((h) => h.id === "H-HAZMAT-HMBP")).toBe(true);
  });
});
