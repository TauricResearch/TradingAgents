import type { ReactNode } from 'react'

const toneClass = { up: 'text-up', down: 'text-down', flat: 'text-fg' } as const

interface KpiProps {
  label: string
  value: string
  /** Small line under the value: a sub-figure or "样本不足". */
  note?: ReactNode
  tone?: keyof typeof toneClass
}

export function Kpi({ label, value, note, tone = 'flat' }: KpiProps) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 bg-panel px-3 py-2 outline outline-border">
      <div className="truncate text-[11px] tracking-wide text-muted uppercase">{label}</div>
      <div className={`num truncate text-[20px] leading-6 font-medium ${toneClass[tone]}`}>{value}</div>
      <div className="num min-h-4 truncate text-[11px] text-muted">{note}</div>
    </div>
  )
}

/** Segmented strip: cell outlines meet in the 1px gaps; an empty trailing slot stays blank. */
export function KpiStrip({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-panel p-px sm:grid-cols-4 xl:grid-cols-7">
      {children}
    </div>
  )
}
