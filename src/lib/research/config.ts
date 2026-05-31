// Typed runtime configuration for the research pipeline.
//
// RESEARCH_MODE replaces the old USE_MODAL boolean. It governs BOTH the research
// pool and (per Decision 5) the orchestration tier:
//   - fixture     : deterministic canned path — the default, used by tests/CI and dev.
//   - live_local  : real Agent SDK query() per task, run in-process (Phase 5).
//   - live_modal  : real Agent SDK query() inside the Modal function process (v2).
// Anything unrecognized falls back to "fixture" (the free, deterministic default).

export type ResearchMode = "fixture" | "live_local" | "live_modal";

const RESEARCH_MODES: readonly ResearchMode[] = ["fixture", "live_local", "live_modal"];

export function getResearchMode(): ResearchMode {
  const raw = process.env.RESEARCH_MODE;
  if (!raw) return "fixture";
  if ((RESEARCH_MODES as readonly string[]).includes(raw)) {
    return raw as ResearchMode;
  }
  console.warn(`[research] Unknown RESEARCH_MODE="${raw}"; falling back to "fixture".`);
  return "fixture";
}

export function isLiveMode(mode: ResearchMode = getResearchMode()): boolean {
  return mode === "live_local" || mode === "live_modal";
}

// Server-only. The live Agent SDK worker needs this; it must NEVER be exposed to the
// client (no NEXT_PUBLIC_ prefix). Returned undefined when unset so callers fail closed.
export function getAnthropicApiKey(): string | undefined {
  return process.env.ANTHROPIC_API_KEY;
}
