import { Link } from 'react-router-dom'
import type { ResearchSummary } from '../api'
import { coinLabel, fmtInt, fmtUsd } from '../format'
import { researchHref, researchKey } from '../routes'
import { RatingChip } from './RatingChip'
import { Empty } from './Status'
import { UpdateNote } from './UpdateNote'

interface Props {
  items: ResearchSummary[]
  /** `${coin}/${trade_date}` of the open record, highlighted. */
  activeKey?: string
  /** Sidebar mode: coin and rating only. */
  compact?: boolean
}

/** Research records grouped by trade date, newest first as the API returns them. */
export function ResearchList({ items, activeKey, compact = false }: Props) {
  if (items.length === 0) return <Empty label="还没有研判记录" />

  const groups: { date: string; rows: ResearchSummary[] }[] = []
  for (const it of items) {
    const last = groups[groups.length - 1]
    if (last && last.date === it.trade_date) last.rows.push(it)
    else groups.push({ date: it.trade_date, rows: [it] })
  }

  return (
    <div className="flex flex-col">
      {groups.map((g) => (
        <div key={g.date}>
          <div className="num sticky top-0 border-b border-border bg-panel-2 px-3 py-1 text-[11px] text-muted">
            研判日 {g.date}
            <span className="ml-2">{g.rows.length} 币</span>
          </div>
          <ul>
            {g.rows.map((r) => {
              const key = researchKey(r.coin, r.trade_date)
              const on = key === activeKey
              return (
                <li key={key} className="border-b border-border/60 last:border-b-0">
                  <Link
                    to={researchHref(r.coin, r.trade_date)}
                    aria-current={on ? 'page' : undefined}
                    className={`flex items-center gap-3 px-3 py-1.5 hover:bg-panel-2/60 ${
                      on ? 'bg-panel-2 shadow-[inset_2px_0_0_var(--color-accent)]' : ''
                    }`}
                  >
                    <span className="num w-10 font-medium" title={r.coin}>
                      {coinLabel(r.coin)}
                    </span>
                    <RatingChip rating={r.rating} />
                    {r.update && <UpdateNote update={r.update} compact={compact} />}
                    {!compact && (
                      <span className="num ml-auto flex gap-4 text-[11px] text-muted">
                        <span className="hidden sm:inline" title="tokens 进 / 出">
                          {fmtInt(r.tokens_in)} / {fmtInt(r.tokens_out)}
                        </span>
                        <span className="w-14 text-right text-fg">{fmtUsd(r.cost_usd)}</span>
                      </span>
                    )}
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}
