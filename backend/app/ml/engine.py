"""Valuation engine: loads the trained artifact once and serves predictions + explanations."""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

log = logging.getLogger("aura.engine")
MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "property_valuation_model.joblib"

FEATURE_LABELS = {
    "city": "City",
    "locality": "Locality",
    "property_type": "Property type",
    "furnishing_status": "Furnishing",
    "area_sqft": "Built-up area",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "property_age_years": "Property age",
    "floor_number": "Floor",
    "guideline_rate_per_sqft_inr": "Govt guideline rate",
    "metro_distance_km": "Distance to metro",
    "infra_score": "Infrastructure pipeline",
    "green_cover_pct": "Green cover (satellite)",
    "market_trend_yoy_pct": "Market trend (YoY)",
}
FEATURE_SOURCES = {
    "guideline_rate_per_sqft_inr": "Government records",
    "metro_distance_km": "Geo-spatial",
    "infra_score": "Infrastructure developments",
    "green_cover_pct": "Satellite imagery",
    "market_trend_yoy_pct": "Market trends",
}

# Relative half-width of the calibrated 90% band -> confidence label.
HIGH_CONFIDENCE_MAX = 0.15
MEDIUM_CONFIDENCE_MAX = 0.25


class ValuationEngine:
    def __init__(self, path: Path = MODEL_PATH):
        self.available = False
        self.error = ""
        try:
            # Trusted input: the artifact is produced by app/ml/train_model.py and shipped in
            # this repo. Never point this loader at a user-supplied file.
            self.artifact = joblib.load(path)
            self.model = self.artifact["model"]
            self.preprocessor = self.model.named_steps["preprocessor"]
            self.explainer = shap.TreeExplainer(self.model.named_steps["regressor"])
            self.features = self.artifact["features"]
            self.localities = pd.DataFrame(self.artifact["locality_table"])
            self.available = True
        except Exception as exc:  # noqa: BLE001 - surfaced through /model-info and 503s
            self.artifact = {}
            self.error = f"{type(exc).__name__}: {exc}"
            log.exception("Could not load the valuation model")

    @property
    def model_version(self) -> str:
        return self.artifact.get("model_version", "unavailable")

    @property
    def data_source(self) -> str:
        return self.artifact.get("data_source", "UNKNOWN")

    def locality_signals(self, city: str, locality: str) -> tuple[dict, bool]:
        """Alternative-data features for a locality; falls back to the city median."""
        table = self.localities
        match = table[(table["city"].str.casefold() == city.casefold())
                      & (table["locality"].str.casefold() == locality.casefold())]
        cols = self.artifact["locality_features"]
        if len(match):
            return {c: float(match.iloc[0][c]) for c in cols}, True
        city_rows = table[table["city"].str.casefold() == city.casefold()]
        base = city_rows if len(city_rows) else table
        return {c: float(base[c].median()) for c in cols}, False

    def coverage_warnings(self, prop: dict, locality_known: bool) -> list[str]:
        cov = self.artifact["coverage"]
        warnings = []
        if prop["city"].casefold() not in {c.casefold() for c in cov["cities"]}:
            warnings.append(f"City '{prop['city']}' is outside the model's training coverage.")
        elif not locality_known:
            warnings.append(f"Locality '{prop['locality']}' has no locality signals; city medians were used.")
        if prop["property_type"].casefold() not in {t.casefold() for t in cov["property_types"]}:
            warnings.append(f"Property type '{prop['property_type']}' is outside the model's training coverage.")
        return warnings

    def _frame(self, rows: list[dict]) -> tuple[pd.DataFrame, list[bool]]:
        records, known = [], []
        for prop in rows:
            signals, is_known = self.locality_signals(prop["city"], prop["locality"])
            records.append({**prop, **signals})
            known.append(is_known)
        return pd.DataFrame(records, columns=self.features), known

    def value(self, rows: list[dict], explain: bool = True) -> list[dict]:
        frame, known = self._frame(rows)
        log_pred = self.model.predict(frame)
        scale = np.maximum(self.artifact["scale_model"].predict(frame), self.artifact["min_scale"])
        band = self.artifact["conformal_q"] * scale
        pred, low, high = np.exp(log_pred), np.exp(log_pred - band), np.exp(log_pred + band)

        shap_rows = None
        if explain:
            transformed = self.preprocessor.transform(frame)
            shap_rows = np.asarray(self.explainer.shap_values(transformed))
            names = [str(n) for n in self.preprocessor.get_feature_names_out()]
            base_log = float(np.ravel(self.explainer.expected_value)[0])

        results = []
        for i, prop in enumerate(rows):
            half_width = float((high[i] - low[i]) / (2 * pred[i]))
            warnings = self.coverage_warnings(prop, known[i])
            if warnings or half_width > MEDIUM_CONFIDENCE_MAX:
                label = "Low"
            elif half_width > HIGH_CONFIDENCE_MAX:
                label = "Medium"
            else:
                label = "High"
            score = int(round(100 * float(np.clip(1 - half_width / 0.5, 0, 1))))
            if warnings:
                score = min(score, 30)

            result = {
                "estimated_value_inr": round(float(pred[i]), 2),
                "low_estimate_inr": round(float(low[i]), 2),
                "high_estimate_inr": round(float(high[i]), 2),
                "rate_per_sqft_inr": round(float(pred[i]) / float(prop["area_sqft"]), 2),
                "confidence": {
                    "label": label,
                    "score": score,
                    "interval_level_pct": int(self.artifact["interval_level"] * 100),
                    "relative_half_width_pct": round(half_width * 100, 1),
                    "method": (
                        "Per-property error model calibrated with split-conformal prediction "
                        f"(held-out coverage {self.artifact['metrics']['interval_coverage_pct']:.1f}% "
                        "on synthetic test data)."
                    ),
                },
                "coverage_warnings": warnings,
                "locality_signals": [
                    {
                        "feature": c,
                        "label": FEATURE_LABELS[c],
                        "source": FEATURE_SOURCES[c],
                        "value": float(frame.iloc[i][c]),
                        "matched_locality": known[i],
                    }
                    for c in self.artifact["locality_features"]
                ],
            }
            if explain:
                result["explainability"] = self._explain(shap_rows[i], names, base_log, frame.iloc[i], float(pred[i]))
            results.append(result)
        return results

    def _explain(self, values, names, base_log, row, predicted) -> dict:
        grouped: dict[str, float] = {}
        for name, value in zip(names, values):
            original = name.split("__", 1)[1]
            for cat in self.artifact["categorical_features"]:
                if original.startswith(cat + "_"):
                    original = cat
                    break
            grouped[original] = grouped.get(original, 0.0) + float(value)

        factors = []
        for feature, phi in grouped.items():
            raw = row[feature]
            display = raw if isinstance(raw, str) else f"{float(raw):g}"
            factors.append({
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature),
                "value": display,
                "source": FEATURE_SOURCES.get(feature, "Property attributes"),
                "impact_pct": round((np.exp(phi) - 1) * 100, 1),
                # INR the estimate would move by if this factor were at its average.
                "impact_inr": round(predicted * (1 - np.exp(-phi)), 0),
                "direction": "increases_estimate" if phi > 0 else "decreases_estimate" if phi < 0 else "neutral",
                "_abs": abs(phi),
            })
        factors.sort(key=lambda f: f["_abs"], reverse=True)
        for f in factors:
            f.pop("_abs")
        return {
            "method": "SHAP TreeExplainer on the LightGBM model (log-value space)",
            "available": True,
            "base_value_inr": round(float(np.exp(base_log)), 0),
            "top_factors": factors[:6],
            "all_factors": factors,
            "notice": "SHAP shows how each input moved this estimate relative to an average property. "
                      "It is not proof of causation.",
        }


engine = ValuationEngine()
