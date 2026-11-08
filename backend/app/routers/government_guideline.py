"""Search raw MPIGR guideline extraction. Raw rates are not normalized/model inputs."""
import csv
from pathlib import Path
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/government-guideline", tags=["Government Guideline Benchmark"])
DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "indore_guideline_raw.csv"

@router.get("/")
def search_guideline(q: str = Query("", max_length=160), limit: int = Query(20, ge=1, le=100)):
    """Return matching raw locality rows with FY, page, and limitations."""
    rows = []
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            location = row.get("guideline_location_as_extracted", "")
            if not q.strip() or q.casefold() in location.casefold():
                rows.append({
                    "serial_no": row.get("serial_no"),
                    "locality_as_extracted": location,
                    "raw_rate_columns_as_extracted": row.get("raw_rate_columns_as_extracted"),
                    "financial_year": row.get("financial_year"),
                    "district": row.get("district"),
                    "source_document": row.get("source_document"),
                    "source_page": row.get("source_page"),
                    "data_type": row.get("data_type"),
                    "usage_note": row.get("usage_note"),
                })
                if len(rows) >= limit:
                    break
    return {
        "source": "Government of Madhya Pradesh, Indore district guideline document",
        "financial_year": "2026-2027",
        "coverage": "Partial raw extraction only; not all 472 PDF pages",
        "matched_count_returned": len(rows),
        "query": q,
        "results": rows,
        "critical_notice": "Guideline rates are registration/stamp-duty reference values, not verified market transaction prices or an independent property valuation. Extracted rate columns and units have not been normalized; do not feed them into the ML model until mapped against official table headers and verified.",
    }
