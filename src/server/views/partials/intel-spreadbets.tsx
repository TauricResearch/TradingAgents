/**
 * Spread bet positions panel — shows open spread bet positions with P&L and notional value.
 */

/** @jsxImportSource hono/jsx */

import type { SpreadBetWithPnl } from "../../lib/portfolio-intel-data.ts"
import { esc, fmtCommas } from "../../lib/markup.ts"

export function SpreadBetTable({ bets }: { bets: SpreadBetWithPnl[] }) {
  if (!bets || bets.length === 0) {
    return <div class="muted">No open spread bets</div>
  }
  return (
    <div style="margin:1.5rem 0">
      <h4>Spread Bet Positions</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Direction</th>
            <th>Stake/£pt</th>
            <th>Entry</th>
            <th>Current</th>
            <th>P&L</th>
            <th>P&L %</th>
            <th>Notional</th>
          </tr>
        </thead>
        <tbody>
          {bets.map((b) => {
            const pnlCls = b.pnl_gbp != null ? (b.pnl_gbp >= 0 ? "positive" : "negative") : ""
            return (
              <tr>
                <td class="ticker">{esc(b.ticker)}</td>
                <td>
                  <span class={b.direction === "long" ? "positive" : "negative"}>
                    {b.direction.toUpperCase()}
                  </span>
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {fmtCommas(b.stake_per_point)}
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  £{fmtCommas(b.entry_price)}
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {b.current_price_gbp != null ? `£${fmtCommas(b.current_price_gbp)}` : "—"}
                </td>
                <td class={pnlCls} style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {b.pnl_gbp != null
                    ? `${b.pnl_gbp >= 0 ? "+" : "-"}£${fmtCommas(Math.abs(b.pnl_gbp))}`
                    : "—"}
                </td>
                <td class={pnlCls} style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {b.pnl_pct != null ? (b.pnl_pct >= 0 ? "+" : "") + `${fmtCommas(b.pnl_pct)}%` : "—"}
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  £{fmtCommas(b.notional_gbp)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
