# AURA — Problem Statement 1 implementation status

AURA is a working prototype of a digital property valuation engine. All data is synthetic and
labelled `SYNTHETIC_DEMO`; it is not a production AVM or a credit decision engine.

Legend: ✅ working in the prototype · 🟡 simulated with labelled synthetic data · ⏳ needs real data or a pilot

## 1 — Scope the market (residential + commercial, across India)
- ✅ 5 property types: Apartment, Independent House, Villa (residential); Office Space, Retail Shop (commercial).
- ✅ 6 launch cities, 24 localities; coverage table on the Overview page.
- ✅ Out-of-coverage city / locality / type is detected, flagged and routed to physical inspection.
- ✅ Phased rollout plan (Phase 1 → Tier-2 cities → all states) on the Overview page.
- ⏳ Real data per city before each city goes live.

## 2 — Combine structured, unstructured and alternative data
- ✅ Merge pipeline: property attributes + locality signals joined on city + locality (training and serving use the same table).
- ✅ Government records: Indore FY 2026-27 guideline-rate extract searchable; guideline rate is a model feature and a baseline.
- ✅ Transactions: CSV import with validation, quarantine reasons and de-duplication; comparables used as evidence.
- 🟡 Satellite (green cover), geo-spatial (metro distance), infrastructure pipeline and market trend features.
- ✅ Source catalog: how each source is collected, cleaned and merged, and its demo status.
- ⏳ Licensed connectors (IGR, GIS, satellite tiles, listing APIs).

## 3 — AI/ML model and accuracy
- ✅ LightGBM on 14 features, log-value target, 70 / 15 / 15 train / calibration / test split.
- ✅ Benchmark against a rate-card AVM and guideline rate x area: MAPE 9.5% vs 13.2% vs 32.6%; PPE10 66.4% vs 46.7% vs 8.4% (synthetic test set).
- ✅ Error analysis by city and property type.
- ✅ Documented method for proving accuracy on real data (out-of-time, out-of-area, shadow pilot).
- ⏳ Real-world accuracy claims.

## 4 — Explainable valuation
- ✅ Value, calibrated 90% range (held-out coverage ~89-90%), confidence label and score per property.
- ✅ SHAP factors grouped by original feature, with % effect and data source.
- ✅ Comparable transactions and model-vs-comparables gap.
- ✅ Audit: every valuation stored with inputs, outputs and model version; PDF report.

## 5 — Automate and scale
- ✅ ~10-20 ms per valuation; batch CSV of up to 1,000 properties per call with routing summary.
- ✅ One-command Docker deployment (database, API, web app); schema and demo data created automatically.
- ✅ Versioned model artifact; one-command data generation and retraining; 19 backend tests.
- ⏳ Scheduled ingestion workers, model registry, monitoring and load testing for production.

## 6 — Lending decisions and fewer physical valuations
- ✅ LTV against RBI housing-loan caps (90% / 80% / 75%) and an illustrative commercial cap (60%), on the conservative (low) value.
- ✅ Maximum eligible loan and risk band.
- ✅ Routing: desk valuation / desktop review / physical inspection, with reasons.
- ✅ Review queue: reviewer records the decision once; summary shows the share of cases that avoided a site visit.
- ⏳ Lender pilot to measure the real reduction in physical valuations and set policy thresholds.

## Data integrity
- Synthetic data is visibly labelled in the UI, API responses and PDF.
- Do not report market accuracy, AVM superiority, lender suitability or inspection reduction until validated on licensed real-world data in a pilot.
