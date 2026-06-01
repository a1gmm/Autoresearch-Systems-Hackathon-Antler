import { afterEach, describe, expect, it } from "vitest";
import { finalizeRun } from "../run";
import { InMemoryArtifactStore, __setArtifactStoreForTests } from "../artifactStore";
import type { EvidenceBundle } from "../types";

// Minimal plan with one hypothesis so finalizeRun produces one determination.
const plan = {
  coverage_family_statuses: [],
  regulatory_angles: [{ id: "A-x", family: "air" as const, label: "L", reason: "", triggering_facts: [], status: "active" as const }],
  research_graph: [{ id: "H-AIR-201", angle_id: "A-x", family: "air" as const, question: "q", claim_to_test: "c", required_facts: [], expected_source_type: "regulation" as const, success_criteria: [], dependencies: [] }],
  research_tasks: [],
};

const scope = {
  run_id: "run_art", facility: { address: "X", jurisdiction_stack: [], naics: "323111", sic: null },
  project_change: { description: "d", equipment: [{ kind: "oven", description: "o" }], chemicals: [], waste_streams: [], disturbance_acres: null, process_discharge: null },
  missing_facts: [], assumptions: [],
};

const bundle: EvidenceBundle = {
  hypothesis_id: "H-AIR-201",
  sources: [{ url: "https://g.gov/x", source_name: "S", authority_rank: 1, fetched_at: "2026-06-01T00:00:00Z", content_hash: "h", effective_date: "2025-01-01", quote: "the rule applies" }],
  extracted_claims: [{ field: "f", value: "v", source_url: "https://g.gov/x", quote: "the rule applies", confidence: 0.9 }],
  researcher_conclusion: "applies",
  uncertainties: [],
};

describe("the run persists evidence as artifacts (subagent memory)", () => {
  afterEach(() => __setArtifactStoreForTests(null));

  it("finalizeRun writes each evidence bundle to the artifact store", async () => {
    const store = new InMemoryArtifactStore();
    __setArtifactStoreForTests(store);

    finalizeRun("run_art", scope as never, plan as never, [bundle], []);

    const persisted = await store.readEvidence("run_art", "H-AIR-201");
    expect(persisted?.hypothesis_id).toBe("H-AIR-201");
    expect(persisted?.sources[0].quote).toBe("the rule applies");
  });
});
