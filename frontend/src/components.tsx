import type { ReactNode } from 'react'
import type { Factor } from './api'

export function Badge({ tone, children }: { tone: 'good' | 'warn' | 'bad' | 'info' | string; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  )
}

export function Card({ title, subtitle, actions, children, className = '' }: {
  title?: string
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return message ? <p className="error-message" role="alert">{message}</p> : null
}

export function FactorBars({ factors }: { factors: Factor[] }) {
  const max = Math.max(...factors.map((f) => Math.abs(f.impact_pct)), 1)
  return (
    <div className="factor-list">
      {factors.map((f) => {
        const width = `${(Math.abs(f.impact_pct) / max) * 50}%`
        const up = f.impact_pct >= 0
        return (
          <div className="factor-row" key={f.feature}>
            <div className="factor-label">
              <strong>{f.label}</strong>
              <small>{f.value} · {f.source}</small>
            </div>
            <div className="factor-track" aria-hidden="true">
              <span className="factor-axis" />
              <span className={`factor-bar ${up ? 'up' : 'down'}`} style={up ? { left: '50%', width } : { right: '50%', width }} />
            </div>
            <span className={`factor-value ${up ? 'up' : 'down'}`}>{up ? '+' : ''}{f.impact_pct.toFixed(1)}%</span>
          </div>
        )
      })}
    </div>
  )
}

export function RangeBar({ low, value, high }: { low: number; value: number; high: number }) {
  const span = high - low || 1
  const pos = ((value - low) / span) * 100
  return (
    <div className="range-bar" aria-hidden="true">
      <span className="range-fill" />
      <span className="range-marker" style={{ left: `${pos}%` }} />
    </div>
  )
}
