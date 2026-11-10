import { fmtTime, fmtTimeFull } from '../format'

/** A UTC time like "11-07 00:15 UTC"; the hover has the full timestamp with the Beijing clock. */
export function Time({ ts }: { ts: string }) {
  return (
    <span className="num" title={fmtTimeFull(ts)}>
      {fmtTime(ts)}
    </span>
  )
}
