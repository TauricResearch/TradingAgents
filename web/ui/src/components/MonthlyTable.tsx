import type { MonthRow } from '../api'
import { fmtPct, fmtSigned, fmtUsdt } from '../format'
import { DataTable, type Column } from './DataTable'
import { Num } from './Num'

// Four columns so the table fits the overview's side column; the opening equity is the
// previous month's closing one, so it is only in the hover text.
const columns: Column<MonthRow>[] = [
  {
    key: 'month',
    header: '月份',
    render: (m) => (
      <span className="num" title={`期初 ${fmtUsdt(m.open)} · ${m.days} 天`}>
        {m.month}
        <span className="ml-1 text-[11px] text-muted">{m.partial ? '进行中' : `${m.days} 天`}</span>
      </span>
    ),
  },
  { key: 'pnl', header: '盈亏', align: 'right', render: (m) => <Num value={m.pnl} fmt={fmtSigned} /> },
  { key: 'pct', header: '收益率', align: 'right', render: (m) => <Num value={m.pct} fmt={fmtPct} /> },
  { key: 'close', header: '期末', align: 'right', render: (m) => fmtUsdt(m.close) },
]

/** The validation period month by month, newest first. */
export function MonthlyTable({ months }: { months: MonthRow[] }) {
  return <DataTable columns={columns} rows={months} rowKey={(m) => m.month} empty="验证期还没有完整的一天" />
}
