from __future__ import annotations

from typing import Any

from research_core.models import InformationRequest, Scenario


def synthesize_result(
    *,
    run_id: str,
    scope: Any,
    plan: Any,
    evidence: list[dict[str, Any]],
    verdicts: list[Any],
    information_requests: list[InformationRequest],
    scenarios: list[Scenario],
    recall_floor_met: bool = True,
) -> dict[str, Any]:
    verdict_dump = [_dump(verdict) for verdict in verdicts]
    failed_or_review = [
        verdict
        for verdict in verdict_dump
        if verdict.get("verdict") in {"fail", "needs_review"}
    ]
    trusted = [
        verdict
        for verdict in verdict_dump
        if verdict.get("verdict") == "pass"
    ]

    if information_requests and not evidence:
        status = "needs_information"
        reasons = [
            f"{request.field}: {request.why_needed}"
            for request in information_requests
        ]
    elif failed_or_review or not recall_floor_met:
        status = "needs_review"
        reasons = _review_reasons(failed_or_review, recall_floor_met)
    else:
        status = "verified"
        reasons = ["All researched hypotheses passed verification."]

    return {
        "run_id": run_id,
        "determination": {
            "status": status,
            "trusted_hypotheses": [item["hypothesis_id"] for item in trusted],
            "needs_review_hypotheses": [
                item.get("hypothesis_id") for item in failed_or_review
            ],
            "reasons": reasons,
        },
        "report": {
            "summary": _summary(status, trusted, failed_or_review, information_requests),
            "coverage": _coverage(plan),
            "evidence_count": len(evidence),
            "scenario_count": len(scenarios),
        },
        "information_requests": [_dump(request) for request in information_requests],
        "scenarios": [_dump(scenario) for scenario in scenarios],
        "evidence": evidence,
        "verdicts": verdict_dump,
        "scope": _dump(scope),
    }


def _review_reasons(
    failed_or_review: list[dict[str, Any]],
    recall_floor_met: bool,
) -> list[str]:
    reasons: list[str] = []
    for verdict in failed_or_review:
        distrust = verdict.get("distrust_reasons") or []
        if distrust:
            reasons.extend(str(reason) for reason in distrust)
        else:
            reasons.append(
                "Verifier does not trust "
                f"{verdict.get('hypothesis_id', 'unknown hypothesis')}."
            )
    if not recall_floor_met:
        reasons.append(
            "Recall floor was not met: not enough planned hypotheses produced "
            "verified evidence."
        )
    return reasons or ["Verifier does not trust the work after bounded retries."]


def _summary(
    status: str,
    trusted: list[dict[str, Any]],
    failed_or_review: list[dict[str, Any]],
    information_requests: list[InformationRequest],
) -> str:
    if status == "needs_information":
        return (
            "The run needs additional project facts before a trusted "
            "determination can be made."
        )
    if status == "needs_review":
        return (
            f"{len(trusted)} hypotheses passed verification, but "
            f"{len(failed_or_review)} require review before relying on the result."
        )
    return f"{len(trusted)} hypotheses passed verification."


def _coverage(plan: Any) -> list[dict[str, Any]]:
    statuses = getattr(plan, "coverage_family_statuses", [])
    return [_dump(status) for status in statuses]


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
