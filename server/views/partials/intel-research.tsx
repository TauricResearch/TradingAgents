/** @jsxImportSource hono/jsx */

import type { DbWatchlistItem } from "../../lib/portfolio-intel-data.ts"
import { esc } from "../../lib/markup.ts"

export function ResearchQueue({ items }: { items: DbWatchlistItem[] }) {
  if (!items || items.length === 0) {
    return <div class="muted">No approved research items</div>
  }
  return (
    <div style="margin:1.5rem 0">
      <h4>Research Queue (Approved)</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Exchange</th>
            <th>Priority</th>
            <th>Signal</th>
            <th>Added</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr>
              <td class="ticker">{esc(i.ticker)}</td>
              <td>{esc(i.exchange)}</td>
              <td>
                <span class={i.priority === "high" ? "negative" : i.priority === "medium" ? "" : "muted"}>
                  {esc(i.priority)}
                </span>
              </td>
              <td>{esc(i.last_signal) || "—"}</td>
              <td>{esc(i.added_date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
