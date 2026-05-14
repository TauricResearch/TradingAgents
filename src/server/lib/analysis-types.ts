/** Analysis data layer — types and helpers extracted from routes for reuse. */

export interface DbAnalysis {
  id: number
  ticker: string
  date: string
  decision: string | null
  platform: string
  raw_state: string | null
  created_at: string
}

export interface AnalysisEvent {
  type: string
  data: Record<string, unknown>
}

export function fmtDate(d: string): string {
  if (!d) return "\u2014"
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ]
  const parts = d.split("-")
  if (parts.length !== 3) return d
  const [year, month, day] = parts as [string, string, string]
  return parseInt(day, 10) + (months[parseInt(month, 10) - 1] ?? "") + year.slice(2)
}
