import type { CoverageFamily, ResearchRun } from "@/lib/research/types";

export type SandboxStatus =
  | "queued"
  | "booting"
  | "fetching"
  | "verifying"
  | "verified"
  | "failed"
  | "repairing"
  | "repaired"
  | "needs_review"
  | "out_of_scope";

export type SandboxTile = {
  id: string;
  family: CoverageFamily;
  label: string;
  status: SandboxStatus;
  active: boolean;
};

function fired(
  run: ResearchRun,
  ids: Set<string>,
  actor: string,
  phase: string,
  status: string,
): boolean {
  return run.trace_events.some(
    (e) => e.actor === actor && e.phase === phase && e.status === status && ids.has(e.id),
  );
}

function eventMatchesTask(
  event: ResearchRun["trace_events"][number],
  task: ResearchRun["research_tasks"][number],
): boolean {
  const haystack = `${event.artifact_id ?? ""} ${event.message ?? ""}`.toLowerCase();
  return haystack.includes(task.task_id.toLowerCase()) || haystack.includes(task.hypothesis_id.toLowerCase());
}

function runtimeFired(
  run: ResearchRun,
  ids: Set<string>,
  task: ResearchRun["research_tasks"][number],
  actor: string,
  phase: string,
  status?: string,
): boolean {
  return run.trace_events.some(
    (e) =>
      ids.has(e.id) &&
      e.actor === actor &&
      e.phase === phase &&
      (!status || e.status === status) &&
      eventMatchesTask(e, task),
  );
}

function runtimeFiredAnyTask(
  run: ResearchRun,
  ids: Set<string>,
  actor: string,
  phase: string,
  status?: string,
): boolean {
  return run.trace_events.some(
    (e) => ids.has(e.id) && e.actor === actor && e.phase === phase && (!status || e.status === status),
  );
}

function hasRuntimeTrace(run: ResearchRun): boolean {
  return run.trace_events.some((e) =>
    e.actor === "workspace.booting" ||
    e.actor === "parent" ||
    e.actor === "research_worker" ||
    e.actor === "reviewer" ||
    e.phase.includes(".") ||
    e.phase === "bundles.complete",
  );
}

function runtimeStatusForTask(run: ResearchRun, ids: Set<string>, task: ResearchRun["research_tasks"][number], terminal: SandboxStatus): SandboxStatus {
  const booting =
    runtimeFiredAnyTask(run, ids, "workspace.booting", "parent.planning", "running") ||
    runtimeFiredAnyTask(run, ids, "parent", "workspace.booting", "running") ||
    runtimeFiredAnyTask(run, ids, "parent", "parent.planning", "running");
  const draftDone = runtimeFired(run, ids, task, "research_worker", "draft.completed", "done");
  const needsRepair = runtimeFired(run, ids, task, "reviewer", "review.decision.needs_repair", "needs_review");
  const repairDone = runtimeFired(run, ids, task, "research_worker", "repair.completed", "done");
  const accepted = runtimeFired(run, ids, task, "reviewer", "review.accepted", "done");
  const humanReview = runtimeFired(run, ids, task, "reviewer", "review.needs_human_review", "needs_review");
  const runtimeFailed =
    runtimeFiredAnyTask(run, ids, "parent", "runtime.failed", "failed") ||
    runtimeFired(run, ids, task, "runtime", "runtime.failed", "failed") ||
    runtimeFired(run, ids, task, "runtime", "failed", "failed") ||
    runtimeFired(run, ids, task, "runtime.failed", "runtime.failed", "failed") ||
    runtimeFired(run, ids, task, "runtime.failed", "failed", "failed") ||
    runtimeFired(run, ids, task, "research_worker", "runtime.failed", "failed") ||
    runtimeFired(run, ids, task, "reviewer", "runtime.failed", "failed");
  const bundlesComplete = runtimeFiredAnyTask(run, ids, "synthesis_agent", "bundles.complete", "done");

  if (runtimeFailed) return "failed";
  if (humanReview) return "needs_review";
  if (bundlesComplete && accepted) return repairDone || needsRepair ? "repaired" : "verified";
  if (bundlesComplete) return terminal;
  if (accepted) return repairDone || needsRepair ? "repaired" : "verified";
  if (repairDone) return "repaired";
  if (needsRepair) return "repairing";
  if (draftDone) return "verifying";
  if (booting) return "booting";
  return "queued";
}

export function deriveSandboxTiles(run: ResearchRun, replayedEventIds: Set<string>): SandboxTile[] {
  const ids = replayedEventIds;
  const runtimeTrace = hasRuntimeTrace(run);
  const fanoutRunning = fired(run, ids, "research_pool", "fanout", "running");
  const fanoutDone = fired(run, ids, "research_pool", "fanout", "done");
  const failFired = fired(run, ids, "verifier", "verification", "failed");
  const repairResolved =
    fired(run, ids, "verifier", "repair_verification", "done") ||
    fired(run, ids, "verifier", "repair_verification", "needs_review") ||
    fired(run, ids, "synthesis_agent", "matrix", "done");

  const hypById = new Map(run.research_graph.map((h) => [h.id, h]));
  const verdictByHyp = new Map(run.verification_verdicts.map((v) => [v.hypothesis_id, v]));
  const repairHyp = new Set(run.repair_tickets.map((r) => r.hypothesis_id));
  const familiesWithTask = new Set<CoverageFamily>();

  const activeTiles: SandboxTile[] = run.research_tasks.map((task) => {
    const hyp = hypById.get(task.hypothesis_id);
    const family = (hyp?.family ?? "air") as CoverageFamily;
    familiesWithTask.add(family);

    const hasRepair = repairHyp.has(task.hypothesis_id);
    const verdict = verdictByHyp.get(task.hypothesis_id);
    const terminal: SandboxStatus =
      verdict?.verdict === "pass"
        ? hasRepair
          ? "repaired"
          : "verified"
        : verdict?.verdict === "needs_review"
          ? "needs_review"
          : verdict?.verdict === "fail"
            ? "failed"
            : "needs_review";

    let status: SandboxStatus;
    if (runtimeTrace) {
      status = runtimeStatusForTask(run, ids, task, terminal);
    } else if (!fanoutRunning) status = "queued";
    else if (!fanoutDone) status = "fetching";
    else if (!repairResolved) status = hasRepair && failFired ? "repairing" : "verifying";
    else status = terminal;

    return { id: task.task_id, family, label: hyp?.question ?? family, status, active: true };
  });

  const mutedTiles: SandboxTile[] = run.coverage_family_statuses
    .filter((cf) => !familiesWithTask.has(cf.family))
    .map((cf) => ({
      id: cf.id,
      family: cf.family,
      label: cf.reason,
      status: (cf.status === "out_of_scope" ? "out_of_scope" : "needs_review") as SandboxStatus,
      active: false,
    }));

  return [...activeTiles, ...mutedTiles];
}
