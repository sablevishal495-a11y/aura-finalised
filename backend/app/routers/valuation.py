"""Valuation API: single and batch valuations, audit log, PDF report and model card."""
from __future__ import annotations

import io
import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app.db import engine as db
from app.lending import route
from app.ml.engine import engine as valuation_engine

log = logging.getLogger("aura.valuation")
router = APIRouter(prefix="/api/valuation", tags=["Valuation"])

MAX_BATCH_ROWS = 1000
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
DISCLAIMER = (
    "Prototype estimate from a model trained on SYNTHETIC demo data. Not a certified valuation "
    "and not a lending decision; a credit officer must review before any use."
)


class ValuationRequest(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    locality: str = Field(min_length=1, max_length=100)
    property_type: str = Field(default="Apartment", min_length=1, max_length=50)
    area_sqft: float = Field(gt=0, le=50000)
    bedrooms: int = Field(default=2, ge=0, le=20)
    bathrooms: int = Field(default=2, ge=0, le=20)
    property_age_years: int = Field(default=0, ge=0, le=100)
    floor_number: int = Field(default=0, ge=0, le=200)
    furnishing_status: str = Field(default="Unfurnished", max_length=50)
    loan_amount_inr: float | None = Field(default=None, gt=0, le=10_000_000_000)

    def property_input(self) -> dict:
        data = self.model_dump(exclude={"loan_amount_inr"})
        for key in ("city", "locality", "property_type", "furnishing_status"):
            data[key] = " ".join(data[key].split())
        return data


def require_model() -> None:
    if not valuation_engine.available:
        raise HTTPException(status_code=503, detail="Valuation model is not available. Check the model artifact.")


async def fetch_comparables(prop: dict) -> list[dict]:
    query = text("""
        SELECT city, locality, property_type, transaction_date, area_sqft, transaction_value_inr,
               rate_per_sqft_inr, data_source, is_verified
        FROM property_comparables
        WHERE lower(city) = lower(:city) AND lower(locality) = lower(:locality)
          AND lower(property_type) = lower(:property_type)
        ORDER BY abs(area_sqft - :area_sqft), transaction_date DESC NULLS LAST
        LIMIT 8
    """)
    try:
        async with db.connect() as conn:
            rows = (await conn.execute(query, prop)).mappings().all()
    except Exception:  # noqa: BLE001 - the model estimate is still useful without evidence
        log.exception("Comparable lookup failed")
        return []
    return [
        {**dict(r), "transaction_date": r["transaction_date"].isoformat() if r["transaction_date"] else None}
        for r in rows
    ]


def comparable_evidence(comps: list[dict], area_sqft: float, model_value: float) -> dict:
    count = len(comps)
    verified = sum(1 for c in comps if c["is_verified"])
    if count:
        avg_rate = sum(float(c["rate_per_sqft_inr"]) for c in comps) / count
        comp_value = avg_rate * area_sqft
        gap_pct = (model_value - comp_value) / comp_value * 100
    else:
        avg_rate = comp_value = gap_pct = None
    return {
        "comparable_count": count,
        "verified_comparable_count": verified,
        "average_rate_per_sqft_inr": round(avg_rate, 2) if avg_rate else None,
        "comparable_estimate_inr": round(comp_value, 2) if comp_value else None,
        "model_vs_comparable_gap_pct": round(gap_pct, 1) if gap_pct is not None else None,
        "records": comps,
        "notice": (
            "Nearest comparable transactions by size in the same locality and property type. "
            "Synthetic demo records are unverified."
            if count else "No comparable transactions found for this locality and property type."
        ),
    }


def build_result(
    prop: dict, valued: dict, comps: list[dict], loan: float | None, latency_ms: float,
    comparable_count: int | None = None,
) -> dict:
    evidence = comparable_evidence(comps, prop["area_sqft"], valued["estimated_value_inr"])
    if comparable_count is not None:  # batch mode counts comparables without fetching rows
        evidence["comparable_count"] = comparable_count
    decision = route(valued, evidence["comparable_count"], prop["property_type"], loan)
    return {
        **valued,
        "property_input": prop,
        "model": "LightGBM",
        "model_version": valuation_engine.model_version,
        "data_source": valuation_engine.data_source,
        "comparables": evidence,
        "decision_support": decision,
        "latency_ms": round(latency_ms, 1),
        "disclaimer": DISCLAIMER,
    }


async def persist(results: list[dict], channel: str) -> bool:
    now = datetime.now(timezone.utc)
    rows = []
    for r in results:
        r["valuation_id"] = str(uuid4())
        r["valued_at"] = now.isoformat()
        rows.append({
            "valuation_id": r["valuation_id"],
            "created_at": now,
            "channel": channel,
            "model_version": r["model_version"],
            "property_input": json.dumps(r["property_input"]),
            "result": json.dumps(r, default=str),
            "estimated": r["estimated_value_inr"],
            "low": r["low_estimate_inr"],
            "high": r["high_estimate_inr"],
            "confidence": r["confidence"]["label"],
            "routing": r["decision_support"]["routing"],
            "latency": r["latency_ms"],
        })
    try:
        async with db.begin() as conn:
            await conn.execute(text("""
                INSERT INTO valuations (
                    valuation_id, created_at, channel, model_version, property_input, result,
                    estimated_value_inr, low_estimate_inr, high_estimate_inr, confidence_label,
                    routing, latency_ms
                ) VALUES (
                    :valuation_id, :created_at, :channel, :model_version, CAST(:property_input AS JSONB),
                    CAST(:result AS JSONB), :estimated, :low, :high, :confidence, :routing, :latency
                )
            """), rows)
        return True
    except Exception:  # noqa: BLE001
        log.exception("Could not store valuation audit record")
        for r in results:
            r["valuation_id"] = None
        return False


@router.post("/")
async def estimate_valuation(request: ValuationRequest):
    require_model()
    started = time.perf_counter()
    prop = request.property_input()
    valued = valuation_engine.value([prop])[0]
    comps = await fetch_comparables(prop)
    result = build_result(prop, valued, comps, request.loan_amount_inr, (time.perf_counter() - started) * 1000)
    result["audit_saved"] = await persist([result], "single")
    return result


@router.get("/model-info")
def model_info():
    if not valuation_engine.available:
        return {"available": False, "error": valuation_engine.error}
    a = valuation_engine.artifact
    return {
        "available": True,
        "model": "LightGBM gradient-boosted trees (value model + per-property error model)",
        "model_version": a["model_version"],
        "trained_at": a["trained_at"],
        "data_source": a["data_source"],
        "rows": {"train": a["training_rows"], "calibration": a["calibration_rows"], "test": a["test_rows"]},
        "features": [
            {"feature": f, "type": "categorical" if f in a["categorical_features"] else "numeric",
             "group": "Locality signal" if f in a["locality_features"] else "Property attribute"}
            for f in a["features"]
        ],
        "metrics": a["metrics"],
        "baselines": a["baselines"],
        "segments": a["segments"],
        "coverage": a["coverage"],
        "locality_table": a["locality_table"],
        "notice": "All metrics are measured on a held-out split of SYNTHETIC data. They show the "
                  "measurement method, not real-market accuracy.",
    }


@router.get("/history")
async def valuation_history(limit: int = Query(default=50, ge=1, le=200)):
    async with db.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT valuation_id, created_at, channel, model_version, property_input,
                   estimated_value_inr, low_estimate_inr, high_estimate_inr, confidence_label,
                   routing, latency_ms
            FROM valuations ORDER BY created_at DESC LIMIT :limit
        """), {"limit": limit})).mappings().all()
    return {"count": len(rows), "valuations": [dict(r) for r in rows]}


@router.post("/batch")
async def batch_valuation(file: UploadFile = File(...)):
    require_model()
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds the 5 MB limit.")
    try:
        df = pd.read_csv(io.BytesIO(content), dtype="string")
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Could not parse the CSV file.")
    if len(df) > MAX_BATCH_ROWS:
        raise HTTPException(status_code=413, detail=f"Batch is limited to {MAX_BATCH_ROWS} rows.")
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = {"city", "locality", "area_sqft"} - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV is missing required columns: {', '.join(sorted(missing))}")

    started = time.perf_counter()
    requests, errors = [], []
    for idx, row in df.iterrows():
        data = {k: v for k, v in row.items() if v is not None and not pd.isna(v) and str(v).strip() != ""}
        try:
            requests.append((int(idx) + 2, ValuationRequest(**data)))
        except ValidationError as exc:
            errors.append({"csv_row": int(idx) + 2, "errors": [f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()]})

    results = []
    if requests:
        props = [r.property_input() for _, r in requests]
        valued = valuation_engine.value(props, explain=True)
        async with db.connect() as conn:
            counts = {
                (r[0], r[1], r[2]): r[3]
                for r in (await conn.execute(text("""
                    SELECT lower(city), lower(locality), lower(property_type), count(*)
                    FROM property_comparables GROUP BY 1, 2, 3
                """))).all()
            }
        per_row_ms = (time.perf_counter() - started) * 1000 / len(requests)
        for (csv_row, req), prop, v in zip(requests, props, valued):
            n = counts.get((prop["city"].lower(), prop["locality"].lower(), prop["property_type"].lower()), 0)
            result = build_result(prop, v, [], req.loan_amount_inr, per_row_ms, comparable_count=n)
            result["explainability"]["all_factors"] = []
            result["csv_row"] = csv_row
            results.append(result)
        await persist(results, "batch")

    total_ms = (time.perf_counter() - started) * 1000
    routing_counts: dict[str, int] = {}
    for r in results:
        key = r["decision_support"]["routing"]
        routing_counts[key] = routing_counts.get(key, 0) + 1
    avoided = sum(1 for r in results if r["decision_support"]["physical_visit_avoided"])
    return {
        "filename": file.filename,
        "rows_received": len(df),
        "rows_valued": len(results),
        "rows_rejected": len(errors),
        "total_time_ms": round(total_ms, 1),
        "avg_time_per_property_ms": round(total_ms / max(len(results), 1), 2),
        "routing_counts": routing_counts,
        "physical_visits_avoided_pct": round(avoided / len(results) * 100, 1) if results else 0.0,
        "results": [
            {
                "csv_row": r["csv_row"],
                "valuation_id": r.get("valuation_id"),
                **{k: r["property_input"][k] for k in ("city", "locality", "property_type", "area_sqft")},
                "estimated_value_inr": r["estimated_value_inr"],
                "low_estimate_inr": r["low_estimate_inr"],
                "high_estimate_inr": r["high_estimate_inr"],
                "confidence": r["confidence"]["label"],
                "routing": r["decision_support"]["routing"],
                "ltv_pct": (r["decision_support"]["lending"] or {}).get("ltv_pct"),
                "risk_band": (r["decision_support"]["lending"] or {}).get("risk_band"),
                "top_factor": r["explainability"]["top_factors"][0]["label"],
                "coverage_warnings": r["coverage_warnings"],
            }
            for r in results
        ],
        "errors": errors,
        "disclaimer": DISCLAIMER,
    }


async def load_valuation(valuation_id: str) -> dict:
    async with db.connect() as conn:
        row = (await conn.execute(
            text("SELECT result FROM valuations WHERE valuation_id = :id"), {"id": valuation_id}
        )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Valuation not found.")
    return row


@router.get("/{valuation_id}")
async def get_valuation(valuation_id: str):
    return await load_valuation(valuation_id)


@router.get("/{valuation_id}/report.pdf")
async def valuation_report(valuation_id: str):
    from app.report import build_report

    result = await load_valuation(valuation_id)
    pdf = build_report(result)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="aura-valuation-{valuation_id[:8]}.pdf"'},
    )
