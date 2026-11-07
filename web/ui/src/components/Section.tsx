import type { ReactNode } from 'react'
import type { HelpKey } from '../content/help'
import { Help } from './Help'

interface Props {
  index: number
  title: string
  /** Source field in the research record, shown in monospace. */
  field: string
  open: boolean
  onToggle: () => void
  /** Short summary shown in the header when collapsed, e.g. a length. */
  meta?: ReactNode
  /** `?` mark after the title. */
  help?: HelpKey
  children: ReactNode
}

/** Collapsible step of the research pipeline. */
export function Section({ index, title, field, open, onToggle, meta, help, children }: Props) {
  return (
    <section className="rounded-sm border border-border bg-panel">
      {/* The toggle's ::after stretches over the whole row, so the `?` can sit beside it rather than inside it. */}
      <div className="relative flex items-center gap-2 px-3 py-1.5 hover:bg-panel-2/60">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex min-w-0 items-center gap-2 text-left after:absolute after:inset-0"
        >
          <span className={`num w-4 shrink-0 text-[11px] ${open ? 'text-accent' : 'text-muted'}`}>
            {open ? '▾' : '▸'}
          </span>
          <span className="num text-[11px] text-muted">{String(index).padStart(2, '0')}</span>
          <span className="font-medium">{title}</span>
        </button>
        {help && <Help k={help} />}
        <span className="num hidden text-[11px] text-muted sm:inline">{field}</span>
        {meta !== undefined && <span className="ml-auto text-[11px] text-muted">{meta}</span>}
      </div>
      {open && <div className="border-t border-border px-3 py-2">{children}</div>}
    </section>
  )
}
