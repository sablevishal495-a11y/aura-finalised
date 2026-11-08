from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine as db

router = APIRouter(prefix="/api/properties", tags=["Properties"])


@router.get("/")
async def get_properties(
    city: str | None = Query(default=None, max_length=100),
    property_type: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    filters, params = [], {"limit": limit, "offset": offset}
    if city:
        filters.append("lower(city) = lower(:city)")
        params["city"] = city
    if property_type:
        filters.append("lower(property_type) = lower(:property_type)")
        params["property_type"] = property_type
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    async with db.connect() as connection:
        total = (await connection.execute(text(f"SELECT count(*) FROM properties {where}"), params)).scalar()
        rows = (await connection.execute(text(f"""
            SELECT property_id, city, locality, property_type, segment, area_sqft, bedrooms,
                   bathrooms, property_age_years, floor_number, furnishing_status,
                   rate_per_sqft_inr, estimated_value_inr, data_source
            FROM properties {where}
            ORDER BY property_id LIMIT :limit OFFSET :offset
        """), params)).mappings().all()

    return {"count": len(rows), "total": total, "limit": limit, "offset": offset, "data": [dict(r) for r in rows]}


@router.get("/summary")
async def property_summary():
    async with db.connect() as connection:
        rows = (await connection.execute(text("""
            SELECT city, segment, property_type, count(*) AS n,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY rate_per_sqft_inr) AS median_rate
            FROM properties GROUP BY city, segment, property_type ORDER BY city, property_type
        """))).mappings().all()
        localities = (await connection.execute(text(
            "SELECT DISTINCT city, locality FROM properties ORDER BY city, locality"
        ))).all()
        sources = (await connection.execute(text(
            "SELECT data_source, count(*) FROM properties GROUP BY 1"
        ))).all()
        comparables = (await connection.execute(text(
            "SELECT count(*), count(*) FILTER (WHERE is_verified) FROM property_comparables"
        ))).one()

    by_city: dict[str, dict] = {}
    for r in rows:
        city = by_city.setdefault(r["city"], {"city": r["city"], "properties": 0, "types": []})
        city["properties"] += r["n"]
        city["types"].append({
            "property_type": r["property_type"],
            "segment": r["segment"],
            "count": r["n"],
            "median_rate_per_sqft_inr": round(float(r["median_rate"]), 0) if r["median_rate"] else None,
        })
    locality_map: dict[str, list[str]] = {}
    for city, locality in localities:
        locality_map.setdefault(city, []).append(locality)

    return {
        "total_properties": sum(c["properties"] for c in by_city.values()),
        "cities": list(by_city.values()),
        "localities": locality_map,
        "property_types": sorted({r["property_type"] for r in rows}),
        "segments": sorted({r["segment"] for r in rows}),
        "by_data_source": {k: v for k, v in sources},
        "comparables": {"total": comparables[0], "verified": comparables[1]},
    }
