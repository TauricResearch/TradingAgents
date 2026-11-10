import type { Mirror, MirrorPoint, MirrorPosition, MirrorSide, MirrorTrade } from '../api'
import { coinLabel, fmtDay, fmtNum, fmtPct, fmtQty, fmtSigned, fmtTime } from '../format'
import { DataTable, type Column } from './DataTable'
import { Num, Side } from './Num'

function SideCell({ side }: { side: MirrorSide | null }) {
  if (!side) return <span className="text-muted">空仓</span>
  return (
    <span className="num">
      <Side qty={side.qty} /> {fmtQty(side.qty)} @ {fmtNum(side.entry)}
      <span className="ml-1 text-[11px] text-muted">止损 {side.stop === null ? '待挂' : fmtNum(side.stop)}</span>
    </span>
  )
}

const positionColumns: Column<MirrorPosition>[] = [
  { key: 'coin', header: '币', render: (p) => coinLabel(p.coin) },
  { key: 'intraday', header: '日内模拟', render: (p) => <SideCell side={p.intraday} /> },
  { key: 'demo', header: 'Demo（交易所）', render: (p) => <SideCell side={p.demo} /> },
  {
    key: 'same_side',
    header: '方向',
    render: (p) => (p.same_side ? <span className="text-muted">一致</span> : <span className="text-down">不一致</span>),
  },
]

function fillText(f: MirrorTrade['demo'] | null) {
  if (!f) return <span className="text-muted">无成交</span>
  return (
    <span className="num" title={`手续费 ${fmtNum(f.fee)} · ${fmtTime(f.ts)}`}>
      <Num value={f.qty} fmt={fmtQty} /> @ {fmtNum(f.price)}
    </span>
  )
}

const tradeColumns: Column<MirrorTrade>[] = [
  { key: 'hour', header: '小时（UTC）', render: (t) => <span className="num">{fmtTime(t.hour)}</span> },
  { key: 'coin', header: '币', render: (t) => coinLabel(t.coin ?? t.inst) },
  { key: 'intraday', header: '日内模拟成交', render: (t) => fillText(t.intraday) },
  { key: 'demo', header: 'Demo 成交', render: (t) => fillText(t.demo) },
  {
    key: 'slippage',
    header: '滑点 bp',
    align: 'right',
    render: (t) =>
      t.slippage_bps === null ? (
        <span className="text-muted">—</span>
      ) : (
        <Num value={t.slippage_bps} fmt={(x) => fmtSigned(x, 1)} by={t.slippage_bps === 0 ? 0 : -t.slippage_bps} />
      ),
  },
]

const equityColumns: Column<MirrorPoint>[] = [
  { key: 'ts', header: '零点（UTC）', render: (p) => <span className="num">{fmtDay(p.ts)}</span> },
  { key: 'intraday', header: '日内模拟累计', align: 'right', render: (p) => <Num value={p.intraday} fmt={fmtPct} /> },
  { key: 'demo', header: 'Demo 累计', align: 'right', render: (p) => <Num value={p.demo} fmt={fmtPct} /> },
  {
    key: 'gap',
    header: '差',
    align: 'right',
    render: (p) => (p.demo === null || p.intraday === null ? '—' : <Num value={p.demo - p.intraday} fmt={fmtPct} />),
  },
]

/** The demo account beside the intraday account it follows: positions, the trades hour by hour with their slippage, both curves. */
export function MirrorView({ mirror }: { mirror: Mirror }) {
  const s = mirror.summary
  return (
    <div className="flex flex-col gap-4 p-3">
      <div className="num flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
        <span>
          跟随成交 {s.trades} 笔，对上日内成交 {s.matched} 笔
        </span>
        <span>
          平均滑点 {s.avg_slippage_bps === null ? '—' : `${fmtSigned(s.avg_slippage_bps, 1)} bp`}
        </span>
        <span>
          自首次执行：日内 <Num value={s.intraday_return} fmt={fmtPct} />，Demo <Num value={s.demo_return} fmt={fmtPct} />
        </span>
      </div>
      <section>
        <h3 className="mb-1 text-[12px] text-muted">当前持仓</h3>
        <DataTable columns={positionColumns} rows={mirror.positions} rowKey={(p) => p.inst} />
      </section>
      <section>
        <h3 className="mb-1 text-[12px] text-muted">逐小时成交对照（滑点为正表示 Demo 比模拟成交价吃亏）</h3>
        <DataTable
          columns={tradeColumns}
          rows={mirror.trades}
          rowKey={(t, i) => `${t.hour}-${t.inst}-${i}`}
          empty="Demo 还没有跟随过成交"
        />
      </section>
      <section>
        <h3 className="mb-1 text-[12px] text-muted">每日零点累计收益（两账户都有快照的日子）</h3>
        <DataTable columns={equityColumns} rows={[...mirror.equity].reverse()} rowKey={(p) => p.ts} empty="还没有共同的零点快照" />
      </section>
    </div>
  )
}
