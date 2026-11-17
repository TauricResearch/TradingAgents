import { Link } from 'react-router-dom'
import type { ResearchSummary } from '../api'
import { coinLabel, fmtBeijing, fmtInt, fmtTimeFull, fmtUsd, fmtUtcClock } from '../format'
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

/** Research records grouped by trade date, newest first as the API returns them, each on
 * one line with when its rating was published. A row with an update note gives up, as the
 * screen narrows, the tokens and the UTC clocks (below `lg`), then the publish time (below
 * `md`), so that the note is not cut; on a phone the note takes a second line. */
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
              const wide = r.update ? 'hidden lg:inline' : 'hidden sm:inline'
              return (
                <li key={key} className="border-b border-border/60 last:border-b-0">
                  <Link
                    to={researchHref(r.coin, r.trade_date)}
                    aria-current={on ? 'page' : undefined}
                    className={`flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-1.5 hover:bg-panel-2/60 sm:flex-nowrap ${
                      on ? 'bg-panel-2 shadow-[inset_2px_0_0_var(--color-accent)]' : ''
                    }`}
                  >
                    <span className="num w-10 font-medium" title={r.coin}>
                      {coinLabel(r.coin)}
                    </span>
                    <RatingChip rating={r.rating} />
                    {!compact && r.published_at && (
                      <span
                        className={`num shrink-0 text-[11px] text-muted ${r.update ? 'hidden md:inline' : ''}`}
                        title={`发布时间：${fmtTimeFull(r.published_at)}`}
                      >
                        发布 {fmtBeijing(r.published_at)}
                        <span className={wide}> · {fmtUtcClock(r.published_at)}</span>
                      </span>
                    )}
                    {r.update && (
                      <UpdateNote
                        update={r.update}
                        compact={compact}
                        className={compact ? '' : 'max-[540px]:order-last max-[540px]:basis-full'}
                      />
                    )}
                    {!compact && (
                      <span className="num ml-auto flex shrink-0 gap-4 whitespace-nowrap text-[11px] text-muted">
                        <span className={wide} title="tokens 进 / 出">
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
