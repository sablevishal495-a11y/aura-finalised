"""Source catalog and provenance contract for AURA's multi-source ingestion pipeline.

``demo_status`` says honestly what the prototype does with each source today:
  * ``live_in_demo``      - wired end-to-end (CSV import, guideline search)
  * ``simulated_in_demo`` - represented by labelled synthetic features the model really uses
  * ``connector_required``- production connector and licence still needed
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/data-catalog", tags=["Data Catalog"])

SOURCES = [
    {
        "source_id": "registered_transactions",
        "name": "Transaction data",
        "category": "structured",
        "examples": ["registered sale deeds (state IGR portals)", "lender's own disbursed-loan valuations"],
        "collection": "Licensed bulk feed or validated CSV upload",
        "cleaning": "Schema + range checks, duplicate fingerprinting, outlier flags, verified/unverified split",
        "merge_key": "city + locality + property type (geocode in production)",
        "model_use": "Training labels and comparable evidence",
        "demo_status": "live_in_demo",
        "demo_note": "CSV import with validation and de-duplication; synthetic transactions seeded.",
    },
    {
        "source_id": "government_records",
        "name": "Government records",
        "category": "structured",
        "examples": ["guideline / circle rates", "property tax records", "RERA project registrations"],
        "collection": "Official PDFs and portals, extracted and versioned by financial year",
        "cleaning": "Locality name normalisation, unit and column mapping against official headers",
        "merge_key": "city + locality",
        "model_use": "Feature: guideline rate per sq.ft.; baseline for accuracy comparison",
        "demo_status": "live_in_demo",
        "demo_note": "Indore FY 2026-27 guideline extract is searchable; model uses a synthetic guideline-rate feature.",
    },
    {
        "source_id": "property_attributes",
        "name": "Property attributes",
        "category": "structured",
        "examples": ["area, type, age, floor, bedrooms", "loan application form", "sanctioned building plan"],
        "collection": "Loan origination system / application API",
        "cleaning": "Required-field and range validation at the API",
        "merge_key": "application ID",
        "model_use": "Core model features",
        "demo_status": "live_in_demo",
        "demo_note": "Entered in Valuation Studio or uploaded as a batch CSV.",
    },
    {
        "source_id": "satellite_imagery",
        "name": "Satellite imagery",
        "category": "unstructured",
        "examples": ["Sentinel-2 / ISRO Bhuvan tiles", "construction progress", "green cover (NDVI)"],
        "collection": "Tile API, processed to locality-level indices on a schedule",
        "cleaning": "Cloud masking, seasonal normalisation, aggregation to locality polygons",
        "merge_key": "locality polygon",
        "model_use": "Feature: green cover %",
        "demo_status": "simulated_in_demo",
        "demo_note": "Synthetic locality green-cover index stands in for an NDVI pipeline.",
    },
    {
        "source_id": "geospatial",
        "name": "Geo-spatial information",
        "category": "alternative",
        "examples": ["metro / rail stations", "schools, hospitals", "flood and hazard zones"],
        "collection": "OpenStreetMap / licensed GIS layers, versioned",
        "cleaning": "Coordinate validation, distance computation from geocoded property",
        "merge_key": "latitude / longitude",
        "model_use": "Feature: distance to metro (km)",
        "demo_status": "simulated_in_demo",
        "demo_note": "Synthetic locality-level metro distance.",
    },
    {
        "source_id": "infrastructure_developments",
        "name": "Infrastructure developments",
        "category": "alternative",
        "examples": ["announced metro lines and highways", "smart-city projects", "SEZ / IT parks"],
        "collection": "Government tenders and project announcements, curated quarterly",
        "cleaning": "Project status tracking, distance-weighted scoring",
        "merge_key": "locality",
        "model_use": "Feature: infrastructure pipeline score (0-10)",
        "demo_status": "simulated_in_demo",
        "demo_note": "Synthetic infrastructure score per locality.",
    },
    {
        "source_id": "market_trends",
        "name": "Market trends",
        "category": "alternative",
        "examples": ["listing asking prices", "absorption and inventory", "RBI / NHB RESIDEX house price index"],
        "collection": "Permitted listing APIs and published indices, monthly",
        "cleaning": "Asking-price discounting, de-duplication of listings, index rebasing",
        "merge_key": "city + locality",
        "model_use": "Feature: year-on-year price trend %",
        "demo_status": "simulated_in_demo",
        "demo_note": "Synthetic YoY trend per locality.",
    },
]


@router.get("/")
def get_data_catalog():
    return {
        "sources": SOURCES,
        "pipeline_contract": [
            "Collect: licensed connector, official extract or validated CSV - every record keeps provider, licence and ingest time",
            "Validate: required fields and ranges; invalid rows are quarantined with reasons",
            "Normalise: city / locality / property-type vocabulary, units (sq.ft., INR)",
            "De-duplicate: provider record ID, then exact-record fingerprint",
            "Merge: locality signals joined on city + locality (geocode + polygon join in production)",
            "Separate: verified transactions vs asking prices vs synthetic records",
            "Monitor: freshness, missing values and drift before each retrain",
        ],
        "status_notice": "Sources marked simulated_in_demo are represented by labelled synthetic features; "
                         "production connectors and licences are still required.",
    }
