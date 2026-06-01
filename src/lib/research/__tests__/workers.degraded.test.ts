import { afterEach, describe, expect, it } from "vitest";
import { runLocalResearchPool } from "../workers";
import { planResearch } from "../planner";
import { installFakeResearch, groundedBundle } from "@/test/researchTransport";
import type { ScopePack } from "../types";

function plan() {
  const scope: ScopePack = {
    run_id: "run_test",
    facility: { address: "X", jurisdiction_stack: [], county: null, city: null, naics: "323111", sic: null },
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

describe("runLocalResearchPool — single real path, fails closed", () => {
  let cleanup: (() => void) | null = null;
  afterEach(() => {
    cleanup?.();
    cleanup = null;
    delete process.env.MODAL_RESEARCH_ENDPOINT;
    delete process.env.MODAL_RESEARCH_TOKEN;
  });

  it("no backend configured -> FAILS CLOSED: one needs_review bundle per task, no canned data", async () => {
    delete process.env.MODAL_RESEARCH_ENDPOINT;
    delete process.env.MODAL_RESEARCH_TOKEN;
    const p = plan();
    const result = await runLocalResearchPool(p.research_tasks, p.research_graph);
    expect(result.degraded?.reason).toMatch(/not configured/i);
    expect(result.bundles.length).toBe(p.research_tasks.length);
    for (const bundle of result.bundles) {
      expect(bundle.researcher_conclusion).toBe("needs_review");
      expect(bundle.sources).toEqual([]);
    }
  });

  it("drives the real pool via injected transport (no fixture codepath)", async () => {
    cleanup = installFakeResearch((hid) => groundedBundle(hid));
    const p = plan();
    const result = await runLocalResearchPool(p.research_tasks, p.research_graph);
    expect(result.degraded).toBeUndefined();
    expect(result.bundles.length).toBe(p.research_tasks.length);
    // Every bundle came back grounded from the (faked) real transport.
    for (const bundle of result.bundles) {
      expect(bundle.sources[0].quote.length).toBeGreaterThan(0);
    }
  });
});
