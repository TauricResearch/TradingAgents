/** @jsxImportSource hono/jsx */

import type { PortfolioIntel } from "../../lib/portfolio-intel-data.ts"
import { fmtCommas } from "../../lib/markup.ts"

export function IntelHero({ data }: { data: PortfolioIntel }) {
  return (
    <>
      {data.cash_negative && (
        <div class="banner" style="margin-bottom:1rem">
          ⚠️ hledger cash is negative — more sells recorded than buys in journal.
          Total and % figures may be misleading until hledger cash is corrected.
        </div>
      )}
      <div class="intel-hero">
        <div class="intel-stat">
          <div class="intel-label">Total Portfolio</div>
          <div class="intel-value">£{fmtCommas(data.total_value_gbp)}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Cash</div>
          <div class={`intel-value${data.cash_negative ? " negative" : ""}`}>
            £{fmtCommas(data.cash_gbp)}
            <span class="intel-pct"> ({fmtCommas(data.cash_pct_raw)}%)</span>
          </div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Positions</div>
          <div class="intel-value">{data.positions_count}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Live Value</div>
          <div class="intel-value">£{fmtCommas(data.position_value_gbp)}</div>
        </div>
      </div>
      <div class="intel-fx">
        {data.fx_rates.GBPEUR > 0 && (
          <span>GBPEUR: {data.fx_rates.GBPEUR.toFixed(4)}</span>
        )}
        {data.fx_rates.GBPUSD > 0 && (
          <span>GBPUSD: {data.fx_rates.GBPUSD.toFixed(4)}</span>
        )}
      </div>
    </>
  )
}
