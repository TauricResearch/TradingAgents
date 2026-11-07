import type { ReactNode } from 'react'
import type { HelpKey } from '../content/help'
import { Help } from './Help'

const toneClass = { up: 'text-up', down: 'text-down', flat: 'text-fg' } as const

interface KpiProps {
  label: string
  value: string
  /** Small line under the value: a sub-figure or "样本不足". */
  note?: ReactNode
  tone?: keyof typeof toneClass
  /** `?` mark after the label. */
  help?: HelpKey
}

export function Kpi({ label, value, note, tone = 'flat', help }: KpiProps) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 bg-panel px-3 py-2 outline outline-border">
      <div className="flex items-center gap-1 text-[11px] tracking-wide text-muted uppercase">
        <span className="truncate">{label}</span>
        {help && <Help k={help} />}
      </div>
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
