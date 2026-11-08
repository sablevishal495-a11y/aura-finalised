import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.bootstrap import bootstrap
from app.db import engine as db
from app.ml.engine import engine as valuation_engine
from app.routers.data_catalog import router as data_catalog_router
from app.routers.data_import import router as data_import_router
from app.routers.government_guideline import router as government_guideline_router
from app.routers.lender_review import router as lender_review_router
from app.routers.properties import router as properties_router
from app.routers.valuation import router as valuation_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await bootstrap()
    except Exception:  # noqa: BLE001 - start degraded; /health reports the database state
        logging.getLogger("aura").exception("Database bootstrap failed; is PostgreSQL running?")
    yield
    await db.dispose()


app = FastAPI(
    title="AURA Property Intelligence API",
    description="AI-powered digital property valuation engine for India (prototype on synthetic data).",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(properties_router)
app.include_router(valuation_router)
app.include_router(data_import_router)
app.include_router(lender_review_router)
app.include_router(data_catalog_router)
app.include_router(government_guideline_router)


@app.get("/")
def root():
    return {
        "message": "AURA API is running",
        "mode": "demo",
        "model_version": valuation_engine.model_version,
        "data_notice": "Synthetic demo data only; imported records require verification.",
    }


@app.get("/health")
async def health():
    try:
        async with db.connect() as conn:
            await conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "unavailable"
    model = "ok" if valuation_engine.available else "unavailable"
    return {"status": "healthy" if database == model == "ok" else "degraded", "database": database, "model": model}
