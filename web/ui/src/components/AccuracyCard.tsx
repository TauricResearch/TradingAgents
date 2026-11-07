import type { Accuracy, RatingStats } from '../api'
import { fmtHolding, fmtInt, fmtPct } from '../format'
import { DataTable, type Column } from './DataTable'
import { Num } from './Num'
import { RatingChip } from './RatingChip'

const ORDER = ['Buy', 'Overweight', 'Hold', 'Underweight', 'Sell', 'REVIEW']

type Row = RatingStats & { rating: string }

const columns: Column<Row>[] = [
  { key: 'rating', header: '评级', render: (r) => <RatingChip rating={r.rating} /> },
  { key: 'count', header: '次数', align: 'right', render: (r) => fmtInt(r.count) },
  {
    key: 'hit_rate',
    header: '命中率',
    align: 'right',
    render: (r) => (r.hit_rate === null ? <span className="text-muted">—</span> : fmtPct(r.hit_rate)),
  },
  {
    key: 'mean_alpha',
    header: '平均 alpha',
    align: 'right',
    render: (r) => <Num value={r.mean_alpha} fmt={fmtPct} />,
  },
]

export function AccuracyCard({ accuracy }: { accuracy: Accuracy }) {
  const holding = fmtHolding(accuracy.holding)
  const rows: Row[] = Object.entries(accuracy.by_rating)
    .map(([rating, stats]) => ({ rating, ...stats }))
    .sort((a, b) => {
      const ia = ORDER.indexOf(a.rating)
      const ib = ORDER.indexOf(b.rating)
      return (ia === -1 ? ORDER.length : ia) - (ib === -1 ? ORDER.length : ib)
    })

  return (
    <div className="flex flex-col gap-2">
      <div className="num flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
        <span>
          已结算 <span className="text-fg">{fmtInt(accuracy.resolved)}</span>
        </span>
        <span className="text-muted">
          待结算 <span className="text-fg">{fmtInt(accuracy.pending)}</span>
        </span>
        <span className="text-muted">
          未评分 <span className="text-fg">{fmtInt(accuracy.unscored)}</span>
        </span>
      </div>
      {accuracy.resolved === 0 ? (
        <div className="py-3 text-center text-muted">还没有结算的评级</div>
      ) : (
        <div className="-mx-3">
          <DataTable columns={columns} rows={rows} rowKey={(r) => r.rating} empty="还没有结算的评级" />
        </div>
      )}
      <div className="text-[11px] text-muted">
        基准：{accuracy.benchmark}
        {holding ? `，持有 ${holding}` : ''}
      </div>
    </div>
  )
}
