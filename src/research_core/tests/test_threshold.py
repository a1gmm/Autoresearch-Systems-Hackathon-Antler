from __future__ import annotations

import math

from research_core.tools import compute_voc_threshold


def test_converts_mass_limit_to_usage_limit_like_alg_memo():
    # The ALG memo derives an actionable usage limit from VCAPCD Rule 23's 200 lb
    # ROC/12-month exemption: ~74 wt% ROC inks at ~9.20 lb/gal -> ~29 gal/period.
    result = compute_voc_threshold(
        voc_content=74,
        voc_content_unit="weight_percent",
        density=9.20,
        density_unit="lb/gal",
        mass_limit_lb=200,
    )

    assert result["ok"] is True
    assert result["status"] == "computed"
    assert math.isclose(result["voc_mass_per_volume"]["lb_per_gal"], 6.808, rel_tol=1e-3)
    assert math.isclose(result["usage_limit"]["gal"], 29.38, abs_tol=0.05)
    # The math is shown so the agent can quote it.
    assert any("200" in line and "6.8" in line for line in result["formula"])


def test_weight_fraction_without_density_is_an_error():
    result = compute_voc_threshold(
        voc_content=0.74,
        voc_content_unit="weight_fraction",
        mass_limit_lb=200,
    )

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"]["code"] == "density_required"


def test_accepts_concentration_in_grams_per_liter_without_density():
    # A coating rated at 250 g/L VOC: 250 g/L -> ~2.086 lb/gal; 200 lb / 2.086 ~= 95.9 gal.
    result = compute_voc_threshold(
        voc_content=250,
        voc_content_unit="g/L",
        mass_limit_lb=200,
    )

    assert result["ok"] is True
    assert math.isclose(result["voc_mass_per_volume"]["lb_per_gal"], 2.0864, rel_tol=1e-3)
    assert math.isclose(result["usage_limit"]["gal"], 95.86, abs_tol=0.1)


def test_estimates_emissions_from_usage_with_control_efficiency():
    # 50 gal of 6.808 lb/gal VOC material, 90% capture/control -> ~34 lb emitted.
    result = compute_voc_threshold(
        voc_content=74,
        voc_content_unit="weight_percent",
        density=9.20,
        density_unit="lb/gal",
        usage=50,
        usage_unit="gal",
        control_efficiency=0.90,
    )

    assert result["ok"] is True
    assert math.isclose(result["emissions"]["lb"], 34.04, abs_tol=0.1)
    assert "usage_limit" not in result  # no mass_limit_lb provided


def test_rejects_non_numeric_content():
    result = compute_voc_threshold(voc_content="lots", voc_content_unit="weight_percent")
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_argument"


def test_rejects_unknown_unit():
    result = compute_voc_threshold(voc_content=5, voc_content_unit="furlongs")
    assert result["ok"] is False
    assert result["error"]["code"] == "unknown_unit"


def test_rejects_out_of_range_control_efficiency():
    result = compute_voc_threshold(
        voc_content=74,
        voc_content_unit="weight_percent",
        density=9.2,
        usage=10,
        control_efficiency=1.5,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_argument"


def test_liters_usage_unit_is_converted():
    # 100 L == 26.417 gal; emissions track the gallon figure.
    result = compute_voc_threshold(
        voc_content=74,
        voc_content_unit="weight_percent",
        density=9.20,
        usage=100,
        usage_unit="L",
    )
    assert result["ok"] is True
    assert math.isclose(result["emissions"]["lb"], 26.417 * 6.808, rel_tol=1e-3)
