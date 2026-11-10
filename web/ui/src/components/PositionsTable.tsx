import type { Position, Totals } from '../api'
import { coinLabel, fmtNum, fmtPct, fmtQty, fmtSigned, fmtUsdt } from '../format'
import { DataTable, type Column } from './DataTable'
import { Help } from './Help'
import { Num, Side } from './Num'

const columns: Column<Position>[] = [
  { key: 'inst', header: '合约', render: (p) => <span className="num">{p.inst}</span> },
  { key: 'side', header: '方向', help: 'side', render: (p) => <Side qty={p.qty} /> },
  { key: 'qty', header: '数量', help: 'qty', align: 'right', render: (p) => <Num value={p.qty} fmt={fmtQty} /> },
  { key: 'entry', header: '开仓均价', help: 'entry', align: 'right', render: (p) => fmtUsdt(p.entry) },
  { key: 'price', header: '现价', help: 'price', align: 'right', render: (p) => fmtUsdt(p.price) },
  { key: 'notional', header: '名义', help: 'notional', align: 'right', render: (p) => fmtUsdt(p.notional) },
  {
    key: 'unrealized',
    header: '浮动盈亏',
    help: 'unrealized',
    align: 'right',
    render: (p) => <Num value={p.unrealized} fmt={fmtSigned} />,
  },
  {
    key: 'unrealized_pct',
    header: '浮盈%',
    help: 'unrealized_pct',
    align: 'right',
    render: (p) => <Num value={p.unrealized_pct} fmt={fmtPct} />,
  },
  { key: 'stop', header: '止损价', help: 'stop', align: 'right', render: (p) => fmtUsdt(p.stop) },
  {
    key: 'stop_distance',
    header: '距止损',
    help: 'stop_distance',
    align: 'right',
    render: (p) => <span className="text-muted">{fmtPct(p.stop_distance)}</span>,
  },
]

/** The open positions with a totals row; `totals` is the API's, null while a quote is missing. */
export function PositionsTable({ positions, totals }: { positions: Position[]; totals: Totals }) {
  // The rows' percentage is on the value at entry, so the total is on the same base.
  const atEntry = positions.reduce((sum, p) => sum + Math.abs(p.qty) * p.entry, 0)
  const footer = {
    inst: <span className="text-muted">合计 · {positions.length} 个合约</span>,
    notional: fmtUsdt(totals.notional),
    unrealized: <Num value={totals.unrealized} fmt={fmtSigned} />,
    unrealized_pct: <Num value={totals.unrealized === null || atEntry === 0 ? null : totals.unrealized / atEntry} fmt={fmtPct} />,
  }
  return <DataTable columns={columns} rows={positions} rowKey={(p) => p.inst} empty="无持仓" footer={footer} />
}

/**
 * How the exposure splits between the contracts: one segment per position, its width
 * the share of the total notional, green long and red short. Nothing without quotes.
 */
export function ExposureBar({ positions, totals }: { positions: Position[]; totals: Totals }) {
  if (positions.length === 0 || totals.notional === null || totals.notional === 0) return null
  const total = totals.notional
  return (
    <div className="flex flex-col gap-1 border-b border-border px-3 py-2">
      <div className="flex items-center gap-1 text-[11px] text-muted">
        敞口分布
        <Help k="exposure" size="xs" />
        <span className="num ml-auto">
          名义 {fmtUsdt(total)} · 杠杆 {fmtNum(totals.leverage)}x
        </span>
      </div>
      <div className="flex h-1.5 w-full gap-px overflow-hidden rounded-sm bg-panel-2">
        {positions.map((p) => (
          <div
            key={p.inst}
            className={`h-full ${p.qty < 0 ? 'bg-down' : 'bg-up'}`}
            style={{ width: `${((p.notional ?? 0) / total) * 100}%` }}
            title={`${p.inst} ${p.qty < 0 ? '空' : '多'} ${fmtUsdt(p.notional)}`}
          />
        ))}
      </div>
      <div className="num flex flex-wrap gap-x-3 text-[11px] text-muted">
        {positions.map((p) => (
          <span key={p.inst}>
            <span className={`mr-1 inline-block h-2 w-2 rounded-xs align-[-1px] ${p.qty < 0 ? 'bg-down' : 'bg-up'}`} />
            {p.coin ? coinLabel(p.coin) : p.inst} {p.qty < 0 ? '空' : '多'} {fmtPct((p.notional ?? 0) / total).replace('+', '')}
          </span>
        ))}
      </div>
    </div>
  )
}
