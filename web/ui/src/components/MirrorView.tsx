import type { Mirror, MirrorPoint, MirrorPosition, MirrorSide, MirrorTrade } from '../api'
import { coinLabel, fmtDay, fmtNum, fmtPct, fmtQty, fmtSigned, fmtTime } from '../format'
import { ACCOUNT_LABEL } from '../llmSettings'
import { DataTable, type Column } from './DataTable'
import { Num, Side } from './Num'
import { Time } from './Time'

/** The intraday account trades on paper, the other two on OKX. */
const sideLabel = (id: string) => (id === 'intraday' ? '日内模拟' : (ACCOUNT_LABEL[id] ?? id))

/** A label within Chinese text, spaced only when Latin: “比 Demo 的”, “比日内模拟的”. */
const inline = (label: string) => (/[A-Za-z]/.test(label) ? ` ${label} ` : label)

/** A label and the word after it: “Demo 成交”, “日内模拟成交”. */
const joined = (label: string, word: string) => `${inline(label)}${word}`.trimStart()

function SideCell({ side }: { side: MirrorSide | null }) {
  if (!side) return <span className="text-muted">空仓</span>
  return (
    <span className="num">
      <Side qty={side.qty} /> {fmtQty(side.qty)} @ {fmtNum(side.entry)}
      <span className="ml-1 text-[11px] text-muted">止损 {side.stop === null ? '待挂' : fmtNum(side.stop)}</span>
    </span>
  )
}

function positionColumns(own: string, other: string): Column<MirrorPosition>[] {
  return [
    { key: 'coin', header: '币', render: (p) => coinLabel(p.coin) },
    { key: 'other', header: other, render: (p) => <SideCell side={p.other} /> },
    { key: 'own', header: own, render: (p) => <SideCell side={p.own} /> },
    {
      key: 'same_side',
      header: '方向',
      render: (p) => (p.same_side ? <span className="text-muted">一致</span> : <span className="text-down">不一致</span>),
    },
  ]
}

function fillText(f: MirrorTrade['own'] | null) {
  if (!f) return <span className="text-muted">无成交</span>
  return (
    <span className="num" title={`币数 ${fmtQty(f.qty)} · 手续费 ${fmtNum(f.fee)} · ${fmtTime(f.ts)}`}>
      <Num value={f.qty * f.price} fmt={fmtSigned} /> @ {fmtNum(f.price)}
    </span>
  )
}

function tradeColumns(own: string, other: string): Column<MirrorTrade>[] {
  return [
    { key: 'hour', header: '小时', render: (t) => <Time ts={t.hour} /> },
    { key: 'coin', header: '币', render: (t) => coinLabel(t.coin ?? t.inst) },
    { key: 'other', header: joined(other, '成交（USDT）'), render: (t) => fillText(t.other) },
    { key: 'own', header: joined(own, '成交（USDT）'), render: (t) => fillText(t.own) },
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
}

function equityColumns(own: string, other: string): Column<MirrorPoint>[] {
  return [
    { key: 'ts', header: '零点（UTC）', render: (p) => <span className="num">{fmtDay(p.ts)}</span> },
    { key: 'other', header: joined(other, '累计'), align: 'right', render: (p) => <Num value={p.other} fmt={fmtPct} /> },
    { key: 'own', header: joined(own, '累计'), align: 'right', render: (p) => <Num value={p.own} fmt={fmtPct} /> },
    {
      key: 'gap',
      header: '差',
      align: 'right',
      render: (p) => (p.own === null || p.other === null ? '—' : <Num value={p.own - p.other} fmt={fmtPct} />),
    },
  ]
}

/** An exchange account beside the account it is compared with: positions, the trades hour by hour with their slippage, both curves. */
export function MirrorView({ mirror, account }: { mirror: Mirror; account: string }) {
  const s = mirror.summary
  const own = sideLabel(account)
  const other = sideLabel(mirror.against)
  return (
    <div className="flex flex-col gap-4 p-3">
      <div className="num flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
        <span>
          {joined(own, '成交')} {s.trades} 笔，其中 {s.matched} 笔对上了{inline(other)}同一小时的成交
        </span>
        <span>
          平均滑点 {s.avg_slippage_bps === null ? '—' : `${fmtSigned(s.avg_slippage_bps, 1)} bp`}
        </span>
        <span>
          自首次执行：{other} <Num value={s.other_return} fmt={fmtPct} />，{own} <Num value={s.own_return} fmt={fmtPct} />
        </span>
      </div>
      <section>
        <h3 className="mb-1 text-[12px] text-muted">当前持仓</h3>
        <DataTable columns={positionColumns(own, other)} rows={mirror.positions} rowKey={(p) => p.inst} />
      </section>
      <section>
        <h3 className="mb-1 text-[12px] text-muted">
          逐小时成交对照（滑点为正表示{inline(own)}比{inline(other)}的成交价吃亏）
        </h3>
        <DataTable
          columns={tradeColumns(own, other)}
          rows={mirror.trades}
          rowKey={(t, i) => `${t.hour}-${t.inst}-${i}`}
          empty={`${own} 还没有成交`}
        />
      </section>
      <section>
        <h3 className="mb-1 text-[12px] text-muted">每日零点累计收益（两账户都有快照的日子）</h3>
        <DataTable
          columns={equityColumns(own, other)}
          rows={[...mirror.equity].reverse()}
          rowKey={(p) => p.ts}
          empty="还没有共同的零点快照"
        />
      </section>
    </div>
  )
}
