import type { EvidenceBundle, RepairTicket, ScopePack, VerificationVerdict } from "./types";
import { computeConfidence, CONFIDENCE_GATE } from "./confidence";
import type { ConsistencySignal } from "./confidence";

// The verifier is hypothesis-ID-AGNOSTIC and mechanical. It never branches on a
// specific hypothesis ID and never rubber-stamps a result with pass:true
// constants. Every bundle — for any permit, any jurisdiction, any future family
// — is judged by the same four checks against the evidence the researcher
// actually returned:
//   currency      — the source carries a fetched/effective date
//   authority     — the source is high-authority (rank <= 2)
//   grounding     — the extracted claim's quote is a verbatim span of the cited
//                   source quote (whitespace-tolerant); this is the anti-fabrication core
//   predicate     — the researcher reached a grounded conclusion (needs_review never passes)
// A grounding failure files a repair ticket. Nothing here knows about fixtures.
export function verifyEvidence(
  _scope: ScopePack,
  bundle: EvidenceBundle,
  consistency?: ConsistencySignal
): VerificationVerdict {
  const source = bundle.sources[0];

  if (!source) {
    return needsReview(bundle.hypothesis_id, "source_failed", "No source was returned by the worker.");
  }

  const claim = bundle.extracted_claims[0];
  const sourceQuote = (source.quote ?? "").trim();
  const claimQuote = (claim?.quote ?? "").trim();
  const grounded =
    sourceQuote.length > 0 &&
    claimQuote.length > 0 &&
    normWs(sourceQuote).includes(normWs(claimQuote));
  const conclusion = bundle.researcher_conclusion;
  const decided = conclusion === "applies" || conclusion === "does_not_apply";

  // Currency: the source must carry a real fetch date or effective date. No date
  // = no currency proof = fail closed (the source could be arbitrarily stale).
  const fetchedAt = source.fetched_at?.slice(0, 10);
  const effectiveDate = source.effective_date?.slice(0, 10);
  const hasDate = Boolean(fetchedAt) || Boolean(effectiveDate);

  const checks = {
    currency: {
      pass: hasDate,
      reason: hasDate
        ? `source dated ${effectiveDate ?? fetchedAt}`
        : "no fetch or effective date — currency cannot be proven",
    },
    authority: { pass: source.authority_rank <= 2, reason: source.authority_rank <= 2 ? "official or high-authority source" : "source authority rank is low" },
    grounding: { pass: grounded, reason: grounded ? "extracted claim quote appears in the cited source quote" : "extracted claim is not grounded in the cited source quote" },
    predicate_math: { pass: decided, reason: decided ? `researcher reached a grounded conclusion: ${conclusion}` : "researcher could not reach a grounded conclusion" }
  };

  if (!grounded) {
    return {
      hypothesis_id: bundle.hypothesis_id,
      verdict: "fail",
      checks,
      confidence: computeConfidence(checks),
      repair_tickets: [
        {
          ticket_id: `R-${bundle.hypothesis_id}-001`,
          hypothesis_id: bundle.hypothesis_id,
          failure_type: "grounding_failed",
          failed_check: "grounding",
          observed_problem: "Extracted claim is not supported by a verbatim quote from the cited source.",
          repair_action: "rerun extraction constrained to verbatim source text",
          max_attempts_remaining: 1
        }
      ]
    };
  }

  const confidence = computeConfidence(checks, consistency);
  const allChecksPass = checks.authority.pass && checks.predicate_math.pass && checks.currency.pass;

  // Confidence drives the agent's continued work, not just a synthesis number.
  // If the evidence is grounded and the checks pass but confidence is still
  // below the gate (e.g. a weak source capped it), the answer isn't good enough
  // to ship — file a low_confidence repair ticket so the orchestrator re-runs
  // the researcher toward a stronger source instead of silently settling.
  if (allChecksPass && confidence < CONFIDENCE_GATE) {
    return {
      hypothesis_id: bundle.hypothesis_id,
      verdict: "needs_review",
      checks,
      confidence,
      repair_tickets: [
        {
          ticket_id: `R-${bundle.hypothesis_id}-conf`,
          hypothesis_id: bundle.hypothesis_id,
          failure_type: "low_confidence",
          failed_check: "confidence",
          observed_problem: `Grounded, but confidence ${confidence.toFixed(2)} is below the ${CONFIDENCE_GATE} gate.`,
          repair_action: "re-research toward a higher-authority / more current source to raise confidence",
          max_attempts_remaining: 1
        }
      ]
    };
  }

  return {
    hypothesis_id: bundle.hypothesis_id,
    verdict: allChecksPass ? "pass" : "needs_review",
    checks,
    confidence,
    repair_tickets: []
  };
}

function normWs(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

// Repair is ID-agnostic. The verifier cannot itself re-fetch a source or re-run
// an LLM extraction (that is the researcher agent's job), so a repair ticket
// resolves to a fail-closed needs_review bundle that carries the repair action
// for the orchestrator to re-dispatch the real researcher. No fixtures, no
// per-ID scripting — the same honest no-op for every hypothesis.
export function repairEvidence(_scope: ScopePack, ticket: RepairTicket): EvidenceBundle {
  return {
    hypothesis_id: ticket.hypothesis_id,
    sources: [],
    extracted_claims: [],
    researcher_conclusion: "needs_review",
    uncertainties: [`Repair requires re-running the researcher: ${ticket.repair_action}`],
  };
}

function needsReview(hypothesis_id: string, failure_type: RepairTicket["failure_type"], reason: string): VerificationVerdict {
  const checks = {
    currency: { pass: false, reason: "no verified source to date" },
    authority: { pass: failure_type !== "source_failed", reason: "authority could be evaluated or source failure was explicit" },
    grounding: { pass: failure_type !== "source_failed", reason },
    predicate_math: { pass: false, reason }
  };
  return {
    hypothesis_id,
    verdict: "needs_review",
    checks,
    confidence: computeConfidence(checks),
    repair_tickets: []
  };
}
