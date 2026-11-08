import { useEffect, useState } from 'react'
import { getJSON, postFile } from '../api'
import { Badge, Card, ErrorNote } from '../components'
import { humanize } from '../format'

type Source = {
  source_id: string
  name: string
  category: string
  examples: string[]
  collection: string
  cleaning: string
  merge_key: string
  model_use: string
  demo_status: string
  demo_note: string
}
type Catalog = { sources: Source[]; pipeline_contract: string[]; status_notice: string }
type ImportResult = {
  filename: string
  total_rows: number
  inserted_records: number
  rejected_records: number
  duplicates_in_file: number
  duplicates_in_database: number
  rejected_rows: { csv_row: number | null; reasons: string[] }[]
  notice: string
}
type Guideline = {
  source: string
  financial_year: string
  coverage: string
  results: { serial_no: string; locality_as_extracted: string; raw_rate_columns_as_extracted: string; source_page: string }[]
  critical_notice: string
}

const statusTone = (s: string) => (s === 'live_in_demo' ? 'good' : s === 'simulated_in_demo' ? 'warn' : 'bad')

export default function DataSources() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState('')
  const [query, setQuery] = useState('')
  const [guideline, setGuideline] = useState<Guideline | null>(null)
  const [guidelineError, setGuidelineError] = useState('')

  useEffect(() => {
    getJSON<Catalog>('/api/data-catalog/').then(setCatalog).catch((e: Error) => setError(e.message))
  }, [])

  const upload = async () => {
    if (!file) return
    setImportError('')
    try {
      setImportResult(await postFile<ImportResult>('/api/data-import/comparables-csv', file))
    } catch (err) {
      setImportResult(null)
      setImportError(err instanceof Error ? err.message : 'Import failed.')
    }
  }

  const search = async () => {
    setGuidelineError('')
    try {
      setGuideline(await getJSON<Guideline>(`/api/government-guideline/?limit=10&q=${encodeURIComponent(query)}`))
    } catch (err) {
      setGuidelineError(err instanceof Error ? err.message : 'Search failed.')
    }
  }

  return (
    <>
      <Card title="How data is collected, cleaned and merged" subtitle={catalog?.status_notice}>
        <ErrorNote message={error} />
        <ol className="pipeline">
          {catalog?.pipeline_contract.map((step) => <li key={step}>{step}</li>)}
        </ol>
      </Card>

      <div className="source-grid">
        {catalog?.sources.map((s) => (
          <article className="card source-card" key={s.source_id}>
            <div className="card-head">
              <div>
                <h3>{s.name}</h3>
                <small className="muted">{humanize(s.category)}</small>
              </div>
              <Badge tone={statusTone(s.demo_status)}>{humanize(s.demo_status)}</Badge>
            </div>
            <dl className="kv compact">
              <dt>Examples</dt><dd>{s.examples.join(', ')}</dd>
              <dt>Collect</dt><dd>{s.collection}</dd>
              <dt>Clean</dt><dd>{s.cleaning}</dd>
              <dt>Merge on</dt><dd>{s.merge_key}</dd>
              <dt>Model use</dt><dd>{s.model_use}</dd>
            </dl>
            <p className="fine">{s.demo_note}</p>
          </article>
        ))}
      </div>

      <div className="two-col">
        <Card title="Import comparable transactions" subtitle="CSV with city, locality, property_type, area_sqft, transaction_value_inr (optional: transaction_date, source_record_id, source_name).">
          <div className="upload-row">
            <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button className="btn btn-primary" type="button" disabled={!file} onClick={upload}>Validate and import</button>
          </div>
          <ErrorNote message={importError} />
          {importResult && (
            <div className="alert alert-good">
              <p><strong>{importResult.inserted_records}</strong> of {importResult.total_rows} rows imported · {importResult.rejected_records} rejected ({importResult.duplicates_in_file} duplicates in file, {importResult.duplicates_in_database} already in database).</p>
              {importResult.rejected_rows.slice(0, 8).map((r, i) => <p key={i} className="fine">Row {r.csv_row}: {r.reasons.join('; ')}</p>)}
              <p className="fine">{importResult.notice}</p>
            </div>
          )}
        </Card>

        <Card title="Government guideline rates (Indore, FY 2026-27)" subtitle="Raw extract from the official district guideline PDF - a government-records benchmark.">
          <div className="upload-row">
            <input placeholder="Search locality (Hindi text), or leave blank" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} />
            <button className="btn btn-primary" type="button" onClick={search}>Search</button>
          </div>
          <ErrorNote message={guidelineError} />
          {guideline && (
            <>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>#</th><th>Locality (as extracted)</th><th>Page</th></tr></thead>
                  <tbody>
                    {guideline.results.map((r) => (
                      <tr key={r.serial_no}><td>{r.serial_no}</td><td>{r.locality_as_extracted}</td><td>{r.source_page}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="fine">{guideline.coverage}. {guideline.critical_notice}</p>
            </>
          )}
        </Card>
      </div>
    </>
  )
}
