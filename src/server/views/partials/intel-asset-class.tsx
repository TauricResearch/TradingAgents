/**
 * Asset class panel — shows positions grouped by asset class with individual P&L.
 */

/** @jsxImportSource hono/jsx */

import type { AssetClassAllocation } from "../../lib/portfolio-intel-data.ts"
import { fmtCommas } from "../../lib/markup.ts"

const ASSET_COLORS: Record<string, string> = {
  cash: "#3b82f6",
  equity: "#22c55e",
  etf: "#eab308",
  crypto: "#ef4444",
}

export function AssetClassBars({ assetClasses, totalValue }: { assetClasses: AssetClassAllocation[]; totalValue: number }) {
  if (!assetClasses || assetClasses.length === 0) {
    return <div class="muted">No allocation data</div>
  }

  const total = totalValue || 1

  return (
    <div class="allocation-bar">
      <div style="height:16px;display:flex">
        {assetClasses.map((ac) => {
          const w = Math.round((ac.value_gbp / total) * 100)
          const color = ASSET_COLORS[ac.assetClass] ?? "#71717a"
          return (
            <div
              style={`display:inline-block;height:16px;width:${w}%;background:${color};margin-right:2px`}
              title={`${ac.assetClass}: ${w}% (${ac.value_gbp.toFixed(0)} GBP)`}
            />
          )
        })}
      </div>
      <div style="margin-top:4px;font-size:0.75em;color:var(--text-dim)">
        {assetClasses.map((ac) => {
          const w = Math.round((ac.value_gbp / total) * 100)
          const color = ASSET_COLORS[ac.assetClass] ?? "#71717a"
          return (
            <span style="margin-right:12px">
              <span
                style={`display:inline-block;width:10px;height:10px;border-radius:2px;background:${color};vertical-align:middle;margin-right:4px`}
              />
              {ac.assetClass} {w}% ({ac.value_gbp.toFixed(0)})
            </span>
          )
        })}
      </div>
    </div>
  )
}
