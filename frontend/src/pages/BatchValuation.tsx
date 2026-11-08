import { useState } from 'react'
import { postFile, type BatchResult } from '../api'
import { Badge, Card, ErrorNote, Stat } from '../components'
import { humanize, inrShort, levelClass, pct, riskClass, routingClass } from '../format'

const SAMPLE = `city,locality,property_type,area_sqft,bedrooms,bathrooms,property_age_years,floor_number,furnishing_status,loan_amount_inr
Mumbai,Powai,Apartment,950,2,2,6,12,Semi-Furnished,9000000
Pune,Baner,Apartment,1100,2,2,3,7,Unfurnished,6000000
Bengaluru,Whitefield,Office Space,2400,0,2,8,5,Furnished,
Indore,Vijay Nagar,Retail Shop,400,0,1,10,0,Unfurnished,1200000
Delhi,Saket,Villa,4200,5,5,12,0,Furnished,
Hyderabad,Gachibowli,Apartment,1500,3,3,1,15,Semi-Furnished,8000000
Pune,Kothrud,Apartment,850,2,2,9,4,Semi-Furnished,4500000
Bengaluru,Indiranagar,Apartment,1300,3,2,5,6,Furnished,9000000
Hyderabad,HITEC City,Office Space,1800,0,2,4,9,Unfurnished,
Jaipur,Malviya Nagar,Apartment,1200,2,2,5,3,Unfurnished,
`

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export default function BatchValuation({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<BatchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async (input: File) => {
    setLoading(true)
    setError('')
    try {
      setResult(await postFile<BatchResult>('/api/valuation/batch', input))
      onDone()
    } catch (err) {
      setResult(null)
      setError(err instanceof Error ? err.message : 'Batch valuation failed.')
    } finally {
      setLoading(false)
    }
  }

  const exportResults = () => {
    if (!result) return
    const header = 'csv_row,city,locality,property_type,area_sqft,estimated_value_inr,low_estimate_inr,high_estimate_inr,confidence,routing,ltv_pct,risk_band,valuation_id'
    const lines = result.results.map((r) =>
      [r.csv_row, r.city, r.locality, r.property_type, r.area_sqft, r.estimated_value_inr, r.low_estimate_inr, r.high_estimate_inr, r.confidence, r.routing, r.ltv_pct ?? '', r.risk_band ?? '', r.valuation_id ?? '']
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(','),
    )
    download('aura-batch-valuations.csv', [header, ...lines].join('\n'))
  }

  return (
    <>
      <Card
        title="Portfolio / batch valuation"
        subtitle="Upload a CSV of properties (up to 1,000 rows). Every row is valued, explained, routed and stored for audit - no manual steps."
        actions={<button className="btn btn-secondary" type="button" onClick={() => download('aura-batch-sample.csv', SAMPLE)}>Download sample CSV</button>}
      >
        <div className="upload-row">
          <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button className="btn btn-primary" type="button" disabled={!file || loading} onClick={() => file && run(file)}>
            {loading ? 'Valuing…' : 'Run batch valuation'}
          </button>
          <button className="btn btn-ghost" type="button" disabled={loading} onClick={() => run(new File([SAMPLE], 'aura-batch-sample.csv', { type: 'text/csv' }))}>
            Try with sample data
          </button>
        </div>
        <p className="fine">Required columns: city, locality, area_sqft. Optional: property_type, bedrooms, bathrooms, property_age_years, floor_number, furnishing_status, loan_amount_inr.</p>
        <ErrorNote message={error} />
      </Card>

      {result && (
        <>
          <section className="stat-grid four">
            <Stat label="Properties valued" value={`${result.rows_valued} / ${result.rows_received}`} hint={`${result.rows_rejected} rejected with reasons`} />
            <Stat label="Total time" value={`${(result.total_time_ms / 1000).toFixed(2)} s`} hint={`${result.avg_time_per_property_ms.toFixed(1)} ms per property`} />
            <Stat label="No site visit needed" value={pct(result.physical_visits_avoided_pct)} hint="Desk valuation or desktop review" />
            <Stat label="Routing" value={<span className="route-mix">{Object.entries(result.routing_counts).map(([k, v]) => <Badge key={k} tone={routingClass(k)}>{humanize(k)}: {v}</Badge>)}</span>} />
          </section>
          <Card title="Results" actions={<button className="btn btn-secondary" type="button" onClick={exportResults}>Export CSV</button>}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Row</th><th>Property</th><th>Value</th><th>Range</th><th>Confidence</th><th>LTV</th><th>Risk</th><th>Route</th><th>Top factor</th></tr>
                </thead>
                <tbody>
                  {result.results.map((r) => (
                    <tr key={r.csv_row}>
                      <td>{r.csv_row}</td>
                      <td><strong>{r.locality}, {r.city}</strong><br /><small>{r.property_type} · {r.area_sqft} sq.ft.</small>{r.coverage_warnings.length > 0 && <><br /><small className="text-bad">Outside coverage</small></>}</td>
                      <td>{inrShort(r.estimated_value_inr)}</td>
                      <td><small>{inrShort(r.low_estimate_inr)} – {inrShort(r.high_estimate_inr)}</small></td>
                      <td><Badge tone={levelClass(r.confidence)}>{r.confidence}</Badge></td>
                      <td>{pct(r.ltv_pct)}</td>
                      <td>{r.risk_band ? <Badge tone={riskClass(r.risk_band)}>{r.risk_band}</Badge> : '—'}</td>
                      <td><Badge tone={routingClass(r.routing)}>{humanize(r.routing)}</Badge></td>
                      <td>{r.top_factor}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.errors.length > 0 && (
              <div className="alert alert-bad">
                {result.errors.map((e) => <p key={e.csv_row}>Row {e.csv_row}: {e.errors.join('; ')}</p>)}
              </div>
            )}
            <p className="fine">{result.disclaimer}</p>
          </Card>
        </>
      )}
    </>
  )
}
