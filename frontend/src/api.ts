export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || 'http://localhost:8000'

type ErrorBody = { detail?: string | { msg?: string; message?: string }[] | { message?: string } }

function errorMessage(body: ErrorBody | null, fallback: string): string {
  const detail = body?.detail
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d.msg || d.message || '').filter(Boolean).join(', ') || fallback
  return detail.message || fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API_BASE + path, init)
  } catch {
    throw new Error(`Cannot reach the AURA API at ${API_BASE}. Is the backend running?`)
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(errorMessage(body, `Request failed (${response.status})`))
  return body as T
}

export const getJSON = <T,>(path: string) => request<T>(path)

export const postJSON = <T,>(path: string, payload: unknown) =>
  request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })

export const postFile = <T,>(path: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return request<T>(path, { method: 'POST', body: form })
}

/* ---------- API types ---------- */

export type PropertyInput = {
  city: string
  locality: string
  property_type: string
  area_sqft: number
  bedrooms: number
  bathrooms: number
  property_age_years: number
  floor_number: number
  furnishing_status: string
}

export type Factor = {
  feature: string
  label: string
  value: string
  source: string
  impact_pct: number
  impact_inr: number
  direction: string
}

export type Lending = {
  loan_amount_inr: number
  collateral_value_inr: number
  collateral_basis: string
  ltv_pct: number
  max_ltv_pct: number
  ltv_policy: string
  max_eligible_loan_inr: number
  risk_band: 'Low' | 'Medium' | 'High'
}

export type Routing = 'AUTO_DESK_VALUATION' | 'DESKTOP_REVIEW' | 'PHYSICAL_INSPECTION'

export type DecisionSupport = {
  routing: Routing
  routing_label: string
  reasons: string[]
  physical_visit_avoided: boolean
  human_review_required: boolean
  lending: Lending | null
  notice: string
}

export type Comparable = {
  city: string
  locality: string
  property_type: string
  transaction_date: string | null
  area_sqft: number
  transaction_value_inr: number
  rate_per_sqft_inr: number
  data_source: string
  is_verified: boolean
}

export type Valuation = {
  valuation_id: string | null
  valued_at: string
  estimated_value_inr: number
  low_estimate_inr: number
  high_estimate_inr: number
  rate_per_sqft_inr: number
  confidence: {
    label: 'High' | 'Medium' | 'Low'
    score: number
    interval_level_pct: number
    relative_half_width_pct: number
    method: string
  }
  coverage_warnings: string[]
  locality_signals: { feature: string; label: string; source: string; value: number; matched_locality: boolean }[]
  explainability: { method: string; available: boolean; base_value_inr: number; top_factors: Factor[]; all_factors: Factor[]; notice: string }
  property_input: PropertyInput
  model: string
  model_version: string
  data_source: string
  comparables: {
    comparable_count: number
    verified_comparable_count: number
    average_rate_per_sqft_inr: number | null
    comparable_estimate_inr: number | null
    model_vs_comparable_gap_pct: number | null
    records: Comparable[]
    notice: string
  }
  decision_support: DecisionSupport
  latency_ms: number
  audit_saved: boolean
  disclaimer: string
}

export type PropertySummary = {
  total_properties: number
  cities: { city: string; properties: number; types: { property_type: string; segment: string; count: number; median_rate_per_sqft_inr: number | null }[] }[]
  localities: Record<string, string[]>
  property_types: string[]
  segments: string[]
  by_data_source: Record<string, number>
  comparables: { total: number; verified: number }
}

export type Accuracy = { mae_inr: number; rmse_inr: number; mape_pct: number; median_ape_pct: number; ppe10_pct: number; ppe20_pct: number; r2: number }

export type ModelInfo = {
  available: boolean
  error?: string
  model: string
  model_version: string
  trained_at: string
  data_source: string
  rows: { train: number; calibration: number; test: number }
  features: { feature: string; type: string; group: string }[]
  metrics: Accuracy & { interval_coverage_pct: number; median_interval_half_width_pct: number }
  baselines: Record<string, Accuracy & { name: string }>
  segments: { dimension: string; segment: string; test_rows: number; mape_pct: number; ppe10_pct: number; ppe20_pct: number; interval_coverage_pct: number }[]
  coverage: { cities: string[]; property_types: string[]; localities: Record<string, string[]> }
  locality_table: Record<string, string | number>[]
  notice: string
}

export type Review = {
  review_id: string
  created_at: string
  valuation_id: string | null
  property_input: PropertyInput
  estimated_value_inr: number
  low_estimate_inr: number
  high_estimate_inr: number
  data_source: string
  comparable_count: number
  verified_comparable_count: number
  evidence_quality: string
  review_status: string
  routing_reason: string
  reviewer_note: string
  model_version: string | null
  confidence_label: string | null
  loan_amount_inr: number | null
  ltv_pct: number | null
  risk_band: string | null
  reviewer_decision: string | null
  reviewer_name: string | null
  decision_note: string | null
  decided_at: string | null
}

export type ReviewSummary = {
  total_reviews: number
  by_routing: Record<string, number>
  by_decision: Record<string, number>
  physical_visits_avoided_pct: number
  total_valuations: number
  avg_valuation_latency_ms: number
  valuations_without_site_visit_pct: number
  notice: string
}

export type BatchResult = {
  filename: string
  rows_received: number
  rows_valued: number
  rows_rejected: number
  total_time_ms: number
  avg_time_per_property_ms: number
  routing_counts: Record<string, number>
  physical_visits_avoided_pct: number
  results: {
    csv_row: number
    valuation_id: string | null
    city: string
    locality: string
    property_type: string
    area_sqft: number
    estimated_value_inr: number
    low_estimate_inr: number
    high_estimate_inr: number
    confidence: string
    routing: Routing
    ltv_pct: number | null
    risk_band: string | null
    top_factor: string
    coverage_warnings: string[]
  }[]
  errors: { csv_row: number; errors: string[] }[]
  disclaimer: string
}
