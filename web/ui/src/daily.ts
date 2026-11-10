import type { DailyRow } from './api'
import { fmtDay } from './format'

/** How many of the newest days the overview's bar chart shows. */
export const CHART_DAYS = 30

/** "11-10 · UTC 全天 · 北京 08:00–次日 08:00", the span a day row covers. */
export function daySpan(row: DailyRow): string {
  return `${fmtDay(row.start_ts)} · UTC 全天 · 北京 08:00–次日 08:00${row.partial ? ' · 进行中' : ''}`
}
