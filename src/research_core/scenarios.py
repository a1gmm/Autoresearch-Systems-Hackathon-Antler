from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from research_core.models import (
    FactProvenance,
    InformationRequest,
    Scenario,
    ScenarioAssumption,
)


class InformationGapOptions(BaseModel):
    request: InformationRequest
    block_immediately: bool
    scenarios: list[Scenario]
    suggestions: list[str]


def scenarios_for_missing_fact(
    request: InformationRequest,
    *,
    provided_estimate: Any | None = None,
    unit: str | None = None,
) -> list[Scenario]:
    if provided_estimate is not None:
        return [
            Scenario(
                id=f"{_slug(request.field)}-provided-estimate",
                label="expected",
                assumptions=[
                    ScenarioAssumption(
                        field=request.field,
                        value=provided_estimate,
                        unit=unit or _infer_unit(request),
                        provenance=FactProvenance.PROVIDED_ESTIMATE,
                    )
                ],
                rationale="User provided this as an estimate, so it is valid input but not exact.",
                affects=request.blocks,
            )
        ]

    if _looks_like_quantity(request):
        values = _quantity_values(request)
        unit = unit or _infer_unit(request)
        rationales = {
            "low": "Below the likely decision threshold for this missing quantity.",
            "expected": "At the likely planning threshold for this missing quantity.",
            "high": "Above the likely decision threshold for this missing quantity.",
        }
        return [
            Scenario(
                id=f"{_slug(request.field)}-{label}",
                label=label,
                assumptions=[
                    ScenarioAssumption(
                        field=request.field,
                        value=value,
                        unit=unit,
                        provenance=FactProvenance.AGENT_INFERRED,
                    )
                ],
                rationale=rationales[label],
                affects=request.blocks,
            )
            for label, value in values
        ]

    return [
        Scenario(
            id=f"{_slug(request.field)}-expected",
            label="expected",
            assumptions=[
                ScenarioAssumption(
                    field=request.field,
                    value="unknown",
                    unit=unit,
                    provenance=FactProvenance.AGENT_INFERRED,
                )
            ],
            rationale="Missing fact has no numeric scenario pattern yet.",
            affects=request.blocks,
        )
    ]


def information_gap_options(
    request: InformationRequest,
    *,
    user_does_not_know: bool,
) -> InformationGapOptions:
    scenarios = scenarios_for_missing_fact(request) if user_does_not_know else []
    return InformationGapOptions(
        request=request,
        block_immediately=not user_does_not_know,
        scenarios=scenarios,
        suggestions=_suggestions_for(request) if user_does_not_know else [],
    )


def is_valid_user_input(assumption: ScenarioAssumption | dict[str, Any]) -> bool:
    provenance = (
        assumption.provenance
        if isinstance(assumption, ScenarioAssumption)
        else assumption.get("provenance")
    )
    return provenance in {
        FactProvenance.PROVIDED_EXACT,
        FactProvenance.PROVIDED_ESTIMATE,
        FactProvenance.AGENT_SUGGESTED_USER_ACCEPTED,
    }


def _quantity_values(request: InformationRequest) -> list[tuple[str, float]]:
    threshold = _domain_threshold(request)
    if threshold is None:
        threshold = _extract_number(request.why_needed) or _extract_number(request.question)
    if threshold is None and "hmbp" in " ".join(request.blocks).lower():
        threshold = 55
    if threshold is None:
        threshold = 100

    low = max(0, threshold - max(1, threshold * 0.1))
    high = threshold + max(1, threshold * 0.1)
    return [
        ("low", _clean_number(low)),
        ("expected", _clean_number(threshold)),
        ("high", _clean_number(high)),
    ]


def _domain_threshold(request: InformationRequest) -> float | None:
    text = _request_text(request)
    blocks = " ".join(request.blocks).lower()
    if (
        "disturbance_acres" in text or "acre" in text
    ) and "stormwater" in blocks and "construction" in blocks:
        return 1
    return None


def _suggestions_for(request: InformationRequest) -> list[str]:
    if _looks_like_quantity(request):
        return [
            "Check container sizes, SDS inventory, purchase records, or the largest expected on-site amount.",
            "If exact amounts are unavailable, provide a conservative estimate and mark it as an estimate.",
        ]
    return [
        "Provide the best available estimate or document where this fact can be confirmed.",
        "If the fact is truly unknown, continue with scenario assumptions for comparison.",
    ]


def _looks_like_quantity(request: InformationRequest) -> bool:
    text = _request_text(request)
    return any(
        token in text
        for token in (
            "disturbance_acres",
            "acre",
            "how many",
            "quantity",
            "amount",
            "volume",
            "kg_per_month",
        )
    )


def _infer_unit(request: InformationRequest) -> str | None:
    text = _request_text(request)
    if "gallon" in text or " gal" in text:
        return "gal"
    if "kg" in text or "kilogram" in text:
        return "kg"
    if "acre" in text:
        return "acre"
    return None


def _extract_number(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def _request_text(request: InformationRequest) -> str:
    return f"{request.field} {request.question} {request.why_needed}".lower()


def _clean_number(value: float) -> float | int:
    rounded = round(value, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "missing-fact"
