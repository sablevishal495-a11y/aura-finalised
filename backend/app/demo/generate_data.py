"""Generate AURA's synthetic demo datasets.

Everything written here is SYNTHETIC and labelled ``SYNTHETIC_DEMO``. It exists so the
end-to-end pipeline (merge -> train -> explain -> route) can be demonstrated without
licensed data. Never use it for a real lending decision.

Outputs (in the data directory, ``data/demo``):
  * locality_features.csv     - one row per locality: the "alternative data" layer
                                (government guideline rate, metro distance, infrastructure
                                pipeline, satellite green cover, market trend)
  * synthetic_properties.csv  - property attributes + value labels (residential + commercial)
  * synthetic_comparables.csv - comparable "transactions" used as valuation evidence

Run:  python -m app.demo.generate_data   (from the backend directory)
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
PROPERTY_ROWS = 3000
COMPARABLE_ROWS = 900

rng = np.random.default_rng(SEED)

LOCALITIES = {
    "Mumbai": ["Andheri", "Powai", "Borivali", "Thane"],
    "Pune": ["Hinjewadi", "Wakad", "Kothrud", "Baner"],
    "Bengaluru": ["Whitefield", "Electronic City", "Indiranagar", "Hebbal"],
    "Delhi": ["Dwarka", "Rohini", "Saket", "Vasant Kunj"],
    "Hyderabad": ["Gachibowli", "Kukatpally", "Miyapur", "HITEC City"],
    "Indore": ["Vijay Nagar", "Rau", "Palasia", "Super Corridor"],
}

# Illustrative base market rates (INR / sq.ft.) - synthetic, not market data.
CITY_BASE_RATE = {
    "Mumbai": 18000,
    "Pune": 8500,
    "Bengaluru": 10000,
    "Delhi": 12000,
    "Hyderabad": 7500,
    "Indore": 4500,
}

# property_type -> (segment, share, area range, rate multiplier, noise sigma)
PROPERTY_TYPES = {
    "Apartment": ("Residential", 0.50, (450, 2500), 1.00, 0.06),
    "Independent House": ("Residential", 0.15, (800, 3500), 1.08, 0.09),
    "Villa": ("Residential", 0.08, (1800, 6000), 1.25, 0.12),
    "Office Space": ("Commercial", 0.15, (300, 5000), 1.35, 0.10),
    "Retail Shop": ("Commercial", 0.12, (150, 2000), 1.60, 0.14),
}

FURNISHING = ["Unfurnished", "Semi-Furnished", "Furnished"]
FURNISHING_MULTIPLIER = {"Unfurnished": 1.00, "Semi-Furnished": 1.05, "Furnished": 1.12}


def data_dir() -> Path:
    """data/ at the repo root locally, /app/data inside the backend container."""
    if os.getenv("AURA_DATA_DIR"):
        return Path(os.environ["AURA_DATA_DIR"])
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "data", here.parents[3] / "data"):
        if (candidate / "demo").exists():
            return candidate
    raise FileNotFoundError("Could not find the data/ directory; set AURA_DATA_DIR.")


def build_locality_features() -> pd.DataFrame:
    rows = []
    for city, names in LOCALITIES.items():
        for name in names:
            # Guideline (circle) rates usually sit below market rates.
            guideline_rate = round(CITY_BASE_RATE[city] * float(rng.uniform(0.55, 0.80)), -1)
            rows.append(
                {
                    "city": city,
                    "locality": name,
                    "guideline_rate_per_sqft_inr": guideline_rate,
                    "metro_distance_km": round(float(rng.uniform(0.3, 12.0)), 1),
                    "infra_score": round(float(rng.uniform(3.0, 9.5)), 1),
                    "green_cover_pct": round(float(rng.uniform(5.0, 35.0)), 1),
                    "market_trend_yoy_pct": round(float(rng.uniform(-2.0, 12.0)), 1),
                    "data_source": "SYNTHETIC_DEMO",
                }
            )
    return pd.DataFrame(rows)


def locality_multiplier(loc: pd.Series) -> float:
    return float(
        (1 + 0.035 * (loc["infra_score"] - 6.0))
        * (1 - 0.018 * (loc["metro_distance_km"] - 4.0))
        * (1 + 0.004 * (loc["green_cover_pct"] - 20.0))
        * (1 + 0.006 * loc["market_trend_yoy_pct"])
    )


def sample_property(loc: pd.Series, property_type: str) -> dict:
    segment, _, (area_lo, area_hi), type_mult, sigma = PROPERTY_TYPES[property_type]
    area_sqft = int(rng.integers(area_lo, area_hi))
    property_age_years = int(rng.integers(0, 35))
    furnishing = str(rng.choice(FURNISHING, p=[0.35, 0.40, 0.25]))

    if segment == "Residential":
        bedrooms = int(np.clip(round(area_sqft / 550 + rng.normal(0, 0.6)), 1, 6))
        bathrooms = int(np.clip(bedrooms - int(rng.integers(0, 2)), 1, 6))
    else:
        bedrooms = 0
        bathrooms = int(rng.integers(1, 3))

    if property_type in ("Apartment", "Office Space"):
        floor_number = int(rng.integers(0, 30))
    elif property_type == "Retail Shop":
        floor_number = int(rng.integers(0, 3))
    else:
        floor_number = 0

    age_mult = max(0.65, 1 - property_age_years * 0.008)
    floor_mult = 1 + min(floor_number, 15) * 0.003
    if property_type == "Retail Shop":
        floor_mult = 1.0 if floor_number == 0 else 0.82  # ground-floor frontage premium
    # Very large units sell at a lower rate per sq.ft.
    size_mult = 1 - 0.04 * np.log(area_sqft / ((area_lo + area_hi) / 2))
    # Noise is higher for heterogeneous types and in thinly-traded (low-infra) localities,
    # so the model's confidence genuinely varies between properties.
    local_sigma = sigma * (1.25 if loc["infra_score"] < 5 else 1.0)
    noise = float(np.exp(rng.normal(0, local_sigma)))

    rate = (
        CITY_BASE_RATE[loc["city"]]
        * locality_multiplier(loc)
        * type_mult
        * age_mult
        * floor_mult
        * FURNISHING_MULTIPLIER[furnishing]
        * size_mult
        * noise
    )
    return {
        "city": loc["city"],
        "locality": loc["locality"],
        "property_type": property_type,
        "segment": segment,
        "area_sqft": area_sqft,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "property_age_years": property_age_years,
        "floor_number": floor_number,
        "furnishing_status": furnishing,
        "rate_per_sqft_inr": round(rate, 2),
        "value_inr": round(area_sqft * rate, 2),
    }


def main() -> None:
    localities = build_locality_features()
    type_names = list(PROPERTY_TYPES)
    type_probs = [PROPERTY_TYPES[t][1] for t in type_names]

    properties = []
    for i in range(PROPERTY_ROWS):
        loc = localities.iloc[int(rng.integers(0, len(localities)))]
        record = sample_property(loc, str(rng.choice(type_names, p=type_probs)))
        record["estimated_value_inr"] = record.pop("value_inr")
        properties.append(
            {"property_id": f"AURA-DEMO-{i + 1:05d}", **record, "data_source": "SYNTHETIC_DEMO"}
        )

    comparables = []
    today = date(2026, 10, 31)
    for i in range(COMPARABLE_ROWS):
        loc = localities.iloc[int(rng.integers(0, len(localities)))]
        record = sample_property(loc, str(rng.choice(type_names, p=type_probs)))
        comparables.append(
            {
                "city": record["city"],
                "locality": record["locality"],
                "property_type": record["property_type"],
                "transaction_date": (today - timedelta(days=int(rng.integers(0, 540)))).isoformat(),
                "area_sqft": record["area_sqft"],
                "transaction_value_inr": record["value_inr"],
                "source_record_id": f"SYN-COMP-{i + 1:05d}",
                "source_name": "SYNTHETIC_DEMO",
            }
        )

    out = data_dir() / "demo"
    localities.to_csv(out / "locality_features.csv", index=False)
    pd.DataFrame(properties).to_csv(out / "synthetic_properties.csv", index=False)
    pd.DataFrame(comparables).to_csv(out / "synthetic_comparables.csv", index=False)
    print(f"Wrote {len(localities)} localities, {len(properties)} properties, "
          f"{len(comparables)} comparables to {out}")


if __name__ == "__main__":
    main()
