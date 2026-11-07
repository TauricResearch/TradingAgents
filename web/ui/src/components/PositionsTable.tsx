import type { Position } from '../api'
import { fmtPct, fmtQty, fmtSigned, fmtUsdt } from '../format'
import { DataTable, type Column } from './DataTable'
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
  { key: 'stop', header: '止损价', help: 'stop', align: 'right', render: (p) => fmtUsdt(p.stop) },
  {
    key: 'stop_distance',
    header: '距止损',
    help: 'stop_distance',
    align: 'right',
    render: (p) => <span className="text-muted">{fmtPct(p.stop_distance)}</span>,
  },
]

export function PositionsTable({ positions }: { positions: Position[] }) {
  return <DataTable columns={columns} rows={positions} rowKey={(p) => p.inst} empty="无持仓" />
}
