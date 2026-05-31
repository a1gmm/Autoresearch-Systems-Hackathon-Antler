import { researcherCoreToolIds, type HarnessToolId } from "./toolCatalog";

type ResearcherCoreToolId = (typeof researcherCoreToolIds)[number];

// Maps our domain HarnessToolIds to Claude Agent SDK built-in tool names
// (PascalCase, same as Claude Code). Most HarnessToolIds are CUSTOM domain
// tools with no 1:1 SDK built-in — for v1 those map to null and would later
// be registered as SDK custom tools. Only retrieval over the open web has a
// direct built-in today (WebFetch), so it is the lone non-null mapping.
export const SDK_TOOL_FOR_HARNESS = {
  read_skill: null,
  get_source_pointers: null,
  get_cached_source: null,
  get_triggers: null,
  fetch_source: "WebFetch",
  prove_currency: null,
  extract_threshold: null,
  evaluate_predicate: null,
  quarantine_injection: null,
} satisfies Record<ResearcherCoreToolId, string | null> & Partial<Record<HarnessToolId, string | null>>;

// Resolve the SDK built-in tool name for a HarnessToolId, or null when the
// id is custom/policy (or simply unmapped).
export function sdkToolName(id: HarnessToolId): string | null {
  if (id in SDK_TOOL_FOR_HARNESS) {
    return SDK_TOOL_FOR_HARNESS[id as keyof typeof SDK_TOOL_FOR_HARNESS] ?? null;
  }
  return null;
}

// The deduped SDK built-in tools a live researcher should receive: WebSearch
// for primary-source discovery, WebFetch to read those sources.
export function researcherSdkAllowedTools(): string[] {
  return [...new Set<string>(["WebFetch", "WebSearch"])];
}
