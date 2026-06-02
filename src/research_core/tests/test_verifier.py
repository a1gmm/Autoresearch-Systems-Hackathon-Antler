from research_core.verifier import (
    ConsistencySignal,
    authority_rank_check,
    compute_confidence,
    quote_grounded,
    verify_evidence,
)


def test_quote_grounded_normalizes_whitespace():
    source = "A facility storing\n55\tgallons   or more must file."
    quote = "55 gallons or more"
    assert quote_grounded(quote, source) is True
    assert quote_grounded("not in source", source) is False


def test_authority_rank_check_requires_high_authority_source():
    assert authority_rank_check(2).pass_ is True
    failed = authority_rank_check(3)

    assert failed.pass_ is False
    assert "authority rank 3" in failed.reason


def test_confidence_caps_failed_grounding_instead_of_averaging_high():
    checks = {
        "currency": {"pass": True, "reason": "dated"},
        "authority": {"pass": True, "reason": "official"},
        "grounding": {"pass": False, "reason": "quote missing"},
        "predicate_math": {"pass": True, "reason": "decided"},
    }

    assert compute_confidence(checks) == 0.35


def test_stale_currency_status_needs_review_with_currency_repair_ticket():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-STALE",
            "sources": [
                {
                    "url": "https://example.test/rule",
                    "source_name": "Agency",
                    "authority_rank": 1,
                    "fetched_at": "2020-01-01T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "stale",
                    "quote": "A permit is required.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "trigger",
                    "value": "permit required",
                    "source_url": "https://example.test/rule",
                    "quote": "A permit is required.",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "needs_review"
    assert verdict.checks["currency"].pass_ is False
    assert any("currency failed" in reason for reason in verdict.distrust_reasons)
    assert any(ticket.failed_check == "currency" for ticket in verdict.repair_tickets)


def test_unconfirmed_currency_status_needs_review_with_currency_repair_ticket():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-UNCONFIRMED",
            "sources": [
                {
                    "url": "https://example.test/rule",
                    "source_name": "Agency",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "unconfirmed",
                    "quote": "A permit is required.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "trigger",
                    "value": "permit required",
                    "source_url": "https://example.test/rule",
                    "quote": "A permit is required.",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "needs_review"
    assert verdict.checks["currency"].pass_ is False
    assert any("currency failed" in reason for reason in verdict.distrust_reasons)
    assert any(ticket.failed_check == "currency" for ticket in verdict.repair_tickets)


def test_low_authority_needs_review_with_authority_repair_ticket():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-LOW-AUTH",
            "sources": [
                {
                    "url": "https://example.test/rule",
                    "source_name": "Unofficial Summary",
                    "authority_rank": 3,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "A permit is required.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "trigger",
                    "value": "permit required",
                    "source_url": "https://example.test/rule",
                    "quote": "A permit is required.",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "needs_review"
    assert any(ticket.failed_check == "authority" for ticket in verdict.repair_tickets)


def test_undecided_conclusion_needs_review_with_predicate_repair_ticket():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-UNDECIDED",
            "sources": [
                {
                    "url": "https://example.test/rule",
                    "source_name": "Agency",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "A permit is required.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "trigger",
                    "value": "permit required",
                    "source_url": "https://example.test/rule",
                    "quote": "A permit is required.",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "needs_review",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "needs_review"
    assert any(ticket.failed_check == "predicate_math" for ticket in verdict.repair_tickets)


def test_verify_evidence_creates_grounding_repair_ticket():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-ANY",
            "sources": [
                {
                    "url": "https://example.test/rule",
                    "source_name": "Agency",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "A facility storing 55 gallons or more must file.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "threshold",
                    "value": "55 gallons",
                    "source_url": "https://example.test/rule",
                    "quote": "100 gallons or more",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "fail"
    assert verdict.confidence == 0.35
    assert verdict.repair_tickets[0].failure_type == "grounding_failed"
    assert "does not trust" in verdict.distrust_reasons[0]


def test_ungrounded_result_includes_all_failed_check_repair_tickets():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-MULTI-FAIL",
            "sources": [
                {
                    "url": "https://example.test/rule",
                    "source_name": "Unofficial Summary",
                    "authority_rank": 3,
                    "fetched_at": "2020-01-01T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "stale",
                    "quote": "A facility storing 55 gallons or more must file.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "threshold",
                    "value": "55 gallons",
                    "source_url": "https://example.test/rule",
                    "quote": "100 gallons or more",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "needs_review",
            "uncertainties": [],
        }
    )

    failed_checks = {ticket.failed_check for ticket in verdict.repair_tickets}

    assert verdict.verdict == "fail"
    assert {"currency", "authority", "grounding", "predicate_math"} <= failed_checks


def test_needs_review_explains_why_work_is_not_trusted():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-ANY",
            "sources": [],
            "extracted_claims": [],
            "researcher_conclusion": "needs_review",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "needs_review"
    assert verdict.distrust_reasons
    assert "No source" in verdict.distrust_reasons[0]
    assert verdict.repair_tickets[0].failure_type == "source_failed"


def test_verify_evidence_grounds_claim_against_cited_second_source():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-MULTI",
            "sources": [
                {
                    "url": "https://example.test/first",
                    "source_name": "First Agency Source",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "This first source discusses a different rule.",
                },
                {
                    "url": "https://example.test/second",
                    "source_name": "Second Agency Source",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "A facility storing 55 gallons or more must file.",
                },
            ],
            "extracted_claims": [
                {
                    "field": "threshold",
                    "value": "55 gallons",
                    "source_url": "https://example.test/second",
                    "quote": "55 gallons or more",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "pass"
    assert verdict.checks["grounding"].pass_ is True


def test_verify_evidence_missing_cited_source_fails_closed_with_repair_ticket():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-MISSING-SOURCE",
            "sources": [
                {
                    "url": "https://example.test/first",
                    "source_name": "Agency",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "A facility storing 55 gallons or more must file.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "threshold",
                    "value": "55 gallons",
                    "source_url": "https://example.test/missing",
                    "quote": "55 gallons or more",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "needs_review"
    assert verdict.repair_tickets[0].failure_type == "source_failed"
    assert "cited source" in verdict.distrust_reasons[0]


def test_verify_evidence_missing_claim_source_url_fails_closed():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-NO-CLAIM-URL",
            "sources": [
                {
                    "url": "https://example.test/first",
                    "source_name": "Agency",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "A facility storing 55 gallons or more must file.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "threshold",
                    "value": "55 gallons",
                    "quote": "55 gallons or more",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    assert verdict.verdict == "needs_review"
    assert verdict.repair_tickets[0].failure_type == "source_failed"
    assert "source_url" in verdict.distrust_reasons[0]


def test_public_json_serialization_uses_aliases():
    verdict = verify_evidence(
        {
            "hypothesis_id": "H-ALIAS",
            "sources": [
                {
                    "url": "https://example.test/rule",
                    "source_name": "Agency",
                    "authority_rank": 1,
                    "fetched_at": "2026-01-02T00:00:00Z",
                    "effective_date": None,
                    "currency_status": "current",
                    "quote": "A permit is required.",
                }
            ],
            "extracted_claims": [
                {
                    "field": "trigger",
                    "value": "permit required",
                    "source_url": "https://example.test/rule",
                    "quote": "A permit is required.",
                    "confidence": 0.9,
                }
            ],
            "researcher_conclusion": "applies",
            "uncertainties": [],
        }
    )

    verdict_json = verdict.model_dump_json()
    signal_json = ConsistencySignal(samples=3, stable_samples=2).model_dump_json()

    assert '"pass"' in verdict_json
    assert '"pass_"' not in verdict_json
    assert '"stableSamples"' in signal_json
    assert '"stable_samples"' not in signal_json


def test_verify_evidence_accepts_ts_style_scope_bundle_signature():
    scope = {"run_id": "run_1"}
    bundle = {
        "hypothesis_id": "H-NOVEL",
        "sources": [
            {
                "url": "https://example.test/rule",
                "source_name": "Agency",
                "authority_rank": 1,
                "fetched_at": "2026-01-02T00:00:00Z",
                "effective_date": None,
                "currency_status": "current",
                "quote": "A permit is required.",
            }
        ],
        "extracted_claims": [
            {
                "field": "trigger",
                "value": "permit required",
                "source_url": "https://example.test/rule",
                "quote": "A permit is required.",
                "confidence": 0.9,
            }
        ],
        "researcher_conclusion": "applies",
        "uncertainties": [],
    }

    verdict = verify_evidence(scope, bundle, {"samples": 3, "stableSamples": 3})

    assert verdict.verdict == "pass"
