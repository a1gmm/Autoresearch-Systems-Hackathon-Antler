import { describe, it, expect } from "vitest";
import type { ResearchRun } from "@/lib/research/types";
import { toUiResearchRun } from "@/lib/research/pythonRunAdapter";
import { buildGraph } from "../graphLayout";

const minimalRun: ResearchRun = {
  run_id: "t",
  status: "done",
  project_facts: {},
  jurisdiction_stack: [],
  scope_pack: {} as never,
  coverage_family_statuses: [
    { id: "cov_hmbp", family: "hazmat", status: "active", reason: "", project_facts_considered: [], missing_facts: [] },
  ],
  regulatory_angles: [
    { id: "ang_hmbp_55", family: "hazmat", label: "55gal threshold", reason: "", triggering_facts: [], status: "active" },
  ],
  research_graph: [
    { id: "hyp_hmbp", angle_id: "ang_hmbp_55", family: "hazmat", question: "Does 60gal trigger HMBP?", required_facts: [], expected_source_type: "regulation", success_criteria: [], dependencies: [] },
  ],
  research_tasks: [
    { task_id: "task_1", hypothesis_id: "hyp_hmbp", assigned_agent: "a", allowed_tools: [], blocked_tools: [], budget: { max_sources: 1, max_runtime_seconds: 1, max_model_calls: 1 } },
  ],
  evidence_bundles: [],
  verification_verdicts: [],
  repair_tickets: [],
  memory_updates: [],
  determinations: [],
  trace_events: [
    { id: "ev_cov", run_id: "t", ts: "1", actor: "orchestrator", phase: "coverage", status: "done", message: "" },
    { id: "ev_tg", run_id: "t", ts: "2", actor: "orchestrator", phase: "task_graph", status: "done", message: "" },
  ],
  report_markdown: "",
};

describe("buildGraph", () => {
  it("returns no nodes when nothing has been replayed yet", () => {
    const { nodes, edges } = buildGraph(minimalRun, new Set());
    expect(nodes).toHaveLength(0);
    expect(edges).toHaveLength(0);
  });

  it("returns only coverage nodes after coverage event replayed", () => {
    const { nodes, edges } = buildGraph(minimalRun, new Set(["ev_cov"]));
    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("coverage");
    expect(edges).toHaveLength(0);
  });

  it("returns coverage + angle + hypothesis + task after task_graph event replayed", () => {
    const { nodes, edges } = buildGraph(minimalRun, new Set(["ev_cov", "ev_tg"]));
    expect(nodes.map((n) => n.type).sort()).toEqual(["angle", "coverage", "hypothesis", "task"]);
    expect(edges).toHaveLength(3);
  });

  it("assigns x/y positions via dagre", () => {
    const { nodes } = buildGraph(minimalRun, new Set(["ev_cov", "ev_tg"]));
    for (const n of nodes) {
      expect(typeof n.position.x).toBe("number");
      expect(typeof n.position.y).toBe("number");
    }
  });

  it("builds graph nodes from normalized Python plan trace events", () => {
    const run = toUiResearchRun({
      run_id: "run_python_graph",
      status: "done",
      artifacts: {
        plan: {
          coverage_family_statuses: [
            { id: "cf-hazmat", family: "hazmat", status: "active", reason: "", project_facts_considered: [], missing_facts: [] },
          ],
          regulatory_angles: [
            { id: "angle-hmbp", family: "hazmat", label: "HMBP", reason: "", triggering_facts: [], status: "active" },
          ],
          research_graph: [
            { id: "H-HAZMAT-HMBP", angle_id: "angle-hmbp", family: "hazmat", question: "Does HMBP apply?", required_facts: [], expected_source_type: "agency_guidance", success_criteria: [], dependencies: [] },
          ],
          research_tasks: [
            { task_id: "T-HMBP", hypothesis_id: "H-HAZMAT-HMBP", assigned_agent: "hazmat_researcher", allowed_tools: [], blocked_tools: [], budget: { max_sources: 1, max_runtime_seconds: 1, max_model_calls: 1 } },
          ],
        },
      },
      trace_events: [
        { scope: "plan:complete", payload: {}, created_at: "2026-06-02T10:00:00.000Z" },
      ],
      result: { determination: { status: "verified", trusted_hypotheses: [], needs_review_hypotheses: [], reasons: [] } },
    });
    const replayed = new Set(run.trace_events.map((event) => event.id));
    const { nodes } = buildGraph(run, replayed);

    expect(nodes.map((node) => node.type).sort()).toEqual(["angle", "coverage", "hypothesis", "task"]);
  });
});
