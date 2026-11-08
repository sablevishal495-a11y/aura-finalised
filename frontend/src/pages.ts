export type PageId = 'overview' | 'valuation' | 'batch' | 'reviews' | 'model' | 'data' | 'properties'

export const PAGES: { id: PageId; label: string; icon: string; title: string; blurb: string }[] = [
  { id: 'overview', label: 'Overview', icon: '◎', title: 'AI-Powered Digital Property Valuation Engine', blurb: 'How AURA values residential and commercial property across India and fits a lender’s workflow.' },
  { id: 'valuation', label: 'Valuation Studio', icon: '⌂', title: 'Valuation Studio', blurb: 'Value one property: estimate, confidence range, main factors, comparables and lending route.' },
  { id: 'batch', label: 'Batch Valuation', icon: '▤', title: 'Batch Valuation', blurb: 'Value a whole portfolio or loan book in seconds, with no manual steps.' },
  { id: 'reviews', label: 'Review Queue', icon: '✓', title: 'Lender Review Queue', blurb: 'Review routed cases, record decisions, and track how many physical visits are avoided.' },
  { id: 'model', label: 'Model & Accuracy', icon: '◈', title: 'Model & Accuracy', blurb: 'How accurate the model is, how that is measured, and how it compares to existing methods.' },
  { id: 'data', label: 'Data Sources', icon: '⛁', title: 'Data Sources & Pipeline', blurb: 'Structured, unstructured and alternative data: how it is collected, cleaned and merged.' },
  { id: 'properties', label: 'Property Explorer', icon: '▦', title: 'Property Explorer', blurb: 'Browse the property dataset behind the model.' },
]
