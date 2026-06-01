import { describe, expect, it } from "vitest";
import { verifyEvidence } from "../verifier";
import { CONFIDENCE_GATE } from "../confidence";
import type { EvidenceBundle, ScopePack } from "../types";

const scope: ScopePack = {
  run_id: "r",
  facility: { address: "X", jurisdiction_stack: [], naics: "323111", sic: null },
  project_change: { description: "d", equipment: [], chemicals: [], waste_streams: [], disturbance_acres: null, process_discharge: null },
  missing_facts: [],
  assumptions: [],
};

function groundedBundle(): EvidenceBundle {
  return {
    hypothesis_id: "H-X",
    sources: [{
      url: "https://example.gov/x", source_name: "primary", authority_rank: 1,
      fetched_at: "2026-06-01T00:00:00Z", content_hash: "h", effective_date: "2025-01-01",
      quote: "the rule applies to this facility",
    }],
    extracted_claims: [{ field: "f", value: "v", source_url: "https://example.gov/x", quote: "the rule applies to this facility", confidence: 0.9 }],
    researcher_conclusion: "applies",
    uncertainties: [],
  };
}

describe("confidence drives the agent's continued work (consistency-wired, not just a number)", () => {
  it("an unstable consistency signal pulls confidence below the gate and files a repair ticket", () => {
    // All four checks pass, but the researcher's re-samples disagreed (1 of 3
    // stable) — that genuine instability must lower confidence below the bar and
    // tell the agent to keep working, not ship a shaky 'verified'.
    const verdict = verifyEvidence(scope, groundedBundle(), { samples: 3, stableSamples: 1 });

    expect(verdict.checks.grounding.pass).toBe(true);
    expect(verdict.confidence).toBeLessThan(CONFIDENCE_GATE);
    expect(verdict.repair_tickets.length).toBeGreaterThan(0);
    expect(verdict.repair_tickets[0].failure_type).toBe("low_confidence");
  });

  it("a stable consistency signal clears the gate — verified, no repair", () => {
    const verdict = verifyEvidence(scope, groundedBundle(), { samples: 3, stableSamples: 3 });
    expect(verdict.confidence).toBeGreaterThanOrEqual(CONFIDENCE_GATE);
    expect(verdict.verdict).toBe("pass");
    expect(verdict.repair_tickets.length).toBe(0);
  });

  it("no consistency signal: all-checks-pass still clears the gate (back-compat)", () => {
    const verdict = verifyEvidence(scope, groundedBundle());
    expect(verdict.confidence).toBeGreaterThanOrEqual(CONFIDENCE_GATE);
    expect(verdict.verdict).toBe("pass");
  });
});
