import { describe, expect, it } from "vitest";
import { verifyEvidence } from "../verifier";
import type { EvidenceBundle, ScopePack } from "../types";

const scope: ScopePack = {
  run_id: "r",
  facility: { address: "X", jurisdiction_stack: [], county: null, city: null, naics: "323111", sic: null },
  project_change: {
    description: "d", equipment: [], chemicals: [], waste_streams: [],
    disturbance_acres: null, process_discharge: null,
  },
  missing_facts: [],
  assumptions: [],
};

function bundle(hid: string, opts: Partial<EvidenceBundle> = {}): EvidenceBundle {
  return {
    hypothesis_id: hid,
    sources: [{
      url: "https://www.govinfo.gov/x", source_name: "Primary", authority_rank: 1,
      fetched_at: "2026-06-01T00:00:00Z", content_hash: "sha256:real", effective_date: "2025-01-01",
      quote: "A permit is required for facilities that emit air contaminants.",
    }],
    extracted_claims: [{
      field: "trigger", value: "permit required",
      source_url: "https://www.govinfo.gov/x",
      quote: "A permit is required for facilities that emit air contaminants.",
      confidence: 0.9,
    }],
    researcher_conclusion: "applies",
    uncertainties: [],
    ...opts,
  };
}

describe("verifier is hypothesis-ID-agnostic (no hardcoded per-ID branches)", () => {
  it("verifies grounded evidence for a NEVER-SEEN hypothesis ID the same as any other", () => {
    // An ID with no hardcoded branch anywhere in the code. If the verifier still
    // works, it is running real mechanical checks, not a per-ID script.
    const v = verifyEvidence(scope, bundle("H-NOVEL-FIRE-CODE-9000"));
    expect(v.verdict).toBe("pass");
    expect(v.checks.grounding.pass).toBe(true);
  });

  it("fails closed when the claim quote is NOT a span of the source quote — any ID", () => {
    const v = verifyEvidence(
      scope,
      bundle("H-ANYTHING", {
        extracted_claims: [{
          field: "trigger", value: "permit required",
          source_url: "https://www.govinfo.gov/x",
          quote: "This sentence is not in the source at all.",
          confidence: 0.9,
        }],
      }),
    );
    expect(v.verdict).toBe("fail");
    expect(v.checks.grounding.pass).toBe(false);
    expect(v.repair_tickets.length).toBe(1);
  });

  it("does NOT treat H-HAZMAT-HMBP specially — no fixture-hash branch", () => {
    // Same grounded shape as any other hypothesis -> same mechanical pass.
    // (Previously this ID hit a hardcoded fixture-hash branch.)
    const v = verifyEvidence(scope, bundle("H-HAZMAT-HMBP"));
    expect(v.verdict).toBe("pass");
    // The reason must NOT mention a fixture/seeded cache (the old hardcoded text).
    expect(v.checks.currency.reason.toLowerCase()).not.toContain("seeded");
    expect(v.checks.currency.reason.toLowerCase()).not.toContain("fixture");
  });

  it("needs_review when the researcher could not reach a grounded conclusion — any ID", () => {
    const v = verifyEvidence(scope, bundle("H-X", { researcher_conclusion: "needs_review" }));
    expect(v.verdict).toBe("needs_review");
  });
});
