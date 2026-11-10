import { fmtBeijing, fmtTime, fmtTimeFull } from '../format'

/** A UTC time like "11-07 00:15 UTC"; the hover has the full timestamp with the Beijing
 * clock, and `beijing` also writes the Beijing clock after it, muted. */
export function Time({ ts, beijing = false }: { ts: string; beijing?: boolean }) {
  return (
    <span className="num" title={fmtTimeFull(ts)}>
      {fmtTime(ts)}
      {beijing && <span className="text-muted"> · {fmtBeijing(ts)}</span>}
    </span>
  )
}
