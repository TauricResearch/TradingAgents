import type { ReactNode } from 'react'
import type { HelpKey } from '../content/help'
import { Help } from './Help'
import { Empty } from './Status'

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  /** Numbers go right-aligned in the monospace face. */
  align?: 'left' | 'right'
  /** Extra classes for both header and body cells, e.g. a width. */
  className?: string
  /** `?` mark after the header text. */
  help?: HelpKey
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T, index: number) => string
  empty?: string
  /** Keep the header visible while the body scrolls inside a bounded panel. */
  stickyHeader?: boolean
  /** A totals row under the body: cells by column key, the other columns blank. */
  footer?: Partial<Record<string, ReactNode>>
}

/** Dense table; scrolls horizontally on narrow screens. */
export function DataTable<T>({ columns, rows, rowKey, empty = '暂无记录', stickyHeader = false, footer }: Props<T>) {
  if (rows.length === 0) return <Empty label={empty} />
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full border-collapse whitespace-nowrap text-[12px]">
        <thead className={stickyHeader ? 'sticky top-0 z-10' : ''}>
          <tr className="bg-panel-2 text-[11px] font-medium text-muted">
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={`border-b border-border px-2 py-1 font-medium ${
                  c.align === 'right' ? 'text-right' : 'text-left'
                } ${c.className ?? ''}`}
              >
                {c.header}
                {c.help && (
                  <Help k={c.help} size="xs" align={c.align === 'right' ? 'end' : 'start'} className="ml-1" />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-b border-border/60 last:border-b-0 hover:bg-panel-2/60">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`px-2 py-[3px] align-top ${
                    c.align === 'right' ? 'num text-right' : 'text-left'
                  } ${c.className ?? ''}`}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && (
          <tfoot>
            <tr className="border-t border-border bg-panel-2/40 font-medium">
              {columns.map((c) => (
                <td key={c.key} className={`px-2 py-[3px] ${c.align === 'right' ? 'num text-right' : 'text-left'} ${c.className ?? ''}`}>
                  {footer[c.key]}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}
