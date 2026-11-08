import { useEffect, useState } from 'react'
import { getJSON, type PropertySummary } from '../api'
import { Card, ErrorNote } from '../components'
import { inr, inrShort } from '../format'

type Property = {
  property_id: string
  city: string
  locality: string
  property_type: string
  segment: string
  area_sqft: number
  bedrooms: number
  property_age_years: number
  furnishing_status: string
  rate_per_sqft_inr: number
  estimated_value_inr: number
  data_source: string
}

const PAGE_SIZE = 24

export default function PropertyExplorer({ summary }: { summary: PropertySummary | null }) {
  const [city, setCity] = useState('')
  const [type, setType] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<{ total: number; data: Property[] } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
    if (city) params.set('city', city)
    if (type) params.set('property_type', type)
    let cancelled = false
    getJSON<{ total: number; data: Property[] }>(`/api/properties/?${params}`)
      .then((d) => { if (!cancelled) { setData(d); setError('') } })
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => { cancelled = true }
  }, [city, type, offset])

  return (
    <Card
      title="Property dataset"
      subtitle={data ? `${data.total.toLocaleString('en-IN')} properties match · synthetic demo records` : 'Loading…'}
      actions={
        <div className="filters">
          <select value={city} onChange={(e) => { setCity(e.target.value); setOffset(0) }}>
            <option value="">All cities</option>
            {summary?.cities.map((c) => <option key={c.city}>{c.city}</option>)}
          </select>
          <select value={type} onChange={(e) => { setType(e.target.value); setOffset(0) }}>
            <option value="">All types</option>
            {summary?.property_types.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      }
    >
      <ErrorNote message={error} />
      <div className="property-grid">
        {data?.data.map((p) => (
          <article className="property-card" key={p.property_id}>
            <div className={`property-visual ${p.segment === 'Commercial' ? 'commercial' : ''}`}>{p.segment === 'Commercial' ? '▥' : '⌂'}</div>
            <div className="property-info">
              <span className="property-tag">{p.segment} · {p.data_source}</span>
              <h3>{p.locality}, {p.city}</h3>
              <p>{p.property_type} · {p.area_sqft} sq.ft.{p.bedrooms ? ` · ${p.bedrooms} BHK` : ''}</p>
              <div className="property-footer">
                <strong>{inrShort(p.estimated_value_inr)}</strong>
                <span>{inr(p.rate_per_sqft_inr)}/sq.ft.</span>
              </div>
            </div>
          </article>
        ))}
      </div>
      {data && data.total > PAGE_SIZE && (
        <div className="pager">
          <button className="btn btn-ghost" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>← Previous</button>
          <span className="muted">{offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}</span>
          <button className="btn btn-ghost" type="button" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next →</button>
        </div>
      )}
    </Card>
  )
}
