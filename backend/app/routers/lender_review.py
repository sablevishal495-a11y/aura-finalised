"""Lender review workflow: a valuation becomes a review case, a reviewer signs it off.

AURA routes each case (desk valuation / desktop review / physical inspection) and records the
human decision. It never approves or declines a loan.
"""
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine as db
from app.lending import PHYSICAL, route

router = APIRouter(prefix="/api/lender-review", tags=["Lender Review"])

Decision = Literal[
    "ACCEPTED_DESK_VALUATION",
    "ACCEPTED_AFTER_DESKTOP_REVIEW",
    "PHYSICAL_INSPECTION_ORDERED",
    "REJECTED_INSUFFICIENT_EVIDENCE",
]


class ReviewCreate(BaseModel):
    valuation_id: str = Field(min_length=36, max_length=36)
    loan_amount_inr: float | None = Field(default=None, gt=0, le=10_000_000_000)
    reviewer_note: str = Field(default="", max_length=2000)


class ReviewDecision(BaseModel):
    decision: Decision
    reviewer_name: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)


def evidence_quality(verified: int, total: int) -> str:
    if verified >= 5:
        return "Higher"
    if verified >= 1:
        return "Moderate"
    return "Low" if total else "Unavailable"


@router.post("/", status_code=201)
async def create_lender_review(payload: ReviewCreate):
    async with db.connect() as conn:
        result = (await conn.execute(
            text("SELECT result FROM valuations WHERE valuation_id = :id"), {"id": payload.valuation_id}
        )).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Valuation not found. Run a valuation first.")

    comps = result["comparables"]
    loan = payload.loan_amount_inr or (result["decision_support"].get("lending") or {}).get("loan_amount_inr")
    # Re-run the policy on the stored valuation so the routing cannot be altered by the client.
    decision = route(result, comps["comparable_count"], result["property_input"]["property_type"], loan)
    lending = decision["lending"] or {}
    review_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with db.begin() as conn:
        await conn.execute(text("""
            INSERT INTO lender_valuation_reviews (
                review_id, created_at, property_input, estimated_value_inr, low_estimate_inr,
                high_estimate_inr, data_source, comparable_count, verified_comparable_count,
                evidence_quality, review_status, routing_reason, reviewer_note, valuation_id,
                model_version, confidence_label, loan_amount_inr, ltv_pct, risk_band
            ) VALUES (
                :review_id, :created_at, CAST(:property_input AS JSONB), :estimated, :low, :high,
                :source, :count, :verified, :quality, :status, :reason, :note, :valuation_id,
                :model_version, :confidence, :loan, :ltv, :risk
            )
        """), {
            "review_id": review_id,
            "created_at": created_at,
            "property_input": json.dumps(result["property_input"]),
            "estimated": result["estimated_value_inr"],
            "low": result["low_estimate_inr"],
            "high": result["high_estimate_inr"],
            "source": result["data_source"],
            "count": comps["comparable_count"],
            "verified": comps["verified_comparable_count"],
            "quality": evidence_quality(comps["verified_comparable_count"], comps["comparable_count"]),
            "status": decision["routing"],
            "reason": " ".join(decision["reasons"]),
            "note": payload.reviewer_note,
            "valuation_id": payload.valuation_id,
            "model_version": result["model_version"],
            "confidence": result["confidence"]["label"],
            "loan": lending.get("loan_amount_inr"),
            "ltv": lending.get("ltv_pct"),
            "risk": lending.get("risk_band"),
        })
    return {
        "review_id": review_id,
        "created_at": created_at.isoformat(),
        "review_status": decision["routing"],
        "routing_label": decision["routing_label"],
        "routing_reason": " ".join(decision["reasons"]),
        "lending": decision["lending"],
        "human_review_required": True,
        "notice": "AURA routes the valuation work; a credit officer makes the lending decision.",
    }


@router.get("/")
async def list_lender_reviews(
    limit: int = Query(default=50, ge=1, le=200),
    pending_only: bool = False,
):
    where = "WHERE reviewer_decision IS NULL" if pending_only else ""
    async with db.connect() as conn:
        rows = (await conn.execute(text(f"""
            SELECT review_id, created_at, valuation_id, property_input, estimated_value_inr,
                   low_estimate_inr, high_estimate_inr, data_source, comparable_count,
                   verified_comparable_count, evidence_quality, review_status, routing_reason,
                   reviewer_note, model_version, confidence_label, loan_amount_inr, ltv_pct,
                   risk_band, reviewer_decision, reviewer_name, decision_note, decided_at
            FROM lender_valuation_reviews {where}
            ORDER BY created_at DESC LIMIT :limit
        """), {"limit": limit})).mappings().all()
    return {"count": len(rows), "reviews": [dict(row) for row in rows]}


@router.get("/summary")
async def review_summary():
    """Workflow metrics a lender would track in a pilot."""
    async with db.connect() as conn:
        by_route = (await conn.execute(text(
            "SELECT review_status, count(*) FROM lender_valuation_reviews GROUP BY 1"
        ))).all()
        by_decision = (await conn.execute(text(
            "SELECT coalesce(reviewer_decision, 'PENDING'), count(*) FROM lender_valuation_reviews GROUP BY 1"
        ))).all()
        valuations = (await conn.execute(text("""
            SELECT count(*), coalesce(avg(latency_ms), 0),
                   count(*) FILTER (WHERE routing <> :physical)
            FROM valuations
        """), {"physical": PHYSICAL})).one()
    total_reviews = sum(n for _, n in by_route)
    physical = sum(n for status, n in by_route if status == PHYSICAL)
    return {
        "total_reviews": total_reviews,
        "by_routing": {k: v for k, v in by_route},
        "by_decision": {k: v for k, v in by_decision},
        "physical_visits_avoided_pct": round((total_reviews - physical) / total_reviews * 100, 1) if total_reviews else 0.0,
        "total_valuations": valuations[0],
        "avg_valuation_latency_ms": round(float(valuations[1]), 1),
        "valuations_without_site_visit_pct": round(valuations[2] / valuations[0] * 100, 1) if valuations[0] else 0.0,
        "notice": "Measured on demo traffic. Real reduction in physical valuations needs a lender pilot.",
    }


@router.post("/{review_id}/decision")
async def record_decision(review_id: str, payload: ReviewDecision):
    async with db.begin() as conn:
        updated = (await conn.execute(text("""
            UPDATE lender_valuation_reviews
            SET reviewer_decision = :decision, reviewer_name = :name, decision_note = :note,
                decided_at = :decided_at
            WHERE review_id = :review_id AND reviewer_decision IS NULL
            RETURNING review_id, reviewer_decision, reviewer_name, decided_at
        """), {
            "decision": payload.decision,
            "name": payload.reviewer_name.strip(),
            "note": payload.note,
            "decided_at": datetime.now(timezone.utc),
            "review_id": review_id,
        })).mappings().first()
        if updated is None:
            exists = (await conn.execute(
                text("SELECT 1 FROM lender_valuation_reviews WHERE review_id = :id"), {"id": review_id}
            )).first()
            if exists is None:
                raise HTTPException(status_code=404, detail="Review not found.")
            raise HTTPException(status_code=409, detail="This review already has a recorded decision.")
    return dict(updated)
