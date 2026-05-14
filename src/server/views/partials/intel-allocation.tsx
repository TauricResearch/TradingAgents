/**
 * Allocation bar panel — shows target vs. actual % per asset class with rebalance arrows.
 */

/** @jsxImportSource hono/jsx */

import type { AllocationBar } from "../../lib/portfolio-intel-data.ts"

export function AllocationBarSection({ bar }: { bar: AllocationBar | null }) {
  if (!bar) return null
  const { buckets, actual, targets } = bar
  return (
    <div class="allocation-bar-section" style="margin:1.5rem 0">
      <h4>Allocation Bar (Target vs Actual)</h4>
      <div style="height:24px;display:flex;border-radius:4px;overflow:hidden;margin:8px 0">
        {buckets.map((b) => (
          <div
            style={`display:inline-block;height:24px;width:${b.actual_pct}%;background:${b.color};`}
            title={`${b.label}: ${b.actual_pct}% (target ${b.target_pct}%)`}
          />
        ))}
      </div>
      <div style="font-size:0.75em;color:var(--text-dim)">
        {buckets.map((b) => (
          <span style="margin-right:16px">
            <span
              style={`display:inline-block;width:10px;height:10px;border-radius:2px;background:${b.color};vertical-align:middle;margin-right:4px`}
            />
            {b.label}: {b.actual_pct}% (target {b.target_pct}%)
          </span>
        ))}
      </div>
      {actual.cash_pct < targets.cash_reserve_pct && (
        <div class="hint" style="margin-top:4px">
          ⚠️ Cash below target ({actual.cash_pct}% &lt; {targets.cash_reserve_pct}%)
        </div>
      )}
      {actual.spreadbet_pct > targets.spreadbet_pct && (
        <div class="hint" style="margin-top:4px">
          ⚠️ Spread bet above target ({actual.spreadbet_pct}% &gt; {targets.spreadbet_pct}%)
        </div>
      )}
    </div>
  )
}
