import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { runResearch } from "@/lib/research/run";
import { deriveSandboxTiles } from "@/lib/ui/sandboxState";
import { installFakeResearch, groundedBundle } from "@/test/researchTransport";
import type { ResearchRun } from "@/lib/research/types";

const SOCAL =
  "A Los Angeles County manufacturer is adding a coating booth and storing 60 gallons of a new flammable solvent.";

function eventIds(run: ResearchRun, predicate: (e: ResearchRun["trace_events"][number]) => boolean) {
  return new Set(run.trace_events.filter(predicate).map((e) => e.id));
}

function runtimeRun(events: ResearchRun["trace_events"]): ResearchRun {
  return {
    run_id: "runtime",
    status: "running",
    project_facts: {},
    jurisdiction_stack: [],
    scope_pack: {} as never,
    coverage_family_statuses: [],
    regulatory_angles: [],
    research_graph: [{ id: "H-AIR-201", angle_id: "a", family: "air", question: "Air permit applicability", required_facts: [], expected_source_type: "regulation", success_criteria: [], dependencies: [] }],
    research_tasks: [{ task_id: "T-AIR-1", hypothesis_id: "H-AIR-201", assigned_agent: "research_worker", allowed_tools: [], blocked_tools: [], budget: { max_sources: 1, max_runtime_seconds: 1, max_model_calls: 1 } }],
    evidence_bundles: [],
    verification_verdicts: [],
    repair_tickets: [],
    memory_updates: [],
    determinations: [],
    trace_events: events,
    report_markdown: "",
  };
}

function runtimeEvent(id: string, actor: string, phase: string, status: ResearchRun["trace_events"][number]["status"], message: string, artifact_id?: string): ResearchRun["trace_events"][number] {
  return { id, run_id: "runtime", ts: `2026-01-01T00:00:0${id.length}.000Z`, actor, phase, status, message, artifact_id };
}

describe("deriveSandboxTiles", () => {
  // Drive the real research pool with an injected transport (no fixture codepath).
  let cleanup: () => void;
  beforeEach(() => {
    cleanup = installFakeResearch((hid) => groundedBundle(hid));
  });
  afterEach(() => cleanup());

  it("starts every active worker tile as queued before replay", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    const tiles = deriveSandboxTiles(run, new Set());
    const active = tiles.filter((t) => t.active);
    expect(active.length).toBe(run.research_tasks.length);
    expect(active.every((t) => t.status === "queued")).toBe(true);
  });

  it("shows workers fetching once fanout is running but not done", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    const ids = eventIds(run, (e) => e.actor === "research_pool" && e.phase === "fanout" && e.status === "running");
    const tiles = deriveSandboxTiles(run, ids);
    expect(tiles.some((t) => t.active && t.status === "fetching")).toBe(true);
  });

  it("resolves every active tile to a terminal status when fully replayed", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    const all = new Set(run.trace_events.map((e) => e.id));
    const tiles = deriveSandboxTiles(run, all);
    const terminal = ["verified", "repaired", "needs_review", "failed"];
    expect(tiles.filter((t) => t.active).every((t) => terminal.includes(t.status))).toBe(true);
  });

  it("marks a repaired hypothesis tile as repaired when fully replayed", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    const all = new Set(run.trace_events.map((e) => e.id));
    const tiles = deriveSandboxTiles(run, all);
    const repairedHyp = new Set(run.repair_tickets.map((r) => r.hypothesis_id));
    // every task whose hypothesis had a repair ticket and ultimately passed reads as "repaired"
    for (const task of run.research_tasks) {
      if (!repairedHyp.has(task.hypothesis_id)) continue;
      const verdict = run.verification_verdicts.find((v) => v.hypothesis_id === task.hypothesis_id);
      if (verdict?.verdict !== "pass") continue;
      const tile = tiles.find((t) => t.id === task.task_id);
      expect(tile?.status).toBe("repaired");
    }
  });

  it("includes muted tiles for coverage families with no worker", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    const tiles = deriveSandboxTiles(run, new Set());
    const muted = tiles.filter((t) => !t.active);
    // every muted tile maps to a coverage family that has no research task
    const familiesWithTask = new Set(
      run.research_tasks.map((task) => run.research_graph.find((h) => h.id === task.hypothesis_id)?.family),
    );
    expect(muted.every((t) => !familiesWithTask.has(t.family))).toBe(true);
  });

  it("keeps old fanout behavior working", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    const fetching = deriveSandboxTiles(run, eventIds(run, (e) => e.actor === "research_pool" && e.phase === "fanout" && e.status === "running"));
    expect(fetching.some((t) => t.active && t.status === "fetching")).toBe(true);
  });

  it("marks runtime accepted first-pass tasks as verified", () => {
    const run = runtimeRun([
      runtimeEvent("boot", "workspace.booting", "parent.planning", "running", "planning T-AIR-1"),
      runtimeEvent("draft", "research_worker", "draft.completed", "done", "draft complete for T-AIR-1", "workspace/T-AIR-1/draft.md"),
      runtimeEvent("accepted", "reviewer", "review.accepted", "done", "accepted T-AIR-1", "workspace/T-AIR-1/review.json"),
      runtimeEvent("bundles", "synthesis_agent", "bundles.complete", "done", "bundles complete"),
    ]);
    const tiles = deriveSandboxTiles(run, new Set(run.trace_events.map((e) => e.id)));
    expect(tiles.find((t) => t.id === "T-AIR-1")?.status).toBe("verified");
  });

  it("marks runtime repaired tasks as repaired after repair then accepted", () => {
    const run = runtimeRun([
      runtimeEvent("draft", "research_worker", "draft.completed", "done", "draft complete for T-AIR-1", "workspace/T-AIR-1/draft.md"),
      runtimeEvent("repair-needed", "reviewer", "review.decision.needs_repair", "needs_review", "needs repair for T-AIR-1"),
      runtimeEvent("repair", "research_worker", "repair.completed", "done", "repair complete for T-AIR-1", "workspace/T-AIR-1/repair.md"),
      runtimeEvent("accepted", "reviewer", "review.accepted", "done", "accepted T-AIR-1"),
      runtimeEvent("bundles", "synthesis_agent", "bundles.complete", "done", "bundles complete"),
    ]);
    const tiles = deriveSandboxTiles(run, new Set(run.trace_events.map((e) => e.id)));
    expect(tiles.find((t) => t.id === "T-AIR-1")?.status).toBe("repaired");
  });

  it("marks runtime human review tasks as needs_review", () => {
    const run = runtimeRun([
      runtimeEvent("draft", "research_worker", "draft.completed", "done", "draft complete for T-AIR-1"),
      runtimeEvent("human", "reviewer", "review.needs_human_review", "needs_review", "human review for T-AIR-1"),
    ]);
    const tiles = deriveSandboxTiles(run, new Set(run.trace_events.map((e) => e.id)));
    expect(tiles.find((t) => t.id === "T-AIR-1")?.status).toBe("needs_review");
  });

  it("marks runtime parent failures as failed for active tasks", () => {
    const run = runtimeRun([
      runtimeEvent("boot", "parent", "workspace.booting", "running", "booting runtime", "runtime"),
      runtimeEvent("failed", "parent", "runtime.failed", "failed", "Workspace runtime failed", "runtime"),
    ]);
    const tiles = deriveSandboxTiles(run, new Set(run.trace_events.map((e) => e.id)));
    expect(tiles.find((t) => t.id === "T-AIR-1")?.status).toBe("failed");
  });
});
