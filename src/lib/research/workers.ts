import type { EvidenceBundle, ResearchHypothesis, ResearchTask } from "./types";
import type { ResearchPoolResult } from "./modal/researchPool";

// The ONLY research path. Every hypothesis is investigated by the real agentic
// worker: it reasons over the skills/tools it is given, fetches allowlisted
// primary sources, and grounds its own extraction. There is no deterministic /
// fixture / canned codepath — tests drive this same path by injecting a fake
// transport (researchPool __setFetchForTests). If the backend is unreachable or
// unconfigured the pool FAILS CLOSED (needs_review, no source); it never
// fabricates a determination.
export async function runLocalResearchPool(
  tasks: ResearchTask[],
  hypotheses: ResearchHypothesis[]
): Promise<ResearchPoolResult> {
  const { runModalResearchPool } = await import("./modal/researchPool");
  const result = await runModalResearchPool(tasks, hypotheses);
  if (result.degraded) {
    return {
      bundles: tasks.map((task) => failedBundle(task.hypothesis_id, `Live research unavailable: ${result.degraded!.reason}`)),
      degraded: result.degraded,
    };
  }
  return { bundles: result.bundles };
}

function failedBundle(hypothesis_id: string, reason: string): EvidenceBundle {
  return {
    hypothesis_id,
    sources: [],
    extracted_claims: [],
    researcher_conclusion: "needs_review",
    uncertainties: [reason],
  };
}
