import { fmtBeijing, fmtTimeFull, fmtUtcClock } from '../format'

/** A record's time, "11-07 08:15 北京" dated always, then the UTC clock muted
 * (" · 00:15 UTC"); the hover has both in full. */
export function Time({ ts }: { ts: string }) {
  const utc = fmtUtcClock(ts)
  return (
    <span className="num" title={fmtTimeFull(ts)}>
      {fmtBeijing(ts)}
      {utc && <span className="text-muted"> · {utc}</span>}
    </span>
  )
}
