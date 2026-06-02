from __future__ import annotations

import math
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError


CONFIDENCE_GATE = 0.9
FailureType = Literal[
    "grounding_failed",
    "source_failed",
    "missing_fact",
    "invalid_json",
    "conflict",
    "low_confidence",
]

FAIL_CAP: dict[str, float] = {
    "currency": 0.3,
    "grounding": 0.35,
    "authority": 0.5,
    "predicate_math": 0.55,
    "cross_source": 0.7,
}
DEFAULT_FAIL_CAP = 0.6
BASE_ALL_PASS = 0.9
PER_EXTRA_FAIL_PENALTY = 0.05
MIN_CONFIDENCE = 0.05
MAX_CONFIDENCE = 0.97


class VerificationCheck(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    pass_: bool = Field(alias="pass")
    reason: str


class ConsistencySignal(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    samples: int
    stable_samples: int = Field(alias="stableSamples")


class RepairTicket(BaseModel):
    ticket_id: str
    hypothesis_id: str
    failure_type: FailureType
    failed_check: str
    observed_problem: str
    repair_action: str
    max_attempts_remaining: int


class VerificationVerdict(BaseModel):
    hypothesis_id: str
    verdict: Literal["pass", "fail", "needs_review"]
    checks: dict[str, VerificationCheck]
    confidence: float = Field(ge=0, le=1)
    repair_tickets: list[RepairTicket]
    distrust_reasons: list[str] = Field(default_factory=list)


def quote_grounded(quote: str | None, source: str | None) -> bool:
    normalized_quote = _normalize_whitespace(quote)
    normalized_source = _normalize_whitespace(source)
    return bool(normalized_quote and normalized_source and normalized_quote in normalized_source)


def authority_rank_check(authority_rank: Any, max_rank: int = 2) -> VerificationCheck:
    rank = _coerce_rank(authority_rank)
    if rank is None:
        return VerificationCheck(pass_=False, reason="no authority rank supplied")
    if rank <= max_rank:
        return VerificationCheck(
            pass_=True,
            reason=f"official or high-authority source (authority rank {rank:g})",
        )
    return VerificationCheck(
        pass_=False,
        reason=f"source authority rank {rank:g} is below the required rank <= {max_rank}",
    )


def currency_check(source: Any) -> VerificationCheck:
    status = _currency_status(source)
    if status == "current":
        fetched_at = _first_date(_get(source, "fetched_at"))
        effective_date = _first_date(_get(source, "effective_date"))
        dated_text = f" dated {effective_date or fetched_at}" if fetched_at or effective_date else ""
        return VerificationCheck(
            pass_=True,
            reason=f"source currency explicitly marked current{dated_text}",
        )
    if status in {"stale", "unconfirmed"}:
        return VerificationCheck(
            pass_=False,
            reason=f"source currency is {status}; current law cannot be proven",
        )
    if status is not None:
        return VerificationCheck(
            pass_=False,
            reason=f"source currency status {status!r} is not recognized as current",
        )
    return VerificationCheck(
        pass_=False,
        reason="no explicit current currency_status or currency proof was supplied",
    )


def predicate_check(researcher_conclusion: Any) -> VerificationCheck:
    if researcher_conclusion in {"applies", "does_not_apply"}:
        return VerificationCheck(
            pass_=True,
            reason=f"researcher reached a grounded conclusion: {researcher_conclusion}",
        )
    return VerificationCheck(
        pass_=False,
        reason="researcher could not reach a grounded conclusion",
    )


def compute_confidence(
    checks: Mapping[str, VerificationCheck | Mapping[str, Any]],
    consistency: ConsistencySignal | Mapping[str, Any] | None = None,
) -> float:
    failed = [(name, check) for name, check in checks.items() if not _check_passed(check)]

    confidence = BASE_ALL_PASS
    for name, _check in failed:
        confidence = min(confidence, FAIL_CAP.get(name, DEFAULT_FAIL_CAP))
    if len(failed) > 1:
        confidence -= PER_EXTRA_FAIL_PENALTY * (len(failed) - 1)

    signal = _consistency_signal(consistency)
    if signal and signal.samples > 0:
        stability = _clamp(signal.stable_samples / signal.samples, 0, 1)
        confidence *= 0.6 + 0.4 * stability

    return _round2(_clamp(confidence, MIN_CONFIDENCE, MAX_CONFIDENCE))


def make_repair_ticket(
    *,
    hypothesis_id: str,
    failure_type: FailureType,
    failed_check: str,
    observed_problem: str,
    repair_action: str,
    max_attempts_remaining: int = 1,
    ticket_suffix: str = "001",
) -> RepairTicket:
    return RepairTicket(
        ticket_id=f"R-{hypothesis_id}-{ticket_suffix}",
        hypothesis_id=hypothesis_id,
        failure_type=failure_type,
        failed_check=failed_check,
        observed_problem=observed_problem,
        repair_action=repair_action,
        max_attempts_remaining=max_attempts_remaining,
    )


def verify_evidence(
    scope_or_bundle: Mapping[str, Any] | Any,
    bundle: Mapping[str, Any] | Any | None = None,
    consistency: ConsistencySignal | Mapping[str, Any] | None = None,
) -> VerificationVerdict:
    # Accept both the Python primitive style, verify_evidence(bundle), and the
    # TypeScript-shaped style, verifyEvidence(scope, bundle, consistency).
    if bundle is None:
        bundle = scope_or_bundle

    hypothesis_id = str(_get(bundle, "hypothesis_id") or "unknown")
    sources = _as_list(_get(bundle, "sources"))
    if not sources:
        return needs_review_verdict(
            hypothesis_id,
            "source_failed",
            "No source was returned by the worker.",
        )

    claims = _as_list(_get(bundle, "extracted_claims"))
    claim = claims[0] if claims else None
    if claim is None:
        return needs_review_verdict(
            hypothesis_id,
            "source_failed",
            "No extracted claim was returned by the worker.",
        )

    claim_source_url = str(_get(claim, "source_url") or "").strip()
    if not claim_source_url:
        return needs_review_verdict(
            hypothesis_id,
            "source_failed",
            "Extracted claim has no source_url, so the verifier cannot select cited evidence.",
        )

    source = _source_by_url(sources, claim_source_url)
    if source is None:
        return needs_review_verdict(
            hypothesis_id,
            "source_failed",
            f"Claim cited source_url {claim_source_url!r}, but no matching cited source was returned.",
        )

    source_quote = str(_get(source, "quote") or "")
    claim_quote = str(_get(claim, "quote") or "")
    grounded = quote_grounded(claim_quote, source_quote)
    conclusion = _get(bundle, "researcher_conclusion")

    checks = {
        "currency": currency_check(source),
        "authority": authority_rank_check(_get(source, "authority_rank")),
        "grounding": VerificationCheck(
            pass_=grounded,
            reason=(
                "extracted claim quote appears in the cited source quote"
                if grounded
                else "extracted claim is not grounded in the cited source quote"
            ),
        ),
        "predicate_math": predicate_check(conclusion),
    }
    confidence = compute_confidence(checks, consistency)
    distrust_reasons = _distrust_reasons(checks)

    if not grounded:
        return VerificationVerdict(
            hypothesis_id=hypothesis_id,
            verdict="fail",
            checks=checks,
            confidence=confidence,
            repair_tickets=_repair_tickets_for_failed_checks(hypothesis_id, checks),
            distrust_reasons=distrust_reasons,
        )

    all_checks_pass = all(check.pass_ for check in checks.values())
    if all_checks_pass and confidence >= CONFIDENCE_GATE:
        return VerificationVerdict(
            hypothesis_id=hypothesis_id,
            verdict="pass",
            checks=checks,
            confidence=confidence,
            repair_tickets=[],
            distrust_reasons=[],
        )

    tickets = _repair_tickets_for_failed_checks(hypothesis_id, checks)
    if confidence < CONFIDENCE_GATE:
        tickets.append(
            make_repair_ticket(
                hypothesis_id=hypothesis_id,
                failure_type="low_confidence",
                failed_check="confidence",
                observed_problem=(
                    f"Verifier confidence {confidence:.2f} is below the "
                    f"{CONFIDENCE_GATE:.2f} gate."
                ),
                repair_action=(
                    "re-research toward stronger, current, directly quoted evidence "
                    "or request missing user facts"
                ),
                ticket_suffix="conf",
            )
        )

    return VerificationVerdict(
        hypothesis_id=hypothesis_id,
        verdict="needs_review",
        checks=checks,
        confidence=confidence,
        repair_tickets=tickets,
        distrust_reasons=distrust_reasons
        or [
            "Verifier does not trust the work because confidence is below the "
            f"{CONFIDENCE_GATE:.2f} gate."
        ],
    )


def needs_review_verdict(
    hypothesis_id: str,
    failure_type: FailureType,
    reason: str,
) -> VerificationVerdict:
    checks = {
        "currency": VerificationCheck(pass_=False, reason="no verified source to date"),
        "authority": VerificationCheck(
            pass_=failure_type != "source_failed",
            reason=(
                "authority could be evaluated or source failure was explicit"
                if failure_type != "source_failed"
                else reason
            ),
        ),
        "grounding": VerificationCheck(pass_=False, reason=reason),
        "predicate_math": VerificationCheck(pass_=False, reason=reason),
    }
    repair_tickets = []
    if failure_type == "source_failed":
        repair_tickets.append(
            make_repair_ticket(
                hypothesis_id=hypothesis_id,
                failure_type="source_failed",
                failed_check="source",
                observed_problem=reason,
                repair_action="rerun research to fetch and cite a matching source_url for each extracted claim",
            )
        )

    return VerificationVerdict(
        hypothesis_id=hypothesis_id,
        verdict="needs_review",
        checks=checks,
        confidence=compute_confidence(checks),
        repair_tickets=repair_tickets,
        distrust_reasons=[f"Verifier does not trust the work: {reason}"],
    )


def repair_evidence(ticket: RepairTicket | Mapping[str, Any]) -> dict[str, Any]:
    try:
        repair_ticket = (
            ticket if isinstance(ticket, RepairTicket) else RepairTicket.model_validate(ticket)
        )
    except ValidationError:
        return {
            "hypothesis_id": "unknown",
            "sources": [],
            "extracted_claims": [],
            "researcher_conclusion": "needs_review",
            "uncertainties": ["Repair ticket was invalid and must be regenerated."],
        }
    return {
        "hypothesis_id": repair_ticket.hypothesis_id,
        "sources": [],
        "extracted_claims": [],
        "researcher_conclusion": "needs_review",
        "uncertainties": [
            f"Repair requires re-running the researcher: {repair_ticket.repair_action}"
        ],
    }


def _normalize_whitespace(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _check_passed(check: VerificationCheck | Mapping[str, Any]) -> bool:
    if isinstance(check, VerificationCheck):
        return check.pass_
    return bool(check.get("pass", check.get("pass_", False)))


def _distrust_reasons(checks: Mapping[str, VerificationCheck]) -> list[str]:
    return [
        f"Verifier does not trust the work because {name} failed: {check.reason}"
        for name, check in checks.items()
        if not check.pass_
    ]


def _consistency_signal(
    consistency: ConsistencySignal | Mapping[str, Any] | None,
) -> ConsistencySignal | None:
    if consistency is None:
        return None
    if isinstance(consistency, ConsistencySignal):
        return consistency
    try:
        return ConsistencySignal.model_validate(consistency)
    except ValidationError:
        return None


def _first_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def _get(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _currency_status(source: Any) -> str | None:
    raw_status = _get(source, "currency_status")
    if raw_status is None:
        raw_status = _get(source, "currency")
    if raw_status is None:
        return None
    return str(raw_status).strip().lower()


def _source_by_url(sources: list[Any], claim_source_url: str) -> Any | None:
    for source in sources:
        if str(_get(source, "url") or "").strip() == claim_source_url:
            return source
    return None


def _repair_tickets_for_failed_checks(
    hypothesis_id: str,
    checks: Mapping[str, VerificationCheck],
) -> list[RepairTicket]:
    tickets: list[RepairTicket] = []
    for name, check in checks.items():
        if check.pass_:
            continue
        spec = _repair_spec_for_failed_check(name)
        if spec is None:
            continue
        failure_type, action = spec
        tickets.append(
            make_repair_ticket(
                hypothesis_id=hypothesis_id,
                failure_type=failure_type,
                failed_check=name,
                observed_problem=check.reason,
                repair_action=action,
                ticket_suffix=name,
            )
        )
    return tickets


def _repair_spec_for_failed_check(
    failed_check: str,
) -> tuple[FailureType, str] | None:
    if failed_check == "grounding":
        return (
            "grounding_failed",
            "rerun extraction constrained to verbatim source text",
        )
    if failed_check == "authority":
        return (
            "source_failed",
            "find official/high-authority source and rerun verification",
        )
    if failed_check == "currency":
        return (
            "source_failed",
            "prove current source status or refetch current law",
        )
    if failed_check == "predicate_math":
        return (
            "missing_fact",
            "resolve threshold facts and reach a grounded conclusion",
        )
    return None


def _coerce_rank(value: Any) -> float | None:
    if value is None:
        return None
    try:
        rank = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(rank) or math.isinf(rank):
        return None
    return rank


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _round2(value: float) -> float:
    return math.floor(value * 100 + 0.5) / 100
