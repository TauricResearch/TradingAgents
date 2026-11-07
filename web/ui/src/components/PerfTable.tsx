import type { Perf, Performance } from '../api'
import { fmtDrawdown, fmtNum, fmtPct } from '../format'
import { Num } from './Num'

const ROWS: { key: keyof Performance; label: string; color: string }[] = [
  { key: 'strategy', label: '策略（扣 LLM 费用）', color: 'var(--color-line-strategy)' },
  { key: 'equal_weight', label: '三币等权持有', color: 'var(--color-line-equal)' },
  { key: 'btc', label: 'BTC 持有', color: 'var(--color-line-btc)' },
]

const HEAD = ['累计', '年化', 'Sharpe', '最大回撤', '年化/回撤']

function cells(p: Perf | null) {
  if (!p) {
    return (
      <td colSpan={HEAD.length} className="px-2 py-1 text-right text-muted">
        样本不足
      </td>
    )
  }
  return (
    <>
      <td className="num px-2 py-1 text-right">
        <Num value={p.cumulative} fmt={fmtPct} />
      </td>
      <td className="num px-2 py-1 text-right">
        <Num value={p.annualized} fmt={fmtPct} />
      </td>
      <td className="num px-2 py-1 text-right">{fmtNum(p.sharpe)}</td>
      <td className="num px-2 py-1 text-right text-down">{fmtDrawdown(p.max_drawdown)}</td>
      <td className="num px-2 py-1 text-right">{fmtNum(p.calmar)}</td>
    </>
  )
}

/** Strategy performance against the baselines, same figures as the KPI strip. */
export function PerfTable({ performance }: { performance: Performance }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse whitespace-nowrap text-[12px]">
        <thead>
          <tr className="text-[11px] text-muted">
            <th className="px-2 py-1 text-left font-medium">策略表现</th>
            {HEAD.map((h) => (
              <th key={h} className="px-2 py-1 text-right font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.key} className="border-t border-border/60">
              <td className="px-2 py-1">
                <span className="mr-2 inline-block h-0.5 w-3 align-middle" style={{ background: r.color }} />
                {r.label}
              </td>
              {cells(performance[r.key])}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
