import type { ReactNode } from 'react'

interface Props {
  title?: ReactNode
  /** Right side of the header: notes, counts, actions. */
  aside?: ReactNode
  className?: string
  /** Drop the body padding, for tables that fill the panel. */
  flush?: boolean
  children: ReactNode
}

export function Panel({ title, aside, className = '', flush = false, children }: Props) {
  return (
    <section className={`flex min-w-0 flex-col rounded-sm border border-border bg-panel ${className}`}>
      {(title !== undefined || aside !== undefined) && (
        <header className="flex min-h-8 items-center justify-between gap-3 border-b border-border px-3 py-1.5">
          <h2 className="truncate text-[12px] font-medium tracking-wide text-muted uppercase">{title}</h2>
          {aside !== undefined && <div className="shrink-0 text-[11px] text-muted">{aside}</div>}
        </header>
      )}
      <div className={`min-w-0 flex-1 ${flush ? '' : 'p-3'}`}>{children}</div>
    </section>
  )
}
