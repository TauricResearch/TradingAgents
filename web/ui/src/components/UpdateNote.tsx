import type { ResearchUpdate } from '../api'
import { DASH, fmtTime, fmtTimeFull } from '../format'

/** "研判已更新：Hold → Buy · 11-14 15:12 北京 · 07:12 UTC"; `compact` writes "已更新" alone,
 * the hover has the rest. */
export function UpdateNote({ update, compact = false }: { update: ResearchUpdate; compact?: boolean }) {
  const change = `研判已更新：${update.from ?? DASH} → ${update.to}`
  return (
    <span className="num min-w-0 truncate text-[11px] text-accent" title={`${change}（${fmtTimeFull(update.at)}）`}>
      {compact ? '已更新' : `${change} · ${fmtTime(update.at)}`}
    </span>
  )
}
