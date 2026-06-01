import { describe, expect, it } from "vitest";
import { synthesize } from "../synthesis";
import { CONFIDENCE_GATE } from "../confidence";
import type { EvidenceBundle, RegulatoryAngle, ResearchHypothesis, VerificationVerdict, ScopePack } from "../types";

const scope: ScopePack = {
  run_id: "r",
  facility: { address: "X", jurisdiction_stack: [], county: null, city: null, naics: "323111", sic: null },
  project_change: { description: "d", equipment: [], chemicals: [], waste_streams: [], disturbance_acres: null, process_discharge: null },
  missing_facts: [],
  assumptions: [],
};

const hyp: ResearchHypothesis = {
  id: "H-X", angle_id: "A-X", family: "air", question: "q",
  required_facts: [], expected_source_type: "regulation", success_criteria: [], dependencies: [],
};
const angle: RegulatoryAngle = { id: "A-X", family: "air", label: "L", reason: "", triggering_facts: [], status: "active" };

const bundle: EvidenceBundle = {
  hypothesis_id: "H-X",
  sources: [{ url: "https://g.gov/x", source_name: "S", authority_rank: 1, fetched_at: "2026-06-01T00:00:00Z", content_hash: "h", effective_date: "2025-01-01", quote: "the rule applies" }],
  extracted_claims: [{ field: "f", value: "v", source_url: "https://g.gov/x", quote: "the rule applies", confidence: 0.9 }],
  researcher_conclusion: "applies",
  uncertainties: [],
};

function verdict(confidence: number): VerificationVerdict {
  return {
    hypothesis_id: "H-X",
    verdict: "pass",
    checks: { grounding: { pass: true, reason: "" } },
    confidence,
    repair_tickets: [],
  };
}

describe("confidence gate before synthesis", () => {
  it("exports a 0.9 gate", () => {
    expect(CONFIDENCE_GATE).toBe(0.9);
  });

  it("a passing verdict BELOW 0.9 is NOT verified — falls to needs_review", () => {
    const out = synthesize(scope, [hyp], [angle], [bundle], [verdict(0.85)]);
    const det = out.determinations[0];
    expect(det.verified).toBe(false);
    expect(det.applies).toBe("needs_review");
    expect(det.review_flag).toBe(true);
  });

  it("a passing verdict AT/ABOVE 0.9 is verified and passes to synthesis", () => {
    const out = synthesize(scope, [hyp], [angle], [bundle], [verdict(0.92)]);
    const det = out.determinations[0];
    expect(det.verified).toBe(true);
    expect(det.applies).not.toBe("needs_review");
  });
});
