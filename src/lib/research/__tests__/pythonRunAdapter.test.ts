import { describe, expect, it } from "vitest";
import { toUiResearchRun } from "../pythonRunAdapter";

describe("pythonRunAdapter", () => {
  it("maps Python information requests and scenarios into UI state", () => {
    const run = toUiResearchRun({
      run_id: "run_1",
      status: "needs_information",
      information_requests: [{ field: "chemicals.quantity", question: "How many gallons?", why_needed: "threshold", blocks: ["ca-hmbp"] }],
      scenarios: [{ id: "s1", label: "expected", assumptions: [], rationale: "typical", affects: ["ca-hmbp"] }],
      determinations: [],
      trace_events: [],
      report_markdown: "",
    });
    expect(run.status).toBe("needs_information");
    expect(run.information_requests).toHaveLength(1);
    expect(run.scenarios).toHaveLength(1);
  });
});
