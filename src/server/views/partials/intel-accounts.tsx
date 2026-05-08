/** @jsxImportSource hono/jsx */

import type { AccountSummary } from "../../lib/portfolio-intel-data.ts"
import { esc, fmtCommas } from "../../lib/markup.ts"

export function AccountsTable({ accounts }: { accounts: AccountSummary[] }) {
  if (!accounts || accounts.length === 0) {
    return <div class="muted">No accounts configured</div>
  }
  return (
    <div style="margin:1.5rem 0">
      <h4>Accounts</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>Account</th>
            <th>Type</th>
            <th>Cash</th>
            <th>Deployed</th>
            <th>Spread Bet</th>
            <th>Total</th>
            <th>Positions</th>
            <th>Bets</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => (
            <tr>
              <td>
                <strong>{esc(a.name || a.id)}</strong>
                {a.notes && <div class="muted" style="font-size:0.75em">{esc(a.notes)}</div>}
              </td>
              <td>
                <span class="platform-tag">{esc(a.account_type)}</span>
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                £{fmtCommas(a.balance_gbp)}
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                £{fmtCommas(a.deployed_gbp)}
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                £{fmtCommas(a.spreadbet_gbp)}
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                <strong>£{fmtCommas(a.total_value_gbp)}</strong>
              </td>
              <td>{a.positions_count}</td>
              <td>{a.bets_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
