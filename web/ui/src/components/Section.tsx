import type { ReactNode } from 'react'

interface Props {
  index: number
  title: string
  /** Source field in the research record, shown in monospace. */
  field: string
  open: boolean
  onToggle: () => void
  /** Short summary shown in the header when collapsed, e.g. a length. */
  meta?: ReactNode
  children: ReactNode
}

/** Collapsible step of the research pipeline. */
export function Section({ index, title, field, open, onToggle, meta, children }: Props) {
  return (
    <section className="rounded-sm border border-border bg-panel">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-panel-2/60"
      >
        <span className={`num w-4 shrink-0 text-[11px] ${open ? 'text-accent' : 'text-muted'}`}>
          {open ? '▾' : '▸'}
        </span>
        <span className="num text-[11px] text-muted">{String(index).padStart(2, '0')}</span>
        <span className="font-medium">{title}</span>
        <span className="num hidden text-[11px] text-muted sm:inline">{field}</span>
        {meta !== undefined && <span className="ml-auto text-[11px] text-muted">{meta}</span>}
      </button>
      {open && <div className="border-t border-border px-3 py-2">{children}</div>}
    </section>
  )
}
