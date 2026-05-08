/** @jsxImportSource hono/jsx */
import type { TradePlan } from "../../lib/trade-calculator.ts"

export function TradePlanView({ plan }: { plan: TradePlan }) {
  const riskWidth = plan.entry - plan.stopLoss
  const target1Width = plan.target1 - plan.entry
  const target2Width = plan.target2 - plan.entry
  const totalWidth = plan.target2 - plan.stopLoss

  const entryPct = totalWidth > 0 ? ((plan.entry - plan.stopLoss) / totalWidth) * 100 : 50
  const t1Pct = totalWidth > 0 ? ((plan.target1 - plan.stopLoss) / totalWidth) * 100 : 65
  const t2Pct = totalWidth > 0 ? ((plan.target2 - plan.stopLoss) / totalWidth) * 100 : 100

  return (
    <section class="panel">
      <h3>
        Trade Plan: {plan.ticker}
        {plan.insufficientHistory && <span class="tag yellow">insufficient history</span>}
      </h3>

      {/* Price ladder visualization */}
      <div class="trade-ladder" style="margin: 1rem 0; position: relative; height: 160px;">
        {/* Stop loss */}
        <div
          style={`position: absolute; bottom: 0; left: 0; width: 100%; height: ${entryPct}%; background: var(--color-danger-muted); border-radius: 4px;`}
        >
          <span style="position: absolute; top: 4px; left: 8px; font-size: 0.75rem; color: var(--color-danger);">
            Stop: {plan.stopLoss} ({plan.entry > 0 ? ((plan.entry - plan.stopLoss) / plan.entry * 100).toFixed(1) : 0}%)
          </span>
        </div>

        {/* Entry */}
        <div
          style={`position: absolute; bottom: ${entryPct}%; left: 0; width: 100%; height: 2px; background: var(--color-text);`}
        >
          <span style="position: absolute; top: -12px; right: 8px; font-size: 0.75rem; font-weight: bold;">
            Entry: {plan.entry}
          </span>
        </div>

        {/* Target 1 */}
        <div
          style={`position: absolute; bottom: ${entryPct}%; left: 0; width: 100%; height: ${t1Pct - entryPct}%; background: var(--color-warning-muted); border-radius: 4px;`}
        >
          <span style="position: absolute; top: 4px; left: 8px; font-size: 0.75rem; color: var(--color-warning);">
            T1: {plan.target1} (scale 50%)
          </span>
        </div>

        {/* Target 2 */}
        <div
          style={`position: absolute; bottom: ${t1Pct}%; left: 0; width: 100%; height: ${t2Pct - t1Pct}%; background: var(--color-success-muted); border-radius: 4px;`}
        >
          <span style="position: absolute; top: 4px; left: 8px; font-size: 0.75rem; color: var(--color-success);">
            T2: {plan.target2} (full exit)
          </span>
        </div>
      </div>

      {/* Metrics grid */}
      <div class="metrics-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin-top: 1rem;">
        <Metric label="Position Size" value={`${plan.positionSize} shares`} />
        <Metric label="Notional" value={`£${(plan.positionSize * plan.entry).toFixed(2)}`} />
        <Metric label="Risk Amount" value={`£${plan.riskAmount.toFixed(2)}`} />
        <Metric label="Risk %" value={`${(plan.riskPercent * 100).toFixed(2)}%`} />
        <Metric label="ATR (14d)" value={plan.atr14.toFixed(4)} />
        <Metric label="R/R (T2)" value={plan.entry - plan.stopLoss > 0 ? ((plan.target2 - plan.entry) / (plan.entry - plan.stopLoss)).toFixed(2) : "—"} />
      </div>

      {/* Warnings */}
      {plan.concentrationFlag && (
        <div class="alert danger" style="margin-top: 1rem;">
          ⚠️ Concentration risk: position exceeds 5% of portfolio
        </div>
      )}

      {plan.insufficientHistory && (
        <div class="alert warning" style="margin-top: 0.5rem;">
          ⚠️ Less than 22 days of price history. ATR and swing detection may be unreliable.
        </div>
      )}

      {/* Bracket order summary */}
      <div style="margin-top: 1.5rem; padding: 0.75rem; background: var(--color-surface); border-radius: 8px;">
        <h4 style="margin: 0 0 0.5rem 0; font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em;">
          Bracket Order
        </h4>
        <pre style="margin: 0; font-size: 0.8rem; overflow-x: auto;">
{`BUY  ${plan.positionSize} @ ${plan.entry} (Limit)
→ SELL ${Math.floor(plan.positionSize / 2)} @ ${plan.target1} (Limit GTC)  [50% at T1]
→ SELL ${plan.positionSize - Math.floor(plan.positionSize / 2)} @ ${plan.target2} (Limit GTC)  [remainder at T2]
→ STOP ${plan.positionSize} @ ${plan.stopLoss} (Stop-Limit)`}
        </pre>
      </div>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style="padding: 0.5rem; background: var(--color-surface); border-radius: 6px;">
      <div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-muted);">
        {label}
      </div>
      <div style="font-size: 1rem; font-weight: 600; margin-top: 0.25rem;">
        {value}
      </div>
    </div>
  )
}
