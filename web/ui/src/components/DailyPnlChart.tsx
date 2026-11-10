import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from 'recharts'
import type { DailyRow } from '../api'
import { CHART_DAYS, daySpan } from '../daily'
import { fmtDay, fmtPct, fmtSigned, fmtUsdt } from '../format'

function ChartTooltip({ active, payload }: TooltipContentProps) {
  const row = payload?.[0]?.payload as DailyRow | undefined
  if (!active || !row) return null
  const rows: [string, string][] = [
    ['盈亏', `${fmtSigned(row.pnl)} (${fmtPct(row.pct)})`],
    ['期初 → 期末', `${fmtUsdt(row.open)} → ${fmtUsdt(row.close)}`],
    ['成交 / 资金费', `${row.fills} 笔 / ${fmtSigned(row.funding)}`],
  ]
  return (
    <div className="rounded-sm border border-border bg-panel px-2 py-1.5 text-[11px] shadow-none">
      <div className="num mb-1 text-muted">{daySpan(row)}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-center justify-between gap-4">
          <span className="text-muted">{k}</span>
          <span className="num text-fg">{v}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * The last CHART_DAYS days' PnL as bars, oldest left, green up and red down; the day
 * in progress is drawn lighter. Nothing to draw before the first midnight snapshot.
 */
export function DailyPnlChart({ days }: { days: DailyRow[] }) {
  if (days.length === 0) {
    return <div className="flex h-[180px] items-center justify-center text-muted">验证期还没有完整的一天</div>
  }
  const data = days.slice(0, CHART_DAYS).reverse()
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="start_ts"
          tickFormatter={(v: string) => fmtDay(v)}
          tick={{ fill: 'var(--color-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
          minTickGap={16}
        />
        <YAxis
          width={64}
          tickFormatter={(v: number) => fmtSigned(v, 0)}
          tick={{ fill: 'var(--color-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
        />
        <ReferenceLine y={0} stroke="var(--color-muted)" />
        <Tooltip content={ChartTooltip} cursor={{ fill: 'var(--color-panel-2)' }} isAnimationActive={false} />
        <Bar dataKey="pnl" isAnimationActive={false} maxBarSize={28}>
          {data.map((row) => (
            <Cell
              key={row.start_ts}
              fill={row.pnl !== null && row.pnl < 0 ? 'var(--color-down)' : 'var(--color-up)'}
              fillOpacity={row.partial ? 0.45 : 0.9}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
