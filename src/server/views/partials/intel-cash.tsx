/** @jsxImportSource hono/jsx */

import type { CashBreakdown } from "../../lib/portfolio-intel-data.ts"
import { fmtCommas } from "../../lib/markup.ts"

export function CashBreakdownPanel({ breakdown }: { breakdown: CashBreakdown | null }) {
  if (!breakdown) return null
  return (
    <div class="cash-breakdown" style="margin:1.5rem 0">
      <h4>Cash Breakdown</h4>
      <div class="intel-hero" style="margin-top:0.5rem">
        <div class="intel-stat">
          <div class="intel-label">Total Cash</div>
          <div class={`intel-value${breakdown.cash_negative ? " negative" : ""}`}>
            £{fmtCommas(breakdown.total_cash_gbp)}
          </div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Reserve ({breakdown.reserve_pct}%)</div>
          <div class="intel-value">£{fmtCommas(breakdown.reserve_gbp)}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Spread Bet Alloc ({breakdown.spreadbet_allocation_pct}%)</div>
          <div class="intel-value">£{fmtCommas(breakdown.spreadbet_allocation_gbp)}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Investable</div>
          <div class="intel-value">£{fmtCommas(breakdown.investable_gbp)}</div>
        </div>
      </div>
    </div>
  )
}
