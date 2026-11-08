from app.lending import (
    AUTO_DESK,
    DESKTOP_REVIEW,
    PHYSICAL,
    max_eligible_loan,
    max_ltv_for,
    route,
)


def valuation(label="High", value=10_000_000, low=9_000_000, warnings=None):
    return {
        "estimated_value_inr": value,
        "low_estimate_inr": low,
        "confidence": {"label": label},
        "coverage_warnings": warnings or [],
    }


def test_rbi_housing_ltv_slabs():
    assert max_ltv_for(2_500_000, "Apartment") == 0.90
    assert max_ltv_for(5_000_000, "Apartment") == 0.80
    assert max_ltv_for(9_000_000, "Villa") == 0.75
    assert max_ltv_for(5_000_000, "Office Space") == 0.60


def test_max_eligible_loan_respects_slab_boundaries():
    # Rs 40 lakh property: 90% would be 36 lakh, above the 30 lakh slab, so 80% applies.
    assert max_eligible_loan(4_000_000, "Apartment") == 3_200_000
    # Rs 30 lakh property: 90% = 27 lakh stays in the first slab.
    assert max_eligible_loan(3_000_000, "Apartment") == 2_700_000
    assert max_eligible_loan(10_000_000, "Retail Shop") == 6_000_000


def test_high_confidence_with_evidence_goes_to_desk():
    decision = route(valuation(), comparable_count=5, property_type="Apartment", loan_amount=5_000_000)
    assert decision["routing"] == AUTO_DESK
    assert decision["physical_visit_avoided"] is True
    assert decision["lending"]["risk_band"] == "Low"
    assert decision["human_review_required"] is True


def test_low_confidence_or_out_of_coverage_needs_site_visit():
    assert route(valuation(label="Low"), 5, "Apartment", None)["routing"] == PHYSICAL
    out = route(valuation(warnings=["City outside coverage"]), 5, "Apartment", None)
    assert out["routing"] == PHYSICAL


def test_thin_evidence_or_medium_confidence_goes_to_desktop_review():
    assert route(valuation(), 1, "Apartment", None)["routing"] == DESKTOP_REVIEW
    assert route(valuation(label="Medium"), 5, "Apartment", None)["routing"] == DESKTOP_REVIEW


def test_high_value_property_always_gets_site_visit():
    big = valuation(value=60_000_000, low=55_000_000)
    assert route(big, 8, "Villa", None)["routing"] == PHYSICAL


def test_ltv_breach_is_high_risk_and_not_auto_desk():
    decision = route(valuation(low=4_000_000), 5, "Apartment", loan_amount=3_900_000)
    assert decision["lending"]["ltv_pct"] > decision["lending"]["max_ltv_pct"]
    assert decision["lending"]["risk_band"] == "High"
    assert decision["routing"] == DESKTOP_REVIEW
