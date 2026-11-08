# AURA - AI-Powered Digital Property Valuation Engine for India

Hero Housing Finance · Problem Statement 1

AURA values residential and commercial property, explains every valuation, says how confident
it is, and tells a lender whether the case needs a physical site visit at all.

> **Prototype on synthetic data.** Every record the model learns from is generated and labelled
> `SYNTHETIC_DEMO`. The pipeline, model, explanations and lender workflow are real and working;
> the accuracy numbers demonstrate the measurement method, not real-market accuracy.

## Run it

Needs Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

| What | Where |
|---|---|
| Web app | http://localhost:5173 |
| API + Swagger docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

On first start the backend creates the database tables and loads 3,000 synthetic properties
and 900 synthetic comparable transactions. Nothing else to set up.

> Already ran an older version? Reset the demo database once so it is reseeded with the new
> data: `docker compose down -v` then `docker compose up --build`.

### Without Docker (development)

```bash
# backend (needs PostgreSQL 14+ with a database "aura" for user aura_user)
cd backend
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+asyncpg://aura_user:aura_dev_password@localhost:5432/aura
uvicorn app.main:app --reload --port 8000
```

```bash
# frontend
cd frontend
npm install
npm run dev        # http://localhost:5173  (set VITE_API_URL if the API is elsewhere)
```

## How AURA covers the six points

| # | Requirement | What AURA does | Where to see it |
|---|---|---|---|
| 1 | **Scope the market** | 5 property types - Apartment, Independent House, Villa (residential); Office Space, Retail Shop (commercial) - in Mumbai, Pune, Bengaluru, Delhi, Hyderabad and Indore. Phased plan to Tier-2 cities and then all states. Anything outside coverage is flagged and sent to physical inspection. | Overview |
| 2 | **Combine data sources** | Property attributes + transactions + government guideline rates, merged on locality with satellite (green cover), geo-spatial (metro distance), infrastructure-pipeline and market-trend signals. Each source documents how it is collected, cleaned and merged. CSV import validates, de-duplicates and quarantines rows. | Data Sources |
| 3 | **Build the AI/ML model** | LightGBM on 14 features (log-value target). Benchmarked on a held-out test set against a rate-card AVM (locality median rate x area) and guideline rate x area, using MAPE and PPE10/PPE20, with errors broken down by city and property type. | Model & Accuracy |
| 4 | **Make it explainable** | Every valuation returns the value, a calibrated 90% range, a confidence label and score, the top SHAP factors (with their data source), comparable transactions, a PDF report and a stored audit record with the model version. | Valuation Studio |
| 5 | **Automate and scale** | Stateless API, ~10-20 ms per valuation, batch CSV valuation of up to 1,000 properties per call, every result stored automatically, Docker deployment, versioned model artifact, retraining in one command. | Batch Valuation |
| 6 | **Enable lending decisions** | Loan-to-value against the RBI caps for housing loans (90% / 80% / 75% by loan size) and a lender policy for commercial property, maximum eligible loan, risk band, and routing to **desk valuation**, **desktop review** or **physical inspection**. A reviewer queue records the human decision and tracks the share of cases that avoided a site visit. | Valuation Studio, Review Queue |

## Architecture

```mermaid
flowchart LR
  subgraph Sources
    T[Transactions / IGR]
    G[Govt guideline rates]
    P[Property attributes]
    S[Satellite · Geo-spatial]
    I[Infrastructure · Market trends]
  end
  subgraph Pipeline
    V[Validate & quarantine] --> N[Normalise] --> D[De-duplicate] --> M[Merge on locality]
  end
  subgraph Engine["Valuation engine"]
    L[LightGBM value model]
    E[Per-property error model + conformal 90% range]
    X[SHAP explanations]
    C[Comparable evidence]
  end
  subgraph Lender["Lender workflow"]
    LTV[LTV vs RBI caps · risk band]
    R{Route}
    R -->|high confidence| DV[Desk valuation]
    R -->|medium / thin evidence| DR[Desktop review]
    R -->|low confidence / high value / out of coverage| PI[Physical inspection]
    Q[Review queue · sign-off · PDF · audit log]
  end
  Sources --> Pipeline --> Engine --> LTV --> R --> Q
```

### How confidence works

1. A LightGBM model predicts log(value).
2. A second LightGBM model, trained on the first model's out-of-fold errors, predicts how large
   the error is likely to be for *this* property. Villas and retail shops get wider ranges than
   standard apartments.
3. On a separate calibration split, AURA picks the multiplier that makes the range contain 90% of
   actual prices (split-conformal prediction). On the held-out test split the range covered
   about 89-90% of properties.
4. Range half-width ≤15% is **High** confidence, ≤25% **Medium**, otherwise **Low**.

### Routing policy (`backend/app/lending.py`)

| Condition | Route |
|---|---|
| Outside coverage, Low confidence, or value ≥ Rs 5 crore | Physical inspection |
| Fewer than 3 comparables, Medium confidence, or LTV above the cap | Desktop review |
| High confidence, ≥3 comparables, within coverage and LTV cap | Desk valuation (no site visit) |

Collateral value for LTV is the **low end** of the range. A credit officer always makes the
final decision; AURA never approves or declines a loan.

## Current results (synthetic held-out test set, 450 properties)

| Method | MAPE | PPE10 | PPE20 |
|---|---|---|---|
| **AURA (LightGBM + locality signals)** | **9.5%** | **66.4%** | **90.0%** |
| Rate-card AVM (locality median rate x area) | 13.2% | 46.7% | 77.8% |
| Government guideline rate x area | 32.6% | 8.4% | 20.9% |

The 90% range covered 89.1% of test properties. These numbers come from synthetic data and
**must not be quoted as real-world accuracy**. The Model & Accuracy page lists how accuracy would
be proven on real data (out-of-time and out-of-area tests, shadow pilot against physical valuations).

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/valuation/` | Value one property (optional `loan_amount_inr` adds the LTV check) |
| POST | `/api/valuation/batch` | Value a CSV of up to 1,000 properties |
| GET | `/api/valuation/{id}` | Stored valuation (audit record) |
| GET | `/api/valuation/{id}/report.pdf` | PDF valuation report |
| GET | `/api/valuation/history` | Recent valuations |
| GET | `/api/valuation/model-info` | Model card, metrics, baselines, segments, coverage |
| POST | `/api/lender-review/` | Open a review case from a stored valuation |
| GET | `/api/lender-review/` | Review queue (`pending_only=true` to filter) |
| POST | `/api/lender-review/{id}/decision` | Record the reviewer's decision (once) |
| GET | `/api/lender-review/summary` | Turnaround and physical-visits-avoided metrics |
| GET | `/api/properties/`, `/api/properties/summary` | Dataset browser and coverage |
| POST | `/api/data-import/comparables-csv` | Import comparable transactions with validation |
| GET | `/api/data-catalog/` | Data sources and pipeline contract |
| GET | `/api/government-guideline/` | Search the Indore FY 2026-27 guideline-rate extract |

Example:

```bash
curl -X POST http://localhost:8000/api/valuation/ -H "Content-Type: application/json" -d '{"city":"Pune","locality":"Baner","property_type":"Apartment","area_sqft":1100,"bedrooms":2,"bathrooms":2,"property_age_years":4,"floor_number":7,"furnishing_status":"Semi-Furnished","loan_amount_inr":6000000}'
```

## Regenerate data and retrain

```bash
cd backend
python -m app.demo.generate_data   # writes data/demo/*.csv
python -m app.ml.train_model       # writes app/ml/artifacts/property_valuation_model.joblib and prints the benchmark
```

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                      # API tests run when PostgreSQL is reachable at DATABASE_URL
```

```bash
cd frontend
npm run lint
npm run build
```

## Project layout

```
backend/app/
  main.py              FastAPI app, start-up bootstrap, health
  bootstrap.py         creates tables (schema.sql) and seeds the demo data
  lending.py           LTV caps, risk band, routing policy
  report.py            PDF valuation report
  ml/engine.py         loads the model; value, range, confidence, SHAP, coverage checks
  ml/train_model.py    merge, train, calibrate, benchmark, save artifact
  demo/generate_data.py  synthetic properties, comparables, locality signals
  routers/             valuation, lender_review, properties, data_import, data_catalog, government_guideline
data/demo/             synthetic datasets (labelled SYNTHETIC_DEMO)
frontend/src/          React app (pages/ = one file per screen)
```

## Limits (be upfront about these when presenting)

- All training data, comparables and locality signals are synthetic. Real accuracy needs licensed
  transaction data (state IGR), the lender's historical valuations and a shadow pilot.
- Satellite, geo-spatial, infrastructure and market-trend inputs are simulated locality-level
  features; the production connectors are documented in the Data Sources page but not built.
- Locations are matched by city + locality name; production would geocode to coordinates.
- The routing thresholds and commercial LTV are illustrative and would be set by the lender's
  credit policy.
