import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { API_BASE, getJSON, type ModelInfo, type PropertySummary } from './api'
import { PAGES, type PageId } from './pages'
import BatchValuation from './pages/BatchValuation'
import DataSources from './pages/DataSources'
import ModelAccuracy from './pages/ModelAccuracy'
import Overview from './pages/Overview'
import PropertyExplorer from './pages/PropertyExplorer'
import ReviewQueue from './pages/ReviewQueue'
import ValuationStudio from './pages/ValuationStudio'

const pageFromHash = (): PageId => {
  const id = window.location.hash.replace('#', '') as PageId
  return PAGES.some((p) => p.id === id) ? id : 'overview'
}

function App() {
  const [page, setPage] = useState<PageId>(pageFromHash)
  const [summary, setSummary] = useState<PropertySummary | null>(null)
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [apiError, setApiError] = useState('')
  const [reviewTick, setReviewTick] = useState(0)

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    Promise.all([getJSON<PropertySummary>('/api/properties/summary'), getJSON<ModelInfo>('/api/valuation/model-info')])
      .then(([s, m]) => { setSummary(s); setModelInfo(m) })
      .catch((err: Error) => setApiError(err.message))
  }, [])

  const go = useCallback((id: PageId) => {
    window.location.hash = id
    setPage(id)
    window.scrollTo({ top: 0 })
  }, [])
  const bumpReviews = useCallback(() => setReviewTick((t) => t + 1), [])

  const meta = PAGES.find((p) => p.id === page) ?? PAGES[0]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">A</span> AURA</div>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {PAGES.map((p) => (
            <button key={p.id} type="button" className={`nav-item ${page === p.id ? 'active' : ''}`} onClick={() => go(p.id)}>
              <span className="nav-icon" aria-hidden="true">{p.icon}</span> {p.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          Digital property valuation for India
          <br />
          {modelInfo?.available ? <code>{modelInfo.model_version}</code> : 'Model loading…'}
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <select className="mobile-nav" value={page} onChange={(e) => go(e.target.value as PageId)} aria-label="Page">
            {PAGES.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          <span className="topbar-title">{meta.label}</span>
          <span className="demo-badge" title="All data in this prototype is synthetic and labelled SYNTHETIC_DEMO">● DEMO · SYNTHETIC DATA</span>
        </header>

        <section className="page-heading">
          <p className="eyebrow">HERO HOUSING FINANCE · PROBLEM STATEMENT 1</p>
          <h1>{meta.title}</h1>
          <p>{meta.blurb}</p>
        </section>

        <div className="page-body">
          {apiError && (
            <div className="alert alert-bad">
              <p><strong>Cannot reach the AURA API.</strong> {apiError}</p>
              <p className="fine">Start it with <code>docker compose up --build</code> (API at {API_BASE}).</p>
            </div>
          )}
          {page === 'overview' && <Overview summary={summary} modelInfo={modelInfo} go={go} />}
          {page === 'valuation' && <ValuationStudio summary={summary} onReviewCreated={bumpReviews} />}
          {page === 'batch' && <BatchValuation onDone={bumpReviews} />}
          {page === 'reviews' && <ReviewQueue refreshKey={reviewTick} />}
          {page === 'model' && <ModelAccuracy info={modelInfo} error={apiError} />}
          {page === 'data' && <DataSources />}
          {page === 'properties' && <PropertyExplorer summary={summary} />}
        </div>
      </main>
    </div>
  )
}

export default App
