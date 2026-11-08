import { useCallback, useEffect, useState } from 'react'
import { API_BASE, getJSON, postJSON, type Review, type ReviewSummary } from '../api'
import { Badge, Card, ErrorNote, Stat } from '../components'
import { dateTime, humanize, inrShort, levelClass, pct, riskClass, routingClass } from '../format'

const DECISIONS = [
  ['ACCEPTED_DESK_VALUATION', 'Accept desk valuation'],
  ['ACCEPTED_AFTER_DESKTOP_REVIEW', 'Accept after desktop review'],
  ['PHYSICAL_INSPECTION_ORDERED', 'Order physical inspection'],
  ['REJECTED_INSUFFICIENT_EVIDENCE', 'Reject - insufficient evidence'],
] as const

function DecisionForm({ review, onSaved }: { review: Review; onSaved: () => void }) {
  const suggested = review.review_status === 'AUTO_DESK_VALUATION'
    ? 'ACCEPTED_DESK_VALUATION'
    : review.review_status === 'DESKTOP_REVIEW' ? 'ACCEPTED_AFTER_DESKTOP_REVIEW' : 'PHYSICAL_INSPECTION_ORDERED'
  const [decision, setDecision] = useState<string>(suggested)
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!name.trim()) return setError('Enter the reviewer name for the audit trail.')
    setSaving(true)
    setError('')
    try {
      await postJSON(`/api/lender-review/${review.review_id}/decision`, { decision, reviewer_name: name, note })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the decision.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="decision-form">
      <select value={decision} onChange={(e) => setDecision(e.target.value)}>
        {DECISIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <input placeholder="Reviewer name" value={name} onChange={(e) => setName(e.target.value)} />
      <input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      <button className="btn btn-primary" type="button" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Record decision'}</button>
      <ErrorNote message={error} />
    </div>
  )
}

export default function ReviewQueue({ refreshKey }: { refreshKey: number }) {
  const [reviews, setReviews] = useState<Review[]>([])
  const [summary, setSummary] = useState<ReviewSummary | null>(null)
  const [error, setError] = useState('')
  const [pendingOnly, setPendingOnly] = useState(false)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      getJSON<{ reviews: Review[] }>(`/api/lender-review/?limit=100&pending_only=${pendingOnly}`),
      getJSON<ReviewSummary>('/api/lender-review/summary'),
    ])
      .then(([list, stats]) => {
        if (cancelled) return
        setReviews(list.reviews)
        setSummary(stats)
        setError('')
      })
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => { cancelled = true }
  }, [pendingOnly, tick, refreshKey])

  return (
    <>
      {summary && (
        <section className="stat-grid four">
          <Stat label="Valuations run" value={summary.total_valuations} hint={`avg ${summary.avg_valuation_latency_ms.toFixed(0)} ms each`} />
          <Stat label="Valuations without a site visit" value={pct(summary.valuations_without_site_visit_pct)} hint="Routed to desk or desktop review" />
          <Stat label="Review cases" value={summary.total_reviews} hint={`${summary.by_decision.PENDING ?? 0} awaiting decision`} />
          <Stat label="Physical visits avoided (cases)" value={pct(summary.physical_visits_avoided_pct)} hint={summary.notice} />
        </section>
      )}
      <Card
        title="Lender review queue"
        subtitle="Each case links to its stored valuation. AURA suggests the route; the reviewer records the decision."
        actions={
          <label className="inline-check">
            <input type="checkbox" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} /> Pending only
          </label>
        }
      >
        <ErrorNote message={error} />
        {reviews.length === 0 && !error && <p className="muted">No review cases yet. Value a property in Valuation Studio and send it to the queue.</p>}
        <div className="review-list">
          {reviews.map((r) => (
            <article className="review-card" key={r.review_id}>
              <div className="review-head">
                <div>
                  <strong>{r.property_input.locality}, {r.property_input.city}</strong>
                  <small>{r.property_input.property_type} · {r.property_input.area_sqft} sq.ft. · case {r.review_id.slice(0, 8)} · {dateTime(r.created_at)}</small>
                </div>
                <Badge tone={routingClass(r.review_status)}>{humanize(r.review_status)}</Badge>
              </div>
              <div className="review-stats">
                <span><small>Value</small><strong>{inrShort(r.estimated_value_inr)}</strong></span>
                <span><small>Range</small><strong>{inrShort(r.low_estimate_inr)} – {inrShort(r.high_estimate_inr)}</strong></span>
                <span><small>Confidence</small>{r.confidence_label ? <Badge tone={levelClass(r.confidence_label)}>{r.confidence_label}</Badge> : '—'}</span>
                <span><small>Loan / LTV</small><strong>{r.loan_amount_inr ? `${inrShort(r.loan_amount_inr)} / ${pct(r.ltv_pct)}` : '—'}</strong></span>
                <span><small>Risk</small>{r.risk_band ? <Badge tone={riskClass(r.risk_band)}>{r.risk_band}</Badge> : '—'}</span>
                <span><small>Comparables</small><strong>{r.comparable_count} ({r.verified_comparable_count} verified)</strong></span>
              </div>
              <p className="muted">{r.routing_reason}</p>
              <div className="review-foot">
                <small>Model <code>{r.model_version ?? '—'}</code>{r.valuation_id && <> · <a href={`${API_BASE}/api/valuation/${r.valuation_id}/report.pdf`}>PDF report</a></>}</small>
                {r.reviewer_decision ? (
                  <Badge tone={r.reviewer_decision.startsWith('ACCEPTED') ? 'good' : 'warn'}>
                    {humanize(r.reviewer_decision)} · {r.reviewer_name} · {dateTime(r.decided_at)}
                  </Badge>
                ) : null}
              </div>
              {!r.reviewer_decision && <DecisionForm review={r} onSaved={reload} />}
              {r.decision_note && <p className="fine">Note: {r.decision_note}</p>}
            </article>
          ))}
        </div>
      </Card>
    </>
  )
}
