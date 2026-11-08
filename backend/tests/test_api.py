"""End-to-end API tests. They need PostgreSQL at DATABASE_URL and are skipped without it."""
import socket
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.db import DATABASE_URL


def _db_reachable() -> bool:
    url = urlparse(DATABASE_URL.replace("+asyncpg", ""))
    try:
        with socket.create_connection((url.hostname, url.port or 5432), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="PostgreSQL is not reachable")

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


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health_and_seeded_data(client):
    assert client.get("/health").json()["status"] == "healthy"
    summary = client.get("/api/properties/summary").json()
    assert summary["total_properties"] > 0
    assert {"Residential", "Commercial"} <= set(summary["segments"])


def test_valuation_review_decision_flow(client):
    response = client.post("/api/valuation/", json={**PROPERTY, "loan_amount_inr": 6_000_000})
    assert response.status_code == 200
    valuation = response.json()
    assert valuation["audit_saved"] is True
    assert valuation["comparables"]["comparable_count"] > 0
    assert valuation["decision_support"]["lending"]["ltv_pct"] > 0

    stored = client.get(f"/api/valuation/{valuation['valuation_id']}").json()
    assert stored["estimated_value_inr"] == valuation["estimated_value_inr"]

    pdf = client.get(f"/api/valuation/{valuation['valuation_id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    review = client.post("/api/lender-review/", json={"valuation_id": valuation["valuation_id"]})
    assert review.status_code == 201
    review_id = review.json()["review_id"]
    assert review.json()["review_status"] == valuation["decision_support"]["routing"]

    decision = {"decision": "ACCEPTED_DESK_VALUATION", "reviewer_name": "Test Officer"}
    assert client.post(f"/api/lender-review/{review_id}/decision", json=decision).status_code == 200
    assert client.post(f"/api/lender-review/{review_id}/decision", json=decision).status_code == 409
    assert client.get("/api/lender-review/summary").json()["total_reviews"] >= 1


def test_review_requires_existing_valuation(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post("/api/lender-review/", json={"valuation_id": missing}).status_code == 404


def test_invalid_valuation_input_is_rejected(client):
    assert client.post("/api/valuation/", json={**PROPERTY, "area_sqft": -10}).status_code == 422


def test_batch_valuation_reports_rejected_rows(client):
    csv = (
        "city,locality,property_type,area_sqft,loan_amount_inr\n"
        "Pune,Baner,Apartment,1100,6000000\n"
        "Mumbai,Powai,Office Space,2000,\n"
        "Pune,Wakad,Apartment,-5,\n"
    )
    response = client.post("/api/valuation/batch", files={"file": ("batch.csv", csv, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["rows_valued"] == 2
    assert body["rows_rejected"] == 1
    assert sum(body["routing_counts"].values()) == 2


def test_model_info_reports_baselines(client):
    info = client.get("/api/valuation/model-info").json()
    assert info["available"] is True
    assert set(info["baselines"]) == {"rate_card_avm", "guideline_rate"}
