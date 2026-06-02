import { describe, expect, it } from "vitest";
import { deriveSandboxTiles } from "@/lib/ui/sandboxState";
import type { ResearchRun } from "@/lib/research/types";

const run: ResearchRun = {
  run_id: "run_sandbox",
  status: "done",
  project_facts: {},
  jurisdiction_stack: [],
  scope_pack: {} as never,
  coverage_family_statuses: [
    { id: "cf-air", family: "air", status: "active", reason: "air equipment", project_facts_considered: [], missing_facts: [] },
    { id: "cf-hazmat", family: "hazmat", status: "active", reason: "hazmat storage", project_facts_considered: [], missing_facts: [] },
    { id: "cf-waste", family: "waste", status: "out_of_scope", reason: "no waste stream", project_facts_considered: [], missing_facts: [] },
  ],
  regulatory_angles: [],
  research_graph: [
    { id: "H-AIR-201", angle_id: "A-AIR", family: "air", question: "Does air permitting apply?", required_facts: [], expected_source_type: "regulation", success_criteria: [], dependencies: [] },
    { id: "H-HAZMAT-HMBP", angle_id: "A-HAZMAT", family: "hazmat", question: "Does HMBP apply?", required_facts: [], expected_source_type: "agency_guidance", success_criteria: [], dependencies: [] },
  ],
  research_tasks: [
    { task_id: "T-AIR-201", hypothesis_id: "H-AIR-201", assigned_agent: "air_researcher", allowed_tools: [], blocked_tools: [], budget: { max_sources: 1, max_runtime_seconds: 1, max_model_calls: 1 } },
    { task_id: "T-HAZMAT-HMBP", hypothesis_id: "H-HAZMAT-HMBP", assigned_agent: "hazmat_researcher", allowed_tools: [], blocked_tools: [], budget: { max_sources: 1, max_runtime_seconds: 1, max_model_calls: 1 } },
  ],
  evidence_bundles: [],
  verification_verdicts: [
    { hypothesis_id: "H-AIR-201", verdict: "pass", checks: {}, confidence: 0.94, repair_tickets: [] },
    { hypothesis_id: "H-HAZMAT-HMBP", verdict: "needs_review", checks: {}, confidence: 0.5, repair_tickets: [] },
  ],
  repair_tickets: [
    { ticket_id: "ticket-air", hypothesis_id: "H-AIR-201", failure_type: "grounding_failed", failed_check: "grounding", observed_problem: "quote mismatch", repair_action: "retry source extraction", max_attempts_remaining: 0 },
  ],
  memory_updates: [],
  determinations: [],
  trace_events: [
    { id: "fanout-running", run_id: "run_sandbox", ts: "1", actor: "research_pool", phase: "fanout", status: "running", message: "" },
    { id: "fanout-done", run_id: "run_sandbox", ts: "2", actor: "research_pool", phase: "fanout", status: "done", message: "" },
    { id: "verification-failed", run_id: "run_sandbox", ts: "3", actor: "verifier", phase: "verification", status: "failed", message: "", artifact_id: "H-AIR-201" },
    { id: "repair-done", run_id: "run_sandbox", ts: "4", actor: "verifier", phase: "repair_verification", status: "done", message: "", artifact_id: "H-AIR-201" },
    { id: "matrix-done", run_id: "run_sandbox", ts: "5", actor: "synthesis_agent", phase: "matrix", status: "done", message: "" },
  ],
  report_markdown: "",
};

function ids(...eventIds: string[]) {
  return new Set(eventIds);
}

describe("deriveSandboxTiles", () => {
  it("starts every active worker tile as queued before replay", () => {
    const tiles = deriveSandboxTiles(run, new Set());
    const active = tiles.filter((tile) => tile.active);
    expect(active).toHaveLength(run.research_tasks.length);
    expect(active.every((tile) => tile.status === "queued")).toBe(true);
  });

  it("shows workers fetching once fanout is running but not done", () => {
    const tiles = deriveSandboxTiles(run, ids("fanout-running"));
    expect(tiles.some((tile) => tile.active && tile.status === "fetching")).toBe(true);
  });

  it("resolves every active tile to a terminal status when fully replayed", () => {
    const all = ids(...run.trace_events.map((event) => event.id));
    const tiles = deriveSandboxTiles(run, all);
    const terminal = ["verified", "repaired", "needs_review", "failed"];
    expect(tiles.filter((tile) => tile.active).every((tile) => terminal.includes(tile.status))).toBe(true);
  });

  it("marks a repaired hypothesis tile as repaired when fully replayed", () => {
    const all = ids(...run.trace_events.map((event) => event.id));
    const tiles = deriveSandboxTiles(run, all);
    expect(tiles.find((tile) => tile.id === "T-AIR-201")?.status).toBe("repaired");
  });

  it("includes muted tiles for coverage families with no worker", () => {
    const tiles = deriveSandboxTiles(run, new Set());
    const muted = tiles.filter((tile) => !tile.active);
    const familiesWithTask = new Set(
      run.research_tasks.map((task) => run.research_graph.find((hypothesis) => hypothesis.id === task.hypothesis_id)?.family),
    );
    expect(muted.every((tile) => !familiesWithTask.has(tile.family))).toBe(true);
  });
});
