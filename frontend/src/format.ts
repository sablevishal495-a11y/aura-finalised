const inrFormatter = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

export const inr = (value: number | null | undefined) => (value == null ? '—' : inrFormatter.format(value))

/** ₹1.25 Cr / ₹48.6 L style, the way Indian lenders read amounts. */
export function inrShort(value: number | null | undefined): string {
  if (value == null) return '—'
  if (Math.abs(value) >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`
  if (Math.abs(value) >= 1e5) return `₹${(value / 1e5).toFixed(1)} L`
  return inr(value)
}

export const pct = (value: number | null | undefined, digits = 1) => (value == null ? '—' : `${value.toFixed(digits)}%`)

export const humanize = (value: string) =>
  value
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')

export const routingClass = (routing: string) =>
  routing === 'AUTO_DESK_VALUATION' ? 'good' : routing === 'DESKTOP_REVIEW' ? 'warn' : 'bad'

export const levelClass = (level: string | null | undefined) =>
  level === 'High' ? 'good' : level === 'Medium' ? 'warn' : 'bad'

export const riskClass = (level: string | null | undefined) =>
  level === 'Low' ? 'good' : level === 'Medium' ? 'warn' : 'bad'

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'
