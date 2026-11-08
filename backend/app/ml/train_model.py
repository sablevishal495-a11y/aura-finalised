"""Train AURA's valuation model and write the artifact the API serves.

Pipeline:
  1. Load property attributes (structured) and locality signals (government guideline rate,
     metro distance, infrastructure score, satellite green cover, market trend) and merge
     them on (city, locality) - the same merge the API performs at valuation time.
  2. Split 70 / 15 / 15 into train / calibration / test.
  3. Train a LightGBM point model on log(value) and a second LightGBM model that predicts the
     size of the point model's error for each property (from out-of-fold residuals), then
     calibrate the band on the calibration split (normalised split-conformal) so the stated
     90% range actually covers ~90% of unseen properties.
  4. Benchmark on the untouched test split against two baselines lenders already use:
       * rate-card AVM:   locality median rate per sq.ft. x area
       * guideline rate:  government guideline (circle) rate x area
     reporting MAE, MAPE, and PPE10 / PPE20 (share of estimates within +/-10% / 20%).
  5. Save model, metrics, per-segment error analysis and locality table to the artifact.

All current data is SYNTHETIC_DEMO; the metrics prove the pipeline works, not market accuracy.

Run:  python -m app.ml.train_model   (from the backend directory)
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.demo.generate_data import data_dir

MODEL_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = MODEL_DIR / "property_valuation_model.joblib"

CATEGORICAL = ["city", "locality", "property_type", "furnishing_status"]
NUMERIC = [
    "area_sqft",
    "bedrooms",
    "bathrooms",
    "property_age_years",
    "floor_number",
    "guideline_rate_per_sqft_inr",
    "metro_distance_km",
    "infra_score",
    "green_cover_pct",
    "market_trend_yoy_pct",
]
FEATURES = CATEGORICAL + NUMERIC
LOCALITY_FEATURES = NUMERIC[5:]
TARGET = "estimated_value_inr"
INTERVAL_LEVEL = 0.90
MIN_SCALE = 0.01


def make_pipeline(**lgbm_params) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
            ("numeric", "passthrough", NUMERIC),
        ]
    )
    params = {"n_estimators": 500, "learning_rate": 0.04, "num_leaves": 31,
              "min_child_samples": 15, "random_state": 42, "verbosity": -1, **lgbm_params}
    regressor = LGBMRegressor(**params)
    return Pipeline(steps=[("preprocessor", preprocessor), ("regressor", regressor)])


def accuracy(actual: np.ndarray, predicted: np.ndarray) -> dict:
    ape = np.abs(predicted - actual) / actual
    return {
        "mae_inr": float(np.mean(np.abs(predicted - actual))),
        "rmse_inr": float(np.sqrt(np.mean((predicted - actual) ** 2))),
        "mape_pct": float(np.mean(ape) * 100),
        "median_ape_pct": float(np.median(ape) * 100),
        "ppe10_pct": float(np.mean(ape <= 0.10) * 100),
        "ppe20_pct": float(np.mean(ape <= 0.20) * 100),
        "r2": float(1 - np.sum((actual - predicted) ** 2) / np.sum((actual - actual.mean()) ** 2)),
    }


def load_training_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    demo = data_dir() / "demo"
    properties = pd.read_csv(demo / "synthetic_properties.csv")
    localities = pd.read_csv(demo / "locality_features.csv")

    # Cleaning: only labelled synthetic rows, valid targets/areas, plausible ranges.
    df = properties[properties["data_source"] == "SYNTHETIC_DEMO"].copy()
    df = df.dropna(subset=["area_sqft", TARGET, "city", "locality", "property_type"])
    df = df[(df["area_sqft"] > 0) & (df[TARGET] > 0)]
    df = df[df["property_age_years"].between(0, 100) & df["floor_number"].between(0, 200)]
    df = df.drop_duplicates(subset=["property_id"])

    merged = df.merge(
        localities.drop(columns=["data_source"]), on=["city", "locality"], how="left", validate="m:1"
    )
    missing = merged[LOCALITY_FEATURES].isna().any(axis=1).sum()
    if missing:
        raise ValueError(f"{missing} properties have no locality signals after the merge.")
    return merged, localities


def main() -> None:
    df, localities = load_training_frame()
    print(f"Training rows after cleaning and merge: {len(df)}")

    train, rest = train_test_split(df, test_size=0.30, random_state=42)
    calib, test = train_test_split(rest, test_size=0.50, random_state=42)

    y_train = np.log(train[TARGET].to_numpy())
    point = make_pipeline().fit(train[FEATURES], y_train)

    # Uncertainty: a second model learns how large the point model's error tends to be for a
    # given property (out-of-fold residuals), so the range is wider for riskier properties.
    oof = cross_val_predict(make_pipeline(), train[FEATURES], y_train, cv=5)
    scale = make_pipeline(n_estimators=300).fit(train[FEATURES], np.abs(y_train - oof))

    # Split-conformal calibration on held-out data: choose the multiplier so the stated
    # 90% range really contains ~90% of unseen properties.
    y_calib = np.log(calib[TARGET].to_numpy())
    calib_scale = np.maximum(scale.predict(calib[FEATURES]), MIN_SCALE)
    scores = np.abs(y_calib - point.predict(calib[FEATURES])) / calib_scale
    n = len(scores)
    q_level = min(1.0, np.ceil((n + 1) * INTERVAL_LEVEL) / n)
    conformal_q = float(np.quantile(scores, q_level, method="higher"))

    actual = test[TARGET].to_numpy()
    log_pred = point.predict(test[FEATURES])
    predicted = np.exp(log_pred)
    test_scale = np.maximum(scale.predict(test[FEATURES]), MIN_SCALE)
    low = np.exp(log_pred - conformal_q * test_scale)
    high = np.exp(log_pred + conformal_q * test_scale)
    coverage = float(np.mean((actual >= low) & (actual <= high)) * 100)
    half_width = (high - low) / (2 * predicted)

    # Baselines.
    train_rates = train.assign(rate=train[TARGET] / train["area_sqft"])
    locality_rate = train_rates.groupby(["city", "locality", "property_type"])["rate"].median()
    city_rate = train_rates.groupby(["city", "property_type"])["rate"].median()
    rate_card = np.array([
        locality_rate.get((r.city, r.locality, r.property_type), city_rate.get((r.city, r.property_type)))
        * r.area_sqft
        for r in test.itertuples()
    ])
    guideline = (test["guideline_rate_per_sqft_inr"] * test["area_sqft"]).to_numpy()

    metrics = accuracy(actual, predicted)
    baselines = {
        "rate_card_avm": {"name": "Rate-card AVM (locality median rate x area)", **accuracy(actual, rate_card)},
        "guideline_rate": {"name": "Government guideline rate x area", **accuracy(actual, guideline)},
    }

    segments = []
    for column in ("city", "property_type"):
        for value, idx in test.groupby(column).groups.items():
            mask = test.index.isin(idx)
            segments.append({
                "dimension": column,
                "segment": str(value),
                "test_rows": int(mask.sum()),
                **{k: v for k, v in accuracy(actual[mask], predicted[mask]).items()
                   if k in ("mape_pct", "ppe10_pct", "ppe20_pct")},
                "interval_coverage_pct": float(np.mean((actual[mask] >= low[mask]) & (actual[mask] <= high[mask])) * 100),
            })

    trained_at = datetime.now(timezone.utc)
    fingerprint = hashlib.sha256(pd.util.hash_pandas_object(df[FEATURES + [TARGET]]).values.tobytes()).hexdigest()[:8]
    model_version = f"aura-lgbm-{trained_at:%Y%m%d}-{fingerprint}"

    artifact = {
        "model": point,
        "scale_model": scale,
        "conformal_q": conformal_q,
        "min_scale": MIN_SCALE,
        "interval_level": INTERVAL_LEVEL,
        "target_transform": "log",
        "features": FEATURES,
        "categorical_features": CATEGORICAL,
        "locality_features": LOCALITY_FEATURES,
        "target": TARGET,
        "data_source": "SYNTHETIC_DEMO",
        "model_version": model_version,
        "trained_at": trained_at.isoformat(),
        "training_rows": int(len(train)),
        "calibration_rows": int(len(calib)),
        "test_rows": int(len(test)),
        "locality_table": localities.drop(columns=["data_source"]).to_dict(orient="records"),
        "coverage": {
            "cities": sorted(df["city"].unique().tolist()),
            "property_types": sorted(df["property_type"].unique().tolist()),
            "localities": {c: sorted(g["locality"].unique().tolist()) for c, g in df.groupby("city")},
        },
        "metrics": {
            **metrics,
            # Back-compat keys used by older clients.
            "mae": metrics["mae_inr"],
            "rmse": metrics["rmse_inr"],
            "interval_coverage_pct": coverage,
            "median_interval_half_width_pct": float(np.median(half_width) * 100),
        },
        "baselines": baselines,
        "segments": segments,
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH, compress=3)

    print(f"\nModel {model_version}")
    print(f"{'':28}{'MAPE':>8}{'PPE10':>8}{'PPE20':>8}")
    for label, m in [("AURA LightGBM", metrics)] + [(b["name"][:27], b) for b in baselines.values()]:
        print(f"{label:28}{m['mape_pct']:7.1f}%{m['ppe10_pct']:7.1f}%{m['ppe20_pct']:7.1f}%")
    print(f"90% interval coverage on test: {coverage:.1f}%  (median half-width {np.median(half_width) * 100:.1f}%)")
    print(f"Saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
