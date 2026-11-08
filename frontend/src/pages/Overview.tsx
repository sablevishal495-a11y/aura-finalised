import type { ModelInfo, PropertySummary } from '../api'
import { Badge, Card, Stat } from '../components'
import { inr, pct } from '../format'
import type { PageId } from '../pages'

const POINTS: { n: number; title: string; how: string; page: PageId }[] = [
  { n: 1, title: 'Scope the market', how: '5 property types (3 residential, 2 commercial) in 6 cities. Phased rollout to Tier-2 cities and all states below.', page: 'overview' },
  { n: 2, title: 'Combine data sources', how: 'Transactions + government guideline rates + property attributes, merged with satellite, geo-spatial, infrastructure and market-trend signals per locality.', page: 'data' },
  { n: 3, title: 'Build the AI/ML model', how: 'LightGBM on 14 features, compared with a rate-card AVM and guideline rates on a held-out test set (MAPE, PPE10, PPE20).', page: 'model' },
  { n: 4, title: 'Make it explainable', how: 'Every valuation shows the value, a calibrated 90% range, a confidence score, SHAP factors, comparables, and a PDF + audit record.', page: 'valuation' },
  { n: 5, title: 'Automate and scale', how: 'API-first, ~10 ms per property, batch CSV of up to 1,000 properties, Docker deployment, model versioning.', page: 'batch' },
  { n: 6, title: 'Enable lending decisions', how: 'LTV vs RBI caps, risk band, max eligible loan, and routing to desk valuation / desktop review / physical inspection with reviewer sign-off.', page: 'reviews' },
]

const FLOW = [
  { title: 'Data sources', items: ['Transactions (IGR)', 'Guideline rates', 'Property attributes', 'Satellite · Geo-spatial', 'Infrastructure · Market trends'] },
  { title: 'Pipeline', items: ['Validate & quarantine', 'Normalise names & units', 'De-duplicate', 'Merge on locality', 'Provenance & lineage'] },
  { title: 'Valuation engine', items: ['LightGBM value model', 'Per-property error model', 'Conformal 90% range', 'SHAP explanations', 'Comparable evidence'] },
  { title: 'Lender workflow', items: ['LTV vs RBI caps', 'Risk band', 'Desk / desktop / physical route', 'Reviewer sign-off', 'PDF + audit trail'] },
]

const ROLLOUT = [
  ['Phase 1 (now)', 'Mumbai, Pune, Bengaluru, Delhi, Hyderabad, Indore', 'Apartments, independent houses, villas, offices, retail shops'],
  ['Phase 2 (+6 months)', 'Tier-1 + top 20 Tier-2 cities (Jaipur, Lucknow, Ahmedabad, Kochi, Nagpur…)', 'Add plots and mixed-use; state IGR feeds per city'],
  ['Phase 3 (+12 months)', 'All states, district by district, as transaction feeds are licensed', 'Warehouses and industrial; rural / peri-urban with satellite-led features'],
]

export default function Overview({ summary, modelInfo, go }: { summary: PropertySummary | null; modelInfo: ModelInfo | null; go: (p: PageId) => void }) {
  const metrics = modelInfo?.available ? modelInfo.metrics : null
  const rateCard = modelInfo?.available ? modelInfo.baselines.rate_card_avm : null
  return (
    <>
      <section className="stat-grid four">
        <Stat label="Properties in dataset" value={summary ? summary.total_properties.toLocaleString('en-IN') : '—'} hint="Synthetic demo records" />
        <Stat label="Coverage" value={summary ? `${summary.cities.length} cities · ${summary.property_types.length} types` : '—'} hint={summary?.segments.join(' + ')} />
        <Stat label="Model error (MAPE)" value={metrics ? pct(metrics.mape_pct) : '—'} hint={rateCard ? `vs ${pct(rateCard.mape_pct)} for a rate-card AVM` : undefined} />
        <Stat label="Within ±10% (PPE10)" value={metrics ? pct(metrics.ppe10_pct) : '—'} hint={rateCard ? `vs ${pct(rateCard.ppe10_pct)} for a rate-card AVM` : undefined} />
      </section>

      <Card title="Solution design" subtitle="Data → model → output → lender workflow">
        <div className="flow">
          {FLOW.map((step, i) => (
            <div className="flow-step" key={step.title}>
              <div className="flow-box">
                <h3>{step.title}</h3>
                <ul>{step.items.map((it) => <li key={it}>{it}</li>)}</ul>
              </div>
              {i < FLOW.length - 1 && <span className="flow-arrow" aria-hidden="true">→</span>}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Problem Statement 1 - how AURA covers each point">
        <div className="points">
          {POINTS.map((p) => (
            <button type="button" className="point" key={p.n} onClick={() => go(p.page)}>
              <span className="point-n">{p.n}</span>
              <span>
                <strong>{p.title}</strong>
                <small>{p.how}</small>
              </span>
            </button>
          ))}
        </div>
      </Card>

      <div className="stack">
        <Card title="Current coverage" subtitle="Median rate per sq.ft. by city and property type (synthetic demo data).">
          <div className="table-wrap">
            <table>
              <thead><tr><th>City</th>{summary?.property_types.map((t) => <th key={t}>{t}</th>)}</tr></thead>
              <tbody>
                {summary?.cities.map((c) => (
                  <tr key={c.city}>
                    <td><strong>{c.city}</strong></td>
                    {summary.property_types.map((t) => {
                      const cell = c.types.find((x) => x.property_type === t)
                      return <td key={t}>{cell ? inr(cell.median_rate_per_sqft_inr) : '—'}</td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Rollout plan across India">
          <div className="rollout">
            {ROLLOUT.map(([phase, where, what]) => (
              <div key={phase}>
                <Badge tone="info">{phase}</Badge>
                <p><strong>{where}</strong></p>
                <p className="muted">{what}</p>
              </div>
            ))}
          </div>
          <p className="fine">Each new city goes live only after its out-of-time accuracy and range coverage pass the same tests as Phase 1. Until then AURA routes it to physical inspection.</p>
        </Card>
      </div>
    </>
  )
}
