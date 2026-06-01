// Research execution mode. Production defaults to LIVE: the real agentic Python
// worker fetches allowlisted primary sources and grounds an LLM extraction. The
// fixture path exists ONLY for deterministic offline tests/evals and must be
// opted into explicitly — production never silently substitutes canned data.
//
//   live    (default) — real Modal agentic worker; fail closed if unreachable.
//   fixture (opt-in)  — deterministic canned bundles; tests/CI/offline demo only.
export type ResearchMode = "live" | "fixture";

const MODES: readonly ResearchMode[] = ["live", "fixture"];

export function getResearchMode(): ResearchMode {
  const raw = process.env.RESEARCH_MODE?.toLowerCase();
  if (raw && (MODES as readonly string[]).includes(raw)) {
    return raw as ResearchMode;
  }
  // Back-compat: the old USE_MODAL=1 flag means "use the real worker" = live.
  // Any unrecognized value falls through to the production default (live).
  return "live";
}

export function isFixtureMode(mode: ResearchMode = getResearchMode()): boolean {
  return mode === "fixture";
}

export function isLiveMode(mode: ResearchMode = getResearchMode()): boolean {
  return mode === "live";
}
