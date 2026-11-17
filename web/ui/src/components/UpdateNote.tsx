import type { ResearchUpdate } from '../api'
import { DASH, fmtBeijing, fmtTimeFull, fmtUtcClock } from '../format'

/** "更新：Buy · 11-14 15:12 北京 · 07:12 UTC": the rating a rerun left and when, with the one
 * it replaced when that differs ("更新：Hold → Buy · …"). Below `lg` the UTC clock is left
 * out; `compact` writes "已更新" alone. The hover has the change and the time in full. */
export function UpdateNote({
  update,
  compact = false,
  className = '',
}: {
  update: ResearchUpdate
  compact?: boolean
  className?: string
}) {
  const rating = update.from === update.to ? update.to : `${update.from ?? DASH} → ${update.to}`
  const utc = fmtUtcClock(update.at)
  return (
    <span
      className={`num min-w-0 truncate text-[11px] text-accent ${className}`}
      title={`研判已更新：${update.from ?? DASH} → ${update.to}（${fmtTimeFull(update.at)}）`}
    >
      {compact ? (
        '已更新'
      ) : (
        <>
          更新：{rating} · {fmtBeijing(update.at)}
          {utc && <span className="hidden lg:inline"> · {utc}</span>}
        </>
      )}
    </span>
  )
}
