/** @jsxImportSource hono/jsx */

import type { PlatformAllocation } from "../../lib/portfolio-intel-data.ts"
import { esc, fmtCommas } from "../../lib/markup.ts"

export function PlatformTable({ platforms }: { platforms: PlatformAllocation[] }) {
  if (!platforms || platforms.length === 0) {
    return <div class="muted">No platform data</div>
  }

  return (
    <table class="data-table">
      <thead>
        <tr>
          <th>Platform</th>
          <th>Total Value</th>
          <th>Weight</th>
          <th>Cash</th>
          <th>Positions</th>
        </tr>
      </thead>
      <tbody>
        {platforms.map((p) => (
          <tr>
            <td>
              <span class="platform-tag">{esc(p.platform)}</span>
            </td>
            <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
              £{fmtCommas(p.total_value_gbp)}
            </td>
            <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
              {fmtCommas(p.weight_pct)}%
            </td>
            <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
              £{fmtCommas(p.cash_gbp)}{" "}
              <span class="muted">({fmtCommas(p.cash_pct)}%)</span>
            </td>
            <td>
              {p.positions.map((pos) => {
                const pnl = pos.pnl_pct
                const pnlCls = pnl != null ? (pnl >= 0 ? "positive" : "negative") : ""
                const pnlStr = pnl != null ? `${(pnl >= 0 ? "+" : "") + fmtCommas(pnl)}%` : ""
                return (
                  <span class="position-pill">
                    {esc(pos.ticker)}{" "}
                    <span class={pnlCls}>{pnlStr}</span>
                  </span>
                )
              })}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
