import { useState, type FormEvent } from 'react'
import { API_BASE, postJSON, type PropertySummary, type Valuation } from '../api'
import { Badge, Card, ErrorNote, FactorBars, RangeBar, Stat } from '../components'
import { inr, inrShort, levelClass, pct, riskClass, routingClass } from '../format'

const FALLBACK_CITIES = ['Mumbai', 'Pune', 'Bengaluru', 'Delhi', 'Hyderabad', 'Indore']
const FALLBACK_TYPES = ['Apartment', 'Independent House', 'Villa', 'Office Space', 'Retail Shop']
const COMMERCIAL = new Set(['Office Space', 'Retail Shop'])

type Form = Record<'city' | 'locality' | 'property_type' | 'furnishing_status' | 'area_sqft' | 'bedrooms' | 'bathrooms' | 'property_age_years' | 'floor_number' | 'loan_amount_lakh', string>

const INITIAL: Form = {
  city: 'Pune',
  locality: 'Baner',
  property_type: 'Apartment',
  furnishing_status: 'Semi-Furnished',
  area_sqft: '1100',
  bedrooms: '2',
  bathrooms: '2',
  property_age_years: '4',
  floor_number: '7',
  loan_amount_lakh: '60',
}

type ReviewCreated = { review_id: string; review_status: string; routing_label: string; routing_reason: string; notice: string }

export default function ValuationStudio({ summary, onReviewCreated }: { summary: PropertySummary | null; onReviewCreated: () => void }) {
  const [form, setForm] = useState<Form>(INITIAL)
  const [result, setResult] = useState<Valuation | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [review, setReview] = useState<ReviewCreated | null>(null)
  const [reviewError, setReviewError] = useState('')
  const [reviewLoading, setReviewLoading] = useState(false)

  const cities = summary?.cities.map((c) => c.city) ?? FALLBACK_CITIES
  const types = summary?.property_types.length ? summary.property_types : FALLBACK_TYPES
  const localities = summary?.localities[form.city] ?? []
  const commercial = COMMERCIAL.has(form.property_type)

  const set = (key: keyof Form) => (e: { target: { value: string } }) => {
    const value = e.target.value
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'city') next.locality = summary?.localities[value]?.[0] ?? ''
      if (key === 'property_type' && COMMERCIAL.has(value)) next.bedrooms = '0'
      return next
    })
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setReview(null)
    setReviewError('')
    const num = (k: keyof Form) => Number(form[k])
    if (!form.city.trim() || !form.locality.trim()) return setError('Enter both city and locality.')
    if (!(num('area_sqft') >= 50 && num('area_sqft') <= 50000)) return setError('Area must be between 50 and 50,000 sq.ft.')
    for (const k of ['bedrooms', 'bathrooms', 'property_age_years', 'floor_number'] as const) {
      if (!Number.isInteger(num(k)) || num(k) < 0) return setError('Bedrooms, bathrooms, age and floor must be whole numbers ≥ 0.')
    }
    const loanLakh = form.loan_amount_lakh.trim() ? Number(form.loan_amount_lakh) : null
    if (loanLakh !== null && !(loanLakh > 0)) return setError('Loan amount must be a positive number (in lakh).')

    setLoading(true)
    try {
      const data = await postJSON<Valuation>('/api/valuation/', {
        city: form.city,
        locality: form.locality,
        property_type: form.property_type,
        furnishing_status: form.furnishing_status,
        area_sqft: num('area_sqft'),
        bedrooms: num('bedrooms'),
        bathrooms: num('bathrooms'),
        property_age_years: num('property_age_years'),
        floor_number: num('floor_number'),
        loan_amount_inr: loanLakh ? loanLakh * 1e5 : null,
      })
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(err instanceof Error ? err.message : 'Valuation failed.')
    } finally {
      setLoading(false)
    }
  }

  const createReview = async () => {
    if (!result?.valuation_id) return
    setReviewLoading(true)
    setReviewError('')
    try {
      setReview(await postJSON<ReviewCreated>('/api/lender-review/', { valuation_id: result.valuation_id }))
      onReviewCreated()
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : 'Could not create the review.')
    } finally {
      setReviewLoading(false)
    }
  }

  const ds = result?.decision_support
  return (
    <>
      <Card title="Property details" subtitle="Residential or commercial. Add the loan amount to get the LTV check and lending route.">
        <form className="form-grid" onSubmit={submit} noValidate>
          <label>City
            <select value={form.city} onChange={set('city')}>
              {cities.map((c) => <option key={c}>{c}</option>)}
              <option value="Jaipur">Jaipur (outside coverage)</option>
            </select>
          </label>
          <label>Locality
            <input list="locality-options" value={form.locality} onChange={set('locality')} placeholder="e.g. Baner" />
            <datalist id="locality-options">{localities.map((l) => <option key={l} value={l} />)}</datalist>
          </label>
          <label>Property type
            <select value={form.property_type} onChange={set('property_type')}>
              {types.map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label>Built-up area (sq.ft.)
            <input type="number" min="50" max="50000" value={form.area_sqft} onChange={set('area_sqft')} />
          </label>
          <label>Bedrooms
            <input type="number" min="0" max="20" value={form.bedrooms} onChange={set('bedrooms')} disabled={commercial} />
          </label>
          <label>Bathrooms
            <input type="number" min="0" max="20" value={form.bathrooms} onChange={set('bathrooms')} />
          </label>
          <label>Property age (years)
            <input type="number" min="0" max="100" value={form.property_age_years} onChange={set('property_age_years')} />
          </label>
          <label>Floor
            <input type="number" min="0" max="200" value={form.floor_number} onChange={set('floor_number')} />
          </label>
          <label>Furnishing
            <select value={form.furnishing_status} onChange={set('furnishing_status')}>
              <option>Unfurnished</option><option>Semi-Furnished</option><option>Furnished</option>
            </select>
          </label>
          <label>Loan requested (₹ lakh, optional)
            <input type="number" min="0" step="0.5" value={form.loan_amount_lakh} onChange={set('loan_amount_lakh')} placeholder="e.g. 60" />
          </label>
          <button className="btn btn-primary span-all" type="submit" disabled={loading}>
            {loading ? 'Valuing…' : 'Value this property'}
          </button>
        </form>
        <ErrorNote message={error} />
      </Card>

      {result && ds && (
        <>
          <section className="result-hero card">
            <div className="hero-main">
              <div className="hero-tags">
                <Badge tone="info">SYNTHETIC-DATA PROTOTYPE</Badge>
                <Badge tone={levelClass(result.confidence.label)}>{result.confidence.label} confidence · {result.confidence.score}/100</Badge>
                <Badge tone={routingClass(ds.routing)}>{ds.routing_label}</Badge>
              </div>
              <p className="muted">{result.property_input.property_type} · {result.property_input.area_sqft} sq.ft. · {result.property_input.locality}, {result.property_input.city}</p>
              <h2 className="hero-value">{inr(result.estimated_value_inr)}</h2>
              <p className="muted">{inrShort(result.estimated_value_inr)} · {inr(result.rate_per_sqft_inr)}/sq.ft.</p>
              <div className="hero-range">
                <div><small>Low ({result.confidence.interval_level_pct}% range)</small><strong>{inrShort(result.low_estimate_inr)}</strong></div>
                <RangeBar low={result.low_estimate_inr} value={result.estimated_value_inr} high={result.high_estimate_inr} />
                <div className="right"><small>High</small><strong>{inrShort(result.high_estimate_inr)}</strong></div>
              </div>
              <p className="fine">±{result.confidence.relative_half_width_pct}% · {result.confidence.method}</p>
            </div>
            <div className="hero-side">
              <Stat label="Turnaround" value={`${result.latency_ms.toFixed(0)} ms`} hint="Model + evidence lookup" />
              <Stat label="Model version" value={<code>{result.model_version}</code>} />
              <Stat label="Audit record" value={result.valuation_id ? <code>{result.valuation_id.slice(0, 8)}</code> : 'Not saved'} hint={result.audit_saved ? 'Stored with inputs and outputs' : 'Database unavailable'} />
              {result.valuation_id && (
                <a className="btn btn-secondary" href={`${API_BASE}/api/valuation/${result.valuation_id}/report.pdf`}>Download PDF report</a>
              )}
            </div>
          </section>

          {result.coverage_warnings.length > 0 && (
            <div className="alert alert-bad">{result.coverage_warnings.map((w) => <p key={w}>{w}</p>)}</div>
          )}

          <div className="two-col">
            <Card title="Why this value" subtitle={`Main factors behind the estimate, measured against an average property (${inrShort(result.explainability.base_value_inr)}).`}>
              <FactorBars factors={result.explainability.top_factors} />
              <p className="fine">{result.explainability.notice}</p>
            </Card>

            <Card title="Lending decision support" subtitle={ds.notice}>
              {ds.lending ? (
                <div className="stat-grid">
                  <Stat label="Loan requested" value={inrShort(ds.lending.loan_amount_inr)} />
                  <Stat label="Collateral value" value={inrShort(ds.lending.collateral_value_inr)} hint={ds.lending.collateral_basis} />
                  <Stat label="LTV / cap" value={<span className={ds.lending.ltv_pct > ds.lending.max_ltv_pct ? 'text-bad' : ''}>{pct(ds.lending.ltv_pct)} / {pct(ds.lending.max_ltv_pct, 0)}</span>} hint={ds.lending.ltv_policy} />
                  <Stat label="Max eligible loan" value={inrShort(ds.lending.max_eligible_loan_inr)} />
                  <Stat label="Risk band" value={<Badge tone={riskClass(ds.lending.risk_band)}>{ds.lending.risk_band}</Badge>} />
                  <Stat label="Site visit" value={ds.physical_visit_avoided ? 'Not needed' : 'Required'} />
                </div>
              ) : (
                <p className="muted">Add a loan amount to see LTV, the maximum eligible loan and the risk band.</p>
              )}
              <h3>Route: <Badge tone={routingClass(ds.routing)}>{ds.routing_label}</Badge></h3>
              <ul className="reasons">{ds.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <button className="btn btn-primary" type="button" onClick={createReview} disabled={reviewLoading || !result.valuation_id || !!review}>
                {review ? 'Sent to review queue' : reviewLoading ? 'Sending…' : 'Send to lender review queue'}
              </button>
              <ErrorNote message={reviewError} />
              {review && <p className="alert alert-good">Review case {review.review_id.slice(0, 8)} created: {review.routing_label}. Open the Review Queue to record the decision.</p>}
            </Card>
          </div>

          <div className="two-col">
            <Card title="Locality signals" subtitle="Alternative data merged into the model for this locality.">
              <div className="signal-grid">
                {result.locality_signals.map((s) => (
                  <div className="signal" key={s.feature}>
                    <small>{s.source}</small>
                    <strong>{s.feature === 'guideline_rate_per_sqft_inr' ? `${inr(s.value)}/sq.ft.` : s.feature === 'metro_distance_km' ? `${s.value} km` : s.feature === 'infra_score' ? `${s.value} / 10` : `${s.value}%`}</strong>
                    <span>{s.label}</span>
                  </div>
                ))}
              </div>
              {!result.locality_signals[0]?.matched_locality && <p className="fine">Locality not in the signal table; city medians used.</p>}
            </Card>

            <Card title="Comparable evidence" subtitle={result.comparables.notice}>
              <div className="stat-grid three">
                <Stat label="Comparables" value={result.comparables.comparable_count} hint={`${result.comparables.verified_comparable_count} verified`} />
                <Stat label="Comparable estimate" value={inrShort(result.comparables.comparable_estimate_inr)} />
                <Stat label="Model vs comparables" value={result.comparables.model_vs_comparable_gap_pct == null ? '—' : `${result.comparables.model_vs_comparable_gap_pct > 0 ? '+' : ''}${result.comparables.model_vs_comparable_gap_pct}%`} />
              </div>
              {result.comparables.records.length > 0 && (
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Date</th><th>Area</th><th>Price</th><th>₹/sq.ft.</th><th>Source</th></tr></thead>
                    <tbody>
                      {result.comparables.records.map((c, i) => (
                        <tr key={i}>
                          <td>{c.transaction_date ?? '—'}</td>
                          <td>{c.area_sqft}</td>
                          <td>{inrShort(c.transaction_value_inr)}</td>
                          <td>{inr(c.rate_per_sqft_inr)}</td>
                          <td>{c.data_source}{c.is_verified ? ' ✓' : ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
          <p className="fine disclaimer">{result.disclaimer}</p>
        </>
      )}
    </>
  )
}
