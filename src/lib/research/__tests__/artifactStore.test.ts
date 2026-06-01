import { describe, expect, it } from "vitest";
import { InMemoryArtifactStore } from "../artifactStore";
import type { EvidenceBundle } from "../types";

function bundle(hid: string, conclusion: EvidenceBundle["researcher_conclusion"] = "applies"): EvidenceBundle {
  return {
    hypothesis_id: hid,
    sources: [{ url: "https://g.gov/x", source_name: "S", authority_rank: 1, fetched_at: "2026-06-01T00:00:00Z", content_hash: "h", effective_date: "2025-01-01", quote: "q" }],
    extracted_claims: [{ field: "f", value: "v", source_url: "https://g.gov/x", quote: "q", confidence: 0.9 }],
    researcher_conclusion: conclusion,
    uncertainties: [],
  };
}

describe("artifacts-driven subagent memory", () => {
  it("a subagent writes an evidence artifact and another run reads it back", async () => {
    const store = new InMemoryArtifactStore();
    await store.writeEvidence("run1", bundle("H-AIR-201"));

    const read = await store.readEvidence("run1", "H-AIR-201");
    expect(read?.hypothesis_id).toBe("H-AIR-201");
    expect(read?.researcher_conclusion).toBe("applies");
  });

  it("writing the same hypothesis again overwrites (latest artifact wins — accumulation)", async () => {
    const store = new InMemoryArtifactStore();
    await store.writeEvidence("run1", bundle("H-AIR-201", "needs_review"));
    await store.writeEvidence("run1", bundle("H-AIR-201", "applies")); // a better re-research

    const read = await store.readEvidence("run1", "H-AIR-201");
    expect(read?.researcher_conclusion).toBe("applies");
    // one artifact per hypothesis, not duplicated
    expect((await store.listEvidence("run1")).length).toBe(1);
  });

  it("artifacts are scoped per run", async () => {
    const store = new InMemoryArtifactStore();
    await store.writeEvidence("run1", bundle("H-AIR-201"));
    expect(await store.readEvidence("run2", "H-AIR-201")).toBeNull();
    expect((await store.listEvidence("run2")).length).toBe(0);
  });

  it("records scratch findings a subagent can resume from (artifact-driven, not in-context)", async () => {
    const store = new InMemoryArtifactStore();
    await store.appendScratch("run1", "H-AIR-201", "fetched rule 201; quote not yet grounded");
    await store.appendScratch("run1", "H-AIR-201", "found candidate quote");
    const notes = await store.readScratch("run1", "H-AIR-201");
    expect(notes).toEqual(["fetched rule 201; quote not yet grounded", "found candidate quote"]);
  });
});
