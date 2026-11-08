import type { ModelInfo } from '../api'
import { Badge, Card, ErrorNote, Stat } from '../components'
import { dateTime, inrShort, pct } from '../format'

export default function ModelAccuracy({ info, error }: { info: ModelInfo | null; error: string }) {
  if (error) return <ErrorNote message={error} />
  if (!info) return <p className="muted">Loading model card…</p>
  if (!info.available) return <ErrorNote message={`Model unavailable: ${info.error}`} />

  const rows = [
    { name: 'AURA (LightGBM + locality signals)', m: info.metrics, ours: true },
    ...Object.values(info.baselines).map((b) => ({ name: b.name, m: b, ours: false })),
  ]
  const maxMape = Math.max(...rows.map((r) => r.m.mape_pct))
  const improvement = info.baselines.rate_card_avm
    ? ((info.baselines.rate_card_avm.mape_pct - info.metrics.mape_pct) / info.baselines.rate_card_avm.mape_pct) * 100
    : null

  return (
    <>
      <div className="alert alert-warn">{info.notice}</div>
      <section className="stat-grid four">
        <Stat label="MAPE (lower is better)" value={pct(info.metrics.mape_pct)} hint={improvement != null ? `${improvement.toFixed(0)}% lower error than the rate-card AVM` : undefined} />
        <Stat label="PPE10 (within ±10%)" value={pct(info.metrics.ppe10_pct)} hint="Industry-standard AVM hit rate" />
        <Stat label="90% range coverage" value={pct(info.metrics.interval_coverage_pct)} hint={`Median range ±${info.metrics.median_interval_half_width_pct.toFixed(1)}%`} />
        <Stat label="R²" value={info.metrics.r2.toFixed(3)} hint={`MAE ${inrShort(info.metrics.mae_inr)}`} />
      </section>

      <Card title="Accuracy vs existing valuation methods" subtitle={`Held-out test set of ${info.rows.test} properties never seen in training or calibration.`}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Method</th><th>MAPE</th><th className="bar-col">Error</th><th>Median APE</th><th>PPE10</th><th>PPE20</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} className={r.ours ? 'highlight' : ''}>
                  <td>{r.ours ? <strong>{r.name}</strong> : r.name}</td>
                  <td>{pct(r.m.mape_pct)}</td>
                  <td className="bar-col"><span className={`hbar ${r.ours ? 'ours' : ''}`} style={{ width: `${(r.m.mape_pct / maxMape) * 100}%` }} /></td>
                  <td>{pct(r.m.median_ape_pct)}</td>
                  <td>{pct(r.m.ppe10_pct)}</td>
                  <td>{pct(r.m.ppe20_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="fine">MAPE = mean absolute % error. PPE10 / PPE20 = share of estimates within ±10% / ±20% of the actual price.</p>
      </Card>

      <div className="two-col">
        <Card title="Error by segment" subtitle="Where the model is strong and where it needs more data.">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Segment</th><th>Rows</th><th>MAPE</th><th>PPE10</th><th>Range coverage</th></tr></thead>
              <tbody>
                {info.segments.map((s) => (
                  <tr key={s.dimension + s.segment}>
                    <td>{s.segment} <small className="muted">{s.dimension === 'city' ? 'city' : 'type'}</small></td>
                    <td>{s.test_rows}</td>
                    <td>{pct(s.mape_pct)}</td>
                    <td>{pct(s.ppe10_pct)}</td>
                    <td>{pct(s.interval_coverage_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Model card" subtitle={info.model}>
          <dl className="kv">
            <dt>Version</dt><dd><code>{info.model_version}</code></dd>
            <dt>Trained</dt><dd>{dateTime(info.trained_at)}</dd>
            <dt>Data</dt><dd><Badge tone="info">{info.data_source}</Badge></dd>
            <dt>Split</dt><dd>{info.rows.train} train · {info.rows.calibration} calibration · {info.rows.test} test</dd>
            <dt>Target</dt><dd>log(market value) → INR</dd>
            <dt>Confidence</dt><dd>Second model predicts each property's expected error; split-conformal calibration makes the 90% range hold on unseen data.</dd>
            <dt>Explainability</dt><dd>SHAP TreeExplainer per valuation</dd>
          </dl>
          <h3>Features ({info.features.length})</h3>
          <div className="chip-row">
            {info.features.map((f) => <Badge key={f.feature} tone={f.group === 'Locality signal' ? 'info' : 'neutral'}>{f.feature}</Badge>)}
          </div>
        </Card>
      </div>

      <Card title="How accuracy would be proven on real data">
        <ol className="steps">
          <li><strong>Ground truth:</strong> registered sale prices (IGR) and the lender's own disbursed-loan valuations, matched to properties.</li>
          <li><strong>Out-of-time test:</strong> train on transactions up to month T, test on months T+1…T+3, so the model never sees the future.</li>
          <li><strong>Out-of-area test:</strong> hold out whole localities to measure how the model behaves where it has little data.</li>
          <li><strong>Same test set for every method:</strong> AURA vs the incumbent AVM vs guideline rates vs physical valuer reports, using MAPE, PPE10 and PPE20.</li>
          <li><strong>Confidence check:</strong> the 90% range must contain ~90% of actual prices in every city and property type.</li>
          <li><strong>Shadow pilot:</strong> run AURA alongside physical valuations for 3 months and compare, before switching any case to desk valuation.</li>
        </ol>
      </Card>
    </>
  )
}
