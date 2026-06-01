import { afterEach, describe, expect, it } from "vitest";
import { runLocalResearchPool } from "../workers";
import { planResearch } from "../planner";
import type { ScopePack } from "../types";

function plan() {
  const scope: ScopePack = {
    run_id: "run_test",
    facility: { address: "X", jurisdiction_stack: [], naics: "323111", sic: null },
    project_change: {
      description: "test",
      equipment: [{ kind: "coating_booth", description: "booth" }],
      chemicals: [{ name: "solvent", quantity: 60, unit: "gal", hazard: "flammable" }],
      waste_streams: [],
      disturbance_acres: null,
      process_discharge: null,
    },
    missing_facts: [],
    assumptions: [],
  };
  return planResearch(scope);
}

describe("runLocalResearchPool — production fails closed, fixtures are opt-in", () => {
  afterEach(() => {
    delete process.env.RESEARCH_MODE;
    delete process.env.MODAL_RESEARCH_ENDPOINT;
    delete process.env.MODAL_RESEARCH_TOKEN;
  });

  it("live mode with no backend FAILS CLOSED: one needs_review bundle per task, no fixtures", async () => {
    process.env.RESEARCH_MODE = "live"; // endpoint env unset -> researchPool reports degraded
    const p = plan();
    const result = await runLocalResearchPool(p.research_tasks, p.research_graph);
    expect(result.degraded?.reason).toMatch(/not configured/i);
    expect(result.bundles.length).toBe(p.research_tasks.length);
    // No canned data: every fail-closed bundle is needs_review with no source.
    for (const bundle of result.bundles) {
      expect(bundle.researcher_conclusion).toBe("needs_review");
      expect(bundle.sources).toEqual([]);
    }
  });

  it("fixture mode (explicit opt-in) returns deterministic bundles with no degraded flag", async () => {
    process.env.RESEARCH_MODE = "fixture";
    const p = plan();
    const result = await runLocalResearchPool(p.research_tasks, p.research_graph);
    expect(result.degraded).toBeUndefined();
    expect(result.bundles.length).toBe(p.research_tasks.length);
  });
});
