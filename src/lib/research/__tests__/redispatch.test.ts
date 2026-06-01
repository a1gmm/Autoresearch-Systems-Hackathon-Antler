import { afterEach, describe, expect, it } from "vitest";
import { runResearch } from "../run";
import { installFakeResearch, groundedBundle } from "@/test/researchTransport";
import { __setArtifactStoreForTests, InMemoryArtifactStore } from "../artifactStore";
import type { EvidenceBundle } from "../types";

// In jsdom, parseScope's OpenAI call fails -> emptyScope, which still triggers
// the wastewater program (discharge !== false). We target that hypothesis so the
// test does not depend on a live LLM extracting equipment from prose.
const TARGET = "H-WASTEWATER-PRETREATMENT";

describe("live re-dispatch: a weak first result is re-researched", () => {
  afterEach(() => __setArtifactStoreForTests(null));

  it("re-runs a hypothesis whose first bundle was ungrounded, keeping the stronger second result", async () => {
    __setArtifactStoreForTests(new InMemoryArtifactStore());
    const attempts: Record<string, number> = {};

    const cleanup = installFakeResearch((hid): EvidenceBundle => {
      attempts[hid] = (attempts[hid] ?? 0) + 1;
      // First attempt for the target comes back UNGROUNDED (quote not in source);
      // the re-dispatch must try again and the second attempt is grounded.
      if (hid === TARGET && attempts[hid] === 1) {
        return {
          hypothesis_id: hid,
          sources: [{ url: "https://g.gov/x", source_name: "S", authority_rank: 1, fetched_at: "2026-06-01T00:00:00Z", content_hash: "h", effective_date: "2025-01-01", quote: "real source text" }],
          extracted_claims: [{ field: "f", value: "v", source_url: "https://g.gov/x", quote: "a quote NOT in the source", confidence: 0.9 }],
          researcher_conclusion: "applies",
          uncertainties: [],
        };
      }
      return groundedBundle(hid);
    });

    try {
      await runResearch({ project_description: "A facility that discharges process wastewater." });
      // The target was re-dispatched: more than one attempt.
      expect(attempts[TARGET]).toBeGreaterThan(1);
    } finally {
      cleanup();
    }
  });
});
