import { describe, expect, it } from "vitest";
import { planResearch } from "../planner";
import { seededConstructionScope } from "../fixtures/scenarios";
import type { ScopePack } from "../types";

// A scope with NO emitting equipment, no chemicals — air would normally be out_of_scope.
const noEquipmentScope: ScopePack = seededConstructionScope("run_test", "construction only");

describe("planResearch air activation", () => {
  it("normalizes equipment kind so 'coating booth' (live LLM output) activates air", () => {
    const scope: ScopePack = {
      ...noEquipmentScope,
      project_change: {
        ...noEquipmentScope.project_change,
        equipment: [{ kind: "coating booth", description: "new coating booth" }],
      },
    };

    const plan = planResearch(scope);

    const air = plan.coverage_family_statuses.find((c) => c.family === "air");
    expect(air?.status).toBe("active");
    expect(plan.research_graph.map((h) => h.id)).toContain("H-AIR-201");
  });

  it("activates air when an SDS review flags voc_air_emissions, even with no equipment", () => {
    // SDS-driven: no equipment in scope, but the SDS handoff flagged air.
    const plan = planResearch(noEquipmentScope, new Set(["air"] as const));

    const air = plan.coverage_family_statuses.find((c) => c.family === "air");
    expect(air?.status).toBe("active");
    expect(air?.reason.toLowerCase()).toContain("sds");
    expect(plan.research_graph.map((h) => h.id)).toContain("H-AIR-VOC");
  });

  it("leaves air out_of_scope when neither equipment nor SDS flags it", () => {
    const plan = planResearch(noEquipmentScope);
    const air = plan.coverage_family_statuses.find((c) => c.family === "air");
    expect(air?.status).toBe("out_of_scope");
  });
});
