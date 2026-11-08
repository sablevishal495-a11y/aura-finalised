import hashlib
import io
from datetime import date

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import text

from app.db import engine

router = APIRouter(prefix="/api/data-import", tags=["Data Import"])

REQUIRED_COLUMNS = {
    "city",
    "locality",
    "property_type",
    "area_sqft",
    "transaction_value_inr",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000


def _clean_text(value):
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def _record_fingerprint(record):
    """Stable exact-record key for duplicate detection (not proof of authenticity)."""
    raw = "|".join(
        [
            _clean_text(record.get("city")).casefold(),
            _clean_text(record.get("locality")).casefold(),
            _clean_text(record.get("property_type")).casefold(),
            str(round(float(record["area_sqft"]), 2)),
            str(round(float(record["transaction_value_inr"]), 2)),
            str(record.get("transaction_date") or ""),
            _clean_text(record.get("source_record_id")).casefold(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.post("/comparables-csv")
async def import_comparables_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded CSV is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds the 10 MB upload limit.")

    try:
        df = pd.read_csv(io.BytesIO(content), dtype="string")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse CSV. Check its encoding and format.")

    if len(df) > MAX_ROWS:
        raise HTTPException(status_code=413, detail=f"CSV exceeds the {MAX_ROWS:,}-row limit.")

    df.columns = [str(column).strip().lower() for column in df.columns]
    missing_columns = REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "CSV is missing required columns.",
                "missing_columns": sorted(missing_columns),
                "required_columns": sorted(REQUIRED_COLUMNS),
            },
        )

    for column, default in {
        "transaction_date": None,
        "source_record_id": None,
        "source_name": "CSV_UPLOAD",
    }.items():
        if column not in df.columns:
            df[column] = default

    accepted = []
    rejected = []
    seen_in_file = set()

    # Keep original CSV row numbers (header is row 1).
    for idx, row in df.iterrows():
        csv_row = int(idx) + 2
        record = {key: row.get(key) for key in df.columns}
        record["_csv_row"] = csv_row
        record["city"] = _clean_text(record.get("city"))
        record["locality"] = _clean_text(record.get("locality"))
        record["property_type"] = _clean_text(record.get("property_type"))
        record["source_name"] = _clean_text(record.get("source_name")) or "CSV_UPLOAD"
        record["source_record_id"] = _clean_text(record.get("source_record_id")) or None

        reasons = []
        for field in ("city", "locality", "property_type"):
            if not record[field]:
                reasons.append(f"{field} is required")

        area = pd.to_numeric(record.get("area_sqft"), errors="coerce")
        value = pd.to_numeric(record.get("transaction_value_inr"), errors="coerce")
        if pd.isna(area) or float(area) <= 0:
            reasons.append("area_sqft must be a positive number")
        if pd.isna(value) or float(value) <= 0:
            reasons.append("transaction_value_inr must be a positive number")

        txn_date = pd.to_datetime(record.get("transaction_date"), errors="coerce")
        raw_date = record.get("transaction_date")
        has_date_value = raw_date is not None and not pd.isna(raw_date) and str(raw_date).strip() != ""
        if has_date_value and pd.isna(txn_date):
            reasons.append("transaction_date is not a valid date")
        if not pd.isna(txn_date):
            if txn_date.date() > date.today():
                reasons.append("transaction_date cannot be in the future")
            record["transaction_date"] = txn_date.date()
        else:
            record["transaction_date"] = None

        if reasons:
            rejected.append({"csv_row": csv_row, "reasons": reasons})
            continue

        record["area_sqft"] = float(area)
        record["transaction_value_inr"] = float(value)
        record["rate_per_sqft_inr"] = float(value) / float(area)
        fingerprint = _record_fingerprint(record)
        if fingerprint in seen_in_file:
            rejected.append({"csv_row": csv_row, "reasons": ["duplicate record within uploaded CSV"]})
            continue
        seen_in_file.add(fingerprint)
        record["_fingerprint"] = fingerprint
        accepted.append(record)

    inserted = 0
    duplicates_in_database = 0
    source_records_created = 0

    async with engine.begin() as connection:
        source_ids = {}
        for record in accepted:
            source_name = record["source_name"]
            if source_name not in source_ids:
                result = await connection.execute(
                    text("""
                        INSERT INTO data_sources (source_name, source_type, license_notes)
                        VALUES (:source_name, 'CSV_UPLOAD', :license_notes)
                        RETURNING source_id
                    """),
                    {
                        "source_name": source_name,
                        "license_notes": (
                            f"Uploaded file: {file.filename}. Source rights, provenance, and authenticity "
                            "must be verified by an authorized reviewer before use in lending decisions."
                        ),
                    },
                )
                source_ids[source_name] = result.scalar_one()
                source_records_created += 1

            # Exact duplicate guard against existing records; imported records remain unverified.
            duplicate = await connection.execute(
                text("""
                    SELECT 1
                    FROM property_comparables
                    WHERE lower(trim(city)) = lower(trim(:city))
                      AND lower(trim(locality)) = lower(trim(:locality))
                      AND lower(trim(property_type)) = lower(trim(:property_type))
                      AND area_sqft = :area_sqft
                      AND transaction_value_inr = :transaction_value_inr
                      AND transaction_date IS NOT DISTINCT FROM :transaction_date
                      AND COALESCE(source_record_id, '') = COALESCE(:source_record_id, '')
                    LIMIT 1
                """),
                record,
            )
            if duplicate.first() is not None:
                duplicates_in_database += 1
                rejected.append({
                    "csv_row": int(record.get("_csv_row", 0)) or None,
                    "reasons": ["duplicate record already exists in database"],
                })
                continue

            await connection.execute(
                text("""
                    INSERT INTO property_comparables (
                        source_id, city, locality, property_type, transaction_date,
                        area_sqft, transaction_value_inr, rate_per_sqft_inr,
                        data_source, source_record_id, is_verified
                    ) VALUES (
                        :source_id, :city, :locality, :property_type, :transaction_date,
                        :area_sqft, :transaction_value_inr, :rate_per_sqft_inr,
                        :data_source, :source_record_id, FALSE
                    )
                """),
                {
                    **{k: v for k, v in record.items() if not k.startswith("_")},
                    "source_id": source_ids[source_name],
                    "data_source": source_name,
                },
            )
            inserted += 1

    return {
        "message": "CSV import completed with validation and duplicate checks.",
        "filename": file.filename,
        "total_rows": len(df),
        "inserted_records": inserted,
        "rejected_records": len(rejected),
        "duplicates_in_file": sum(
            1 for item in rejected if "duplicate record within uploaded CSV" in item["reasons"]
        ),
        "duplicates_in_database": duplicates_in_database,
        "source_records_created": source_records_created,
        "verified_records": 0,
        "rejected_rows": rejected,
        "notice": "Imported records remain unverified. Confirm source rights, provenance, and authenticity before lending use.",
    }
