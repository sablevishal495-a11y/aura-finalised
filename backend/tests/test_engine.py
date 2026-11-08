import pytest

from app.ml.engine import engine

PROPERTY = {
    "city": "Pune",
    "locality": "Baner",
    "property_type": "Apartment",
    "area_sqft": 1100,
    "bedrooms": 2,
    "bathrooms": 2,
    "property_age_years": 4,
    "floor_number": 7,
    "furnishing_status": "Semi-Furnished",
}


def test_model_artifact_loads():
    assert engine.available, engine.error
    assert engine.data_source == "SYNTHETIC_DEMO"
    assert engine.model_version.startswith("aura-lgbm-")


def test_valuation_has_value_range_confidence_and_factors():
    result = engine.value([PROPERTY])[0]
    assert result["low_estimate_inr"] < result["estimated_value_inr"] < result["high_estimate_inr"]
    assert result["confidence"]["label"] in {"High", "Medium", "Low"}
    assert 0 <= result["confidence"]["score"] <= 100
    factors = result["explainability"]["top_factors"]
    assert factors and all("impact_pct" in f and f["label"] for f in factors)
    # One-hot columns are grouped back into the original feature names.
    assert len({f["feature"] for f in result["explainability"]["all_factors"]}) == len(engine.features)
    assert result["coverage_warnings"] == []


def test_bigger_property_is_worth_more():
    small, large = engine.value([PROPERTY, {**PROPERTY, "area_sqft": 2200}], explain=False)
    assert large["estimated_value_inr"] > small["estimated_value_inr"]


@pytest.mark.parametrize("change", [{"city": "Jaipur", "locality": "Malviya Nagar"}, {"property_type": "Warehouse"}])
def test_out_of_coverage_is_flagged_low_confidence(change):
    result = engine.value([{**PROPERTY, **change}], explain=False)[0]
    assert result["coverage_warnings"]
    assert result["confidence"]["label"] == "Low"


def test_published_metrics_beat_baselines_on_synthetic_test_set():
    metrics = engine.artifact["metrics"]
    baselines = engine.artifact["baselines"]
    assert metrics["mape_pct"] < baselines["rate_card_avm"]["mape_pct"]
    assert metrics["mape_pct"] < baselines["guideline_rate"]["mape_pct"]
    assert 85 <= metrics["interval_coverage_pct"] <= 95
