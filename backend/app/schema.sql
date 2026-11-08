-- AURA database schema. Idempotent: safe to run on every start-up.

CREATE TABLE IF NOT EXISTS data_sources (
    source_id      SERIAL PRIMARY KEY,
    source_name    VARCHAR(200) NOT NULL,
    source_type    VARCHAR(50)  NOT NULL,
    license_notes  TEXT         NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS properties (
    property_id          VARCHAR(40) PRIMARY KEY,
    city                 VARCHAR(100) NOT NULL,
    locality             VARCHAR(100) NOT NULL,
    property_type        VARCHAR(50)  NOT NULL,
    segment              VARCHAR(20)  NOT NULL DEFAULT 'Residential',
    area_sqft            DOUBLE PRECISION NOT NULL CHECK (area_sqft > 0),
    bedrooms             INTEGER NOT NULL DEFAULT 0,
    bathrooms            INTEGER NOT NULL DEFAULT 0,
    property_age_years   INTEGER NOT NULL DEFAULT 0,
    floor_number         INTEGER NOT NULL DEFAULT 0,
    furnishing_status    VARCHAR(50) NOT NULL DEFAULT 'Unfurnished',
    rate_per_sqft_inr    DOUBLE PRECISION,
    estimated_value_inr  DOUBLE PRECISION NOT NULL CHECK (estimated_value_inr > 0),
    data_source          VARCHAR(100) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_properties_city ON properties (lower(city));
-- Databases created by earlier versions lack these columns.
ALTER TABLE properties ADD COLUMN IF NOT EXISTS segment VARCHAR(20) NOT NULL DEFAULT 'Residential';
ALTER TABLE properties ADD COLUMN IF NOT EXISTS bathrooms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS furnishing_status VARCHAR(50) NOT NULL DEFAULT 'Unfurnished';
ALTER TABLE property_comparables ADD COLUMN IF NOT EXISTS source_record_id VARCHAR(100);
ALTER TABLE property_comparables ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS property_comparables (
    comparable_id          SERIAL PRIMARY KEY,
    source_id              INTEGER REFERENCES data_sources (source_id),
    city                   VARCHAR(100) NOT NULL,
    locality               VARCHAR(100) NOT NULL,
    property_type          VARCHAR(50)  NOT NULL,
    transaction_date       DATE,
    area_sqft              DOUBLE PRECISION NOT NULL CHECK (area_sqft > 0),
    transaction_value_inr  DOUBLE PRECISION NOT NULL CHECK (transaction_value_inr > 0),
    rate_per_sqft_inr      DOUBLE PRECISION NOT NULL,
    data_source            VARCHAR(200) NOT NULL,
    source_record_id       VARCHAR(100),
    is_verified            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_comparables_lookup
    ON property_comparables (lower(city), lower(locality), lower(property_type));

-- Every valuation is stored so a lender can audit exactly what the engine returned.
CREATE TABLE IF NOT EXISTS valuations (
    valuation_id         VARCHAR(36) PRIMARY KEY,
    created_at           TIMESTAMPTZ NOT NULL,
    channel              VARCHAR(20) NOT NULL,
    model_version        VARCHAR(80) NOT NULL,
    property_input       JSONB NOT NULL,
    result               JSONB NOT NULL,
    estimated_value_inr  DOUBLE PRECISION NOT NULL,
    low_estimate_inr     DOUBLE PRECISION NOT NULL,
    high_estimate_inr    DOUBLE PRECISION NOT NULL,
    confidence_label     VARCHAR(20) NOT NULL,
    routing              VARCHAR(40) NOT NULL,
    latency_ms           DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_valuations_created ON valuations (created_at DESC);

CREATE TABLE IF NOT EXISTS lender_valuation_reviews (
    review_id                  VARCHAR(36) PRIMARY KEY,
    created_at                 TIMESTAMPTZ NOT NULL,
    property_input             JSONB NOT NULL,
    estimated_value_inr        DOUBLE PRECISION NOT NULL,
    low_estimate_inr           DOUBLE PRECISION NOT NULL,
    high_estimate_inr          DOUBLE PRECISION NOT NULL,
    data_source                VARCHAR(100) NOT NULL,
    comparable_count           INTEGER NOT NULL,
    verified_comparable_count  INTEGER NOT NULL,
    evidence_quality           VARCHAR(20) NOT NULL,
    review_status              VARCHAR(40) NOT NULL,
    routing_reason             TEXT NOT NULL,
    reviewer_note              TEXT NOT NULL DEFAULT ''
);
-- Columns added for the audit trail and the reviewer sign-off (safe on existing databases).
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS valuation_id VARCHAR(36) REFERENCES valuations (valuation_id);
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS model_version VARCHAR(80);
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS confidence_label VARCHAR(20);
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS loan_amount_inr DOUBLE PRECISION;
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS ltv_pct DOUBLE PRECISION;
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS risk_band VARCHAR(20);
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS reviewer_decision VARCHAR(40);
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS reviewer_name VARCHAR(120);
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS decision_note TEXT;
ALTER TABLE lender_valuation_reviews ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;
