import { describe, it, expect, afterEach } from "vitest";
import { planRun } from "../run";

afterEach(() => { delete process.env.USE_AGENTIC_ORCHESTRATOR; });

describe("planRun orchestrator flag", () => {
  it("defaults to the deterministic planner (flag off)", async () => {
    const planned = await planRun({ project_description: "Adds a coating booth." });
    expect(planned.plan.research_graph.length).toBeGreaterThan(0);
    expect(planned.plan.research_graph.every((h) => !h.id.startsWith("H-DISCOVER-"))).toBe(true);
  });

  it("uses the orchestrator path when USE_AGENTIC_ORCHESTRATOR=1 (no key -> safe fallback to baseline)", async () => {
    process.env.USE_AGENTIC_ORCHESTRATOR = "1";
    const planned = await planRun({ project_description: "Adds a coating booth." });
    expect(planned.plan.research_graph.length).toBeGreaterThan(0);
    expect(planned.trace_events.some((e) => e.message.includes("orchestrator"))).toBe(true);
  });
});
