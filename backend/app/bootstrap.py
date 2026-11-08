"""Create the schema and load the labelled synthetic demo data on first start-up."""
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.db import engine
from app.demo.generate_data import data_dir

log = logging.getLogger("aura.bootstrap")
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"

PROPERTY_COLUMNS = [
    "property_id", "city", "locality", "property_type", "segment", "area_sqft", "bedrooms",
    "bathrooms", "property_age_years", "floor_number", "furnishing_status",
    "rate_per_sqft_inr", "estimated_value_inr", "data_source",
]


def _statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


async def bootstrap() -> None:
    async with engine.begin() as conn:
        for statement in _statements(SCHEMA_FILE.read_text()):
            await conn.execute(text(statement))

    try:
        demo = data_dir() / "demo"
    except FileNotFoundError:
        log.warning("No data/ directory found; skipping demo seed.")
        return

    async with engine.begin() as conn:
        has_properties = (await conn.execute(text("SELECT EXISTS (SELECT 1 FROM properties)"))).scalar()
        if not has_properties and (demo / "synthetic_properties.csv").exists():
            df = pd.read_csv(demo / "synthetic_properties.csv")[PROPERTY_COLUMNS]
            await conn.execute(
                text(f"INSERT INTO properties ({', '.join(PROPERTY_COLUMNS)}) "
                     f"VALUES ({', '.join(':' + c for c in PROPERTY_COLUMNS)})"),
                df.to_dict(orient="records"),
            )
            log.warning("Seeded %d synthetic demo properties.", len(df))

        has_demo_comps = (await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM property_comparables WHERE data_source = 'SYNTHETIC_DEMO')"
        ))).scalar()
        if not has_demo_comps and (demo / "synthetic_comparables.csv").exists():
            source_id = (await conn.execute(text("""
                INSERT INTO data_sources (source_name, source_type, license_notes)
                VALUES ('SYNTHETIC_DEMO', 'SYNTHETIC',
                        'Generated demo transactions. Not real market evidence; never use for lending.')
                RETURNING source_id
            """))).scalar_one()
            comps = pd.read_csv(demo / "synthetic_comparables.csv")
            comps["transaction_date"] = pd.to_datetime(comps["transaction_date"]).dt.date
            comps["rate_per_sqft_inr"] = comps["transaction_value_inr"] / comps["area_sqft"]
            comps["source_id"] = source_id
            comps["data_source"] = "SYNTHETIC_DEMO"
            await conn.execute(
                text("""
                    INSERT INTO property_comparables (
                        source_id, city, locality, property_type, transaction_date, area_sqft,
                        transaction_value_inr, rate_per_sqft_inr, data_source, source_record_id, is_verified
                    ) VALUES (
                        :source_id, :city, :locality, :property_type, :transaction_date, :area_sqft,
                        :transaction_value_inr, :rate_per_sqft_inr, :data_source, :source_record_id, FALSE
                    )
                """),
                comps.drop(columns=["source_name"]).to_dict(orient="records"),
            )
            log.warning("Seeded %d synthetic demo comparables.", len(comps))
