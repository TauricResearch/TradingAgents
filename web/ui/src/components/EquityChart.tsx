import { useMemo } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'
import type { EquityPoint } from '../api'
import { fmtDay, fmtTimeFull, fmtUsdt } from '../format'

const SERIES = [
  { key: 'strategy_net', name: '策略（扣 LLM 费用）', color: 'var(--color-line-strategy)' },
  { key: 'equal_weight', name: '三币等权持有', color: 'var(--color-line-equal)' },
  { key: 'btc', name: 'BTC 持有', color: 'var(--color-line-btc)' },
] as const

const NAMES: Record<string, string> = Object.fromEntries(SERIES.map((s) => [s.key, s.name]))

function ChartTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-sm border border-border bg-panel px-2 py-1.5 text-[11px] shadow-none">
      <div className="num mb-1 text-muted">{typeof label === 'string' ? fmtTimeFull(label) : label}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-2" style={{ background: p.color }} />
            {NAMES[String(p.dataKey)] ?? String(p.name)}
          </span>
          <span className="num text-fg">{typeof p.value === 'number' ? fmtUsdt(p.value) : '—'}</span>
        </div>
      ))}
    </div>
  )
}

/** Y ticks on a round step with a little headroom around the plotted values. */
function yTicks(points: EquityPoint[]): number[] {
  let lo = Number.POSITIVE_INFINITY
  let hi = Number.NEGATIVE_INFINITY
  for (const p of points) {
    for (const s of SERIES) {
      const v = p[s.key]
      if (typeof v === 'number') {
        lo = Math.min(lo, v)
        hi = Math.max(hi, v)
      }
    }
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1]
  const span = Math.max(hi - lo, Math.abs(hi) * 0.004, 1)
  const raw = span / 6
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10
  const first = Math.floor((lo - span * 0.05) / step) * step
  const last = Math.ceil((hi + span * 0.05) / step) * step
  const ticks: number[] = []
  for (let v = first; v <= last + step / 2; v += step) ticks.push(Math.round(v * 100) / 100)
  return ticks
}

export function EquityChart({ points }: { points: EquityPoint[] }) {
  const ticks = useMemo(() => yTicks(points), [points])

  if (points.length < 2) {
    return (
      <div className="flex h-[280px] items-center justify-center text-muted">
        验证期刚开始，曲线从第二天起显示
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="ts"
          tickFormatter={(v: string) => fmtDay(v)}
          tick={{ fill: 'var(--color-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
          minTickGap={24}
        />
        <YAxis
          domain={[ticks[0], ticks[ticks.length - 1]]}
          ticks={ticks}
          width={64}
          tickFormatter={(v: number) => fmtUsdt(v, 0)}
          tick={{ fill: 'var(--color-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          content={ChartTooltip}
          cursor={{ stroke: 'var(--color-muted)', strokeDasharray: '2 2' }}
          isAnimationActive={false}
          itemSorter={(item) => SERIES.findIndex((s) => s.key === item.dataKey)}
        />
        <Legend
          verticalAlign="top"
          align="right"
          height={24}
          iconType="plainline"
          itemSorter={null}
          wrapperStyle={{ fontSize: 11, color: 'var(--color-muted)' }}
        />
        {SERIES.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={s.color}
            strokeWidth={s.key === 'strategy_net' ? 2 : 1.25}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
