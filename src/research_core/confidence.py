"""Numerical confidence scoring for research findings.

The verifier used to derive confidence from check *boxes*: start at 0.9 and take the
minimum hard cap of whichever boolean checks failed. That throws away real information —
a rank-1 primary source and a rank-2 secondary one both just "passed authority"; one
corroborating source and four looked identical; 51%-stable and 99%-stable self-consistency
were the same.

This module computes confidence as an actual number from continuous evidence signals:

  * grounding     — how verbatim the cited quote is in the source (1.0 == exact substring)
  * authority     — graded by source authority rank (1 curated > 2 gov > 3 other)
  * corroboration — saturating function of how many authoritative sources agree
  * currency      — graded: dated-current > current > unconfirmed > stale
  * predicate     — a grounded (and ideally quantified) applicability conclusion
  * consistency   — fraction of self-consistency samples that agreed

The dimensions combine with a WEIGHTED GEOMETRIC MEAN, then a consistency damping factor:

    score = (Π dimension_i ** weight_i) * consistency_factor

The geometric mean is conjunctive — a near-zero in any single dimension drags the whole
score toward zero (fail-closed), which a weighted arithmetic mean would not do. Every call
returns the full per-dimension breakdown so the number is auditable, not a black box.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping


# Dimension weights (sum to 1.0). Grounding dominates: an altered legal quote is the
# single most disqualifying defect, so it carries the most log-weight.
WEIGHTS: dict[str, float] = {
    "grounding": 0.42,
    "authority": 0.20,
    "corroboration": 0.14,
    "currency": 0.12,
    "predicate": 0.12,
}

EPS = 0.02  # log floor so a 0.0 dimension yields a strong-but-finite penalty, not -inf.
MIN_CONFIDENCE = 0.05
MAX_CONFIDENCE = 0.97


def grounding_score(claim_quote: str | None, source_text: str | None) -> float:
    """How faithfully the claim's quote is present in the cited source, in [0, 1].

    A verbatim substring (whitespace-normalized) scores 1.0 — full grounding. Anything
    else means the agent paraphrased or altered the legal text, which for a citation is
    categorically untrustworthy, so it is capped very low and graded only by how much
    contiguous text actually survived."""
    claim = _normalize(claim_quote)
    source = _normalize(source_text)
    if not claim or not source:
        return 0.0
    if claim in source:
        return 1.0
    overlap = _contiguous_token_overlap(claim, source)
    # Not verbatim: the quote was modified. Floor it (0.04..0.14 by surviving overlap).
    return round(0.04 + 0.10 * overlap, 4)


def authority_score(authority_rank: Any) -> float:
    """Graded source authority. Rank 1 (curated CA/federal authority) is full credit;
    rank 2 (other .gov/.mil) is trusted but lower; rank >= 3 (non-authoritative) is
    near-zero; an unknown/missing rank is treated as unverified."""
    rank = _coerce_rank(authority_rank)
    if rank is None:
        return 0.10
    if rank <= 1:
        return 1.0
    if rank <= 2:
        return 0.65
    if rank <= 3:
        return 0.15
    return 0.08


def corroboration_score(authoritative_source_count: int) -> float:
    """Saturating reward for independent authoritative sources that agree. A single
    authoritative primary source (citing the rule itself) is already strong; each extra
    source adds diminishing assurance: 0 -> 0.2, 1 -> 0.70, 2 -> 0.85, 3 -> 0.925."""
    n = max(0, int(authoritative_source_count))
    if n <= 0:
        return 0.20
    return round(1.0 - 0.30 * (0.5 ** (n - 1)), 4)


def currency_score(status: Any, *, dated: bool = False) -> float:
    """Graded recency/currency of the cited source."""
    text = (str(status).strip().lower() if status is not None else "")
    if text == "current":
        return 1.0 if dated else 0.85
    if text in {"", "unconfirmed", "unknown", "none"}:
        return 0.50
    if text == "stale":
        return 0.20
    return 0.40


def predicate_score(conclusion: Any, *, quantified: bool = False) -> float:
    """Graded strength of the applicability conclusion. A decided conclusion (applies /
    does_not_apply) is strong, and a quantified one (an actual computed threshold) is
    full credit; a conditional determination is partial; no conclusion is weak."""
    text = (str(conclusion).strip().lower() if conclusion is not None else "")
    if text in {"applies", "does_not_apply"}:
        return 1.0 if quantified else 0.90
    if text in {"conditional", "both", "depends"}:
        return 0.80 if quantified else 0.70
    return 0.25


def consistency_factor(samples: int, stable_samples: int) -> float:
    """Damping factor in [0.7, 1.0] from self-consistency sampling. No samples is neutral
    (1.0) — absence of repeated sampling should not by itself lower confidence."""
    if samples <= 0:
        return 1.0
    ratio = _clamp(stable_samples / samples, 0.0, 1.0)
    return 0.70 + 0.30 * ratio


def score_confidence(
    *,
    grounding: float,
    authority: float,
    corroboration: float,
    currency: float,
    predicate: float,
    consistency: tuple[int, int] | Mapping[str, Any] | Any | None = None,
) -> dict[str, Any]:
    """Combine continuous dimension scores (each already in [0, 1]) into a single
    confidence number via a weighted geometric mean, then apply consistency damping.
    Returns the score plus a per-dimension breakdown (score, weight, log-contribution)."""
    dims = {
        "grounding": _unit(grounding),
        "authority": _unit(authority),
        "corroboration": _unit(corroboration),
        "currency": _unit(currency),
        "predicate": _unit(predicate),
    }

    log_sum = 0.0
    breakdown: dict[str, dict[str, float]] = {}
    for name, value in dims.items():
        weight = WEIGHTS[name]
        contribution = weight * math.log(max(value, EPS))
        log_sum += contribution
        breakdown[name] = {
            "score": round(value, 4),
            "weight": weight,
            "log_contribution": round(contribution, 4),
        }

    base = math.exp(log_sum)
    factor = _consistency_factor_from(consistency)
    score = _clamp(base * factor, MIN_CONFIDENCE, MAX_CONFIDENCE)

    return {
        "score": _round2(score),
        "method": "weighted_geometric_mean",
        "dimensions": breakdown,
        "consistency_factor": round(factor, 4),
        "raw_geometric_mean": round(base, 4),
    }


def confidence_from_checks(
    checks: Mapping[str, Any],
    consistency: tuple[int, int] | Mapping[str, Any] | Any | None = None,
) -> dict[str, Any]:
    """Adapter for the legacy boolean-check shape: map each passed/failed check to a
    continuous dimension score (pass -> 1.0, fail -> that dimension's low floor) and run
    the same numerical model over whichever dimensions are present. Lets the verifier's
    needs_review path keep its check-based call site while sharing one scorer."""
    fail_floor = {"grounding": 0.06, "authority": 0.15, "currency": 0.20, "predicate_math": 0.25}
    present = {
        "grounding": "grounding",
        "authority": "authority",
        "currency": "currency",
        "predicate_math": "predicate",
    }
    dims: dict[str, float] = {}
    for check_name, dim_name in present.items():
        if check_name not in checks:
            continue
        passed = _check_passed(checks[check_name])
        dims[dim_name] = 1.0 if passed else fail_floor[check_name]

    if not dims:
        return score_confidence(
            grounding=0.5, authority=0.5, corroboration=0.5, currency=0.5, predicate=0.5,
            consistency=consistency,
        )

    # Renormalize the present dimensions' weights so they sum to 1 (corroboration is not
    # a boolean check, so it is absent from this legacy path).
    weight_total = sum(WEIGHTS[d] for d in dims)
    log_sum = sum(
        (WEIGHTS[d] / weight_total) * math.log(max(score, EPS)) for d, score in dims.items()
    )
    factor = _consistency_factor_from(consistency)
    score = _clamp(math.exp(log_sum) * factor, MIN_CONFIDENCE, MAX_CONFIDENCE)
    return {
        "score": _round2(score),
        "method": "weighted_geometric_mean_from_checks",
        "dimensions": {d: round(s, 4) for d, s in dims.items()},
        "consistency_factor": round(factor, 4),
    }


# --- internals ---------------------------------------------------------------


def _normalize(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _contiguous_token_overlap(claim: str, source: str) -> float:
    """Longest run of consecutive claim tokens that appears contiguously in the source,
    as a fraction of the claim's tokens. Rewards surviving verbatim spans, not scattered
    word matches (so a fabricated number breaks the run rather than being averaged away)."""
    claim_tokens = claim.split()
    if not claim_tokens:
        return 0.0
    source_text = " " + source + " "
    best = 0
    n = len(claim_tokens)
    for start in range(n):
        for end in range(n, start + best, -1):
            span = " ".join(claim_tokens[start:end])
            if (" " + span + " ") in source_text:
                best = max(best, end - start)
                break
    return best / n


def _unit(value: Any) -> float:
    try:
        return _clamp(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return 0.0


def _consistency_factor_from(
    consistency: tuple[int, int] | Mapping[str, Any] | Any | None,
) -> float:
    if consistency is None:
        return 1.0
    if isinstance(consistency, tuple) and len(consistency) == 2:
        return consistency_factor(int(consistency[0]), int(consistency[1]))
    samples = _get(consistency, "samples")
    stable = _get(consistency, "stable_samples")
    if stable is None:
        stable = _get(consistency, "stableSamples")
    if samples is None:
        return 1.0
    try:
        return consistency_factor(int(samples), int(stable or 0))
    except (TypeError, ValueError):
        return 1.0


def _check_passed(check: Any) -> bool:
    if isinstance(check, Mapping):
        return bool(check.get("pass", check.get("pass_", False)))
    return bool(getattr(check, "pass_", False))


def _coerce_rank(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        rank = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(rank) or math.isinf(rank):
        return None
    return rank


def _get(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _round2(value: float) -> float:
    return math.floor(value * 100 + 0.5) / 100
