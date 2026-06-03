from __future__ import annotations

import math

from research_core.confidence import (
    EPS,
    MAX_CONFIDENCE,
    WEIGHTS,
    authority_score,
    confidence_from_checks,
    consistency_factor,
    corroboration_score,
    currency_score,
    grounding_score,
    predicate_score,
    score_confidence,
)


def _score(**overrides) -> float:
    base = dict(grounding=1.0, authority=1.0, corroboration=1.0, currency=1.0, predicate=1.0)
    base.update(overrides)
    return score_confidence(**base)["score"]


# --- dimension scorers are continuous, not boolean -----------------------------


def test_grounding_verbatim_substring_is_full_credit():
    src = "A facility storing\n55\tgallons   or more must file."
    assert grounding_score("55 gallons or more", src) == 1.0


def test_grounding_is_graded_between_verbatim_and_absent():
    src = "A facility storing 55 gallons or more must file."
    verbatim = grounding_score("55 gallons or more", src)
    altered = grounding_score("100 gallons or more", src)  # fabricated number
    absent = grounding_score("entirely unrelated text", src)
    assert verbatim == 1.0
    assert absent < altered < verbatim
    # A fabricated legal number is categorically untrusted, not "75% fine".
    assert altered < 0.3


def test_authority_score_is_graded_by_rank():
    assert authority_score(1) > authority_score(2) > authority_score(3) > authority_score(None) - 0.001
    assert authority_score(1) == 1.0
    assert authority_score(3) < 0.2


def test_corroboration_saturates_with_more_sources():
    s0, s1, s2, s3 = (corroboration_score(n) for n in (0, 1, 2, 3))
    assert s0 < s1 < s2 < s3
    assert s1 >= 0.6  # a single authoritative primary source is already strong
    # diminishing returns: each additional source adds less than the previous
    assert (s2 - s1) < (s1 - s0)
    assert (s3 - s2) < (s2 - s1)


def test_currency_grades_dated_current_above_undated_above_stale():
    assert currency_score("current", dated=True) > currency_score("current", dated=False)
    assert currency_score("current", dated=False) > currency_score("unconfirmed")
    assert currency_score("unconfirmed") > currency_score("stale")


def test_predicate_rewards_quantified_conclusion():
    assert predicate_score("applies", quantified=True) > predicate_score("applies", quantified=False)
    assert predicate_score("applies", quantified=False) > predicate_score("conditional")
    assert predicate_score("needs_review") < 0.5


def test_consistency_factor_scales_with_stable_fraction():
    assert consistency_factor(0, 0) == 1.0  # no sampling is neutral
    assert consistency_factor(3, 3) == 1.0
    assert math.isclose(consistency_factor(3, 1), 0.70 + 0.30 * (1 / 3))
    assert consistency_factor(3, 1) < consistency_factor(3, 2) < consistency_factor(3, 3)


# --- the aggregate is a real weighted geometric mean ---------------------------


def test_weights_sum_to_one():
    assert math.isclose(sum(WEIGHTS.values()), 1.0)


def test_perfect_evidence_scores_near_max_and_passes_gate():
    score = score_confidence(
        grounding=1.0, authority=1.0, corroboration=corroboration_score(3),
        currency=1.0, predicate=1.0, consistency=(3, 3),
    )["score"]
    assert score >= 0.9
    assert score <= MAX_CONFIDENCE


def test_single_authoritative_primary_source_still_passes_gate():
    # grounded, rank-1, current+dated, decided conclusion, ONE source -> should clear 0.9
    score = _score(corroboration=corroboration_score(1), predicate=0.90)
    assert score >= 0.9


def test_geometric_mean_is_conjunctive_low_grounding_dominates():
    # Dropping the high-weight grounding dimension hurts far more than dropping a
    # low-weight one by the same amount -> the mean is conjunctive, not averaging.
    drop_grounding = _score(grounding=0.2)
    drop_currency = _score(currency=0.2)
    assert drop_grounding < drop_currency
    # and a near-zero grounding drags the whole score toward zero (fail-closed)
    assert _score(grounding=0.02) < 0.4


def test_score_is_monotonic_in_every_dimension():
    for dim in ("grounding", "authority", "corroboration", "currency", "predicate"):
        lo = _score(**{dim: 0.3})
        hi = _score(**{dim: 0.9})
        assert hi > lo, dim


def test_score_clamped_and_rounded_two_decimals():
    score = score_confidence(
        grounding=0.0, authority=0.0, corroboration=0.0, currency=0.0, predicate=0.0,
    )["score"]
    assert 0.05 <= score <= MAX_CONFIDENCE
    assert round(score, 2) == score


def test_breakdown_is_transparent_and_auditable():
    out = score_confidence(
        grounding=0.8, authority=0.65, corroboration=0.85, currency=1.0, predicate=0.9,
    )
    assert out["method"] == "weighted_geometric_mean"
    assert set(out["dimensions"]) == set(WEIGHTS)
    # Reconstruct the score from the published log-contributions -> truly numerical.
    log_sum = sum(d["log_contribution"] for d in out["dimensions"].values())
    assert math.isclose(out["raw_geometric_mean"], math.exp(log_sum), rel_tol=1e-3)


# --- legacy boolean-check adapter reduces sensibly ------------------------------


def test_from_checks_failed_grounding_is_low_and_below_gate():
    checks = {
        "currency": {"pass": True, "reason": "dated"},
        "authority": {"pass": True, "reason": "official"},
        "grounding": {"pass": False, "reason": "quote missing"},
        "predicate_math": {"pass": True, "reason": "decided"},
    }
    score = confidence_from_checks(checks)["score"]
    assert score < 0.5
    # all-pass version scores much higher than the grounding-failed one
    all_pass = {k: {"pass": True, "reason": "ok"} for k in checks}
    assert confidence_from_checks(all_pass)["score"] > score + 0.3
